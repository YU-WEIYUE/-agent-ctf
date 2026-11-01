"""LangGraph autonomous cycle; SQLite checkpoint and the external CLI share one engine."""

import json
import time
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, messages_to_dict
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from ctf_forge.llm.client import ModelClient
from ctf_forge.tools.registry import candidate_values
from ctf_forge.workflow.session import Session


class GraphState(TypedDict):
    task_id: str
    phase: str
    tool_calls: int
    llm_calls: int
    status: str
    challenge: dict[str, Any]
    sandbox_id: str | None
    messages: list[dict[str, Any]]
    plan: list[str]
    observations: list[dict[str, Any]]
    candidate_flags: list[dict[str, Any]]
    verified_flag: str | None
    tokens: int


def model_observation(output: dict[str, Any]) -> str:
    """Keep complete observations on disk; send a bounded evidence summary to the model."""
    if output.get("tool") == "inspect_elf" and output.get("exit_code") == 0:
        parsed = json.loads(output["stdout"])
        summary = {
            "bits": parsed["bits"],
            "header": parsed["header"],
            "sections": [
                {k: s.get(k) for k in ("name", "sh_addr", "sh_offset", "sh_size")}
                for s in parsed["sections"]
            ],
            "symbols": [
                {k: s.get(k) for k in ("name", "st_value", "st_size")}
                for s in parsed["symbols"]
                if s.get("name")
            ][:100],
        }
        return json.dumps(
            {
                "tool": "inspect_elf",
                "summary": summary,
                "full_result": "saved in task observations; use Python for more details",
            }
        )
    bounded = dict(output)
    for key in ("stdout", "stderr"):
        text = bounded.get(key, "")
        if len(text) > 8000:
            bounded[key] = (
                text[:6000] + "\n[model context truncated; full output saved]\n" + text[-1500:]
            )
    # Avoid echoing long Python source from argv back into the model context.
    bounded.pop("argv", None)
    return json.dumps(bounded)


def run_autonomous(session: Session, client: Any | None = None) -> None:

    def snapshot(phase: str) -> GraphState:
        session.save()
        return {
            "task_id": session.record.task_id,
            "phase": phase,
            "tool_calls": session.record.tool_calls,
            "llm_calls": session.record.llm_calls,
            "status": session.record.status,
            "challenge": session.record.challenge.model_dump(),
            "sandbox_id": session.record.sandbox_id,
            "messages": messages_to_dict(session.messages),
            "plan": session.plan,
            "observations": session.observations,
            "candidate_flags": [f.model_dump() for f in session.record.candidate_flags],
            "verified_flag": session.record.verified_flag,
            "tokens": session.record.tokens,
        }

    def prepare(state: GraphState) -> GraphState:
        session.prepare()
        output = session.apply("inspect_elf", {})
        if output.get("exit_code") != 0:
            session.finish("invalid_or_unparseable_elf", failed=True)
        session.messages.append(
            HumanMessage(
                content="Initial ELF observation (untrusted):\n" + model_observation(output)
            )
        )
        return snapshot("prepared")

    def solver(state: GraphState) -> GraphState:
        if session.record.status != "running":
            return snapshot("stopped")
        reason = session.budget_reason()
        if reason:
            session.finish(reason)
            return snapshot("stopped")
        session.record.llm_calls += 1
        session.save()  # Failed API attempts consume a model call too.
        response: AIMessage = model.invoke(
            session.messages,
            session.settings.agent.max_tokens - session.record.tokens,
            session.settings.agent.max_seconds - (time.time() - session.started_at),
        )
        usage = response.usage_metadata
        session.record.llm_calls += response.response_metadata.get("request_attempts", 1) - 1
        session.record.tokens += (
            usage["total_tokens"] if usage else len(str(response.content).encode())
        )
        session.messages.append(response)
        return snapshot("model_response")

    def tools(state: GraphState) -> GraphState:
        response = session.messages[-1]
        if isinstance(response, AIMessage) and response.tool_calls:
            for call in response.tool_calls:
                if session.record.status != "running":
                    result = {"stopped": session.record.status}
                else:
                    result = session.apply(call["name"], call["args"])
                session.messages.append(
                    ToolMessage(content=model_observation(result), tool_call_id=call["id"])
                )
        else:
            text = str(response.content)
            values = candidate_values(text)
            for value in values:
                if session.record.status == "running":
                    session.apply("submit_flag", {"value": value})
            if session.record.status == "running":
                session.stalled += 1
                session.messages.append(
                    HumanMessage(
                        content=(
                            "No verified result. Use a registered tool, submit_flag, or finish."
                        )
                    )
                )
        return snapshot("tools_complete")

    def route(state: GraphState) -> str:
        return "solver" if session.record.status == "running" else "report"

    def report(state: GraphState) -> GraphState:
        session.finish(session.record.stop_reason or "verified")
        return snapshot("reported")

    graph = StateGraph(GraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("solver", solver)
    graph.add_node("tools", tools)
    graph.add_node("report", report)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "solver")
    graph.add_conditional_edges(
        "solver", lambda state: "report" if state["status"] != "running" else "tools"
    )
    graph.add_conditional_edges("tools", route)
    graph.add_edge("report", END)
    try:
        model = client or ModelClient(session.settings.model)
        with SqliteSaver.from_conn_string(str(session.root / ".data/checkpoints.sqlite3")) as saver:
            graph.compile(checkpointer=saver).invoke(
                snapshot("start"),
                {
                    "configurable": {"thread_id": session.record.task_id},
                    "recursion_limit": 4 * session.settings.agent.max_llm_calls + 20,
                },
            )
    except Exception as exc:
        # Persist failure and clean the sandbox without logging API response bodies.
        session.finish("workflow_error:" + type(exc).__name__, failed=True)
        raise
