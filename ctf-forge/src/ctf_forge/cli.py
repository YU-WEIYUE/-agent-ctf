"""Foundation CLI; analysis commands fail explicitly until the sandbox is built."""

import json
import sqlite3
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, Literal, cast

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ctf_forge import __version__
from ctf_forge.config import load_settings
from ctf_forge.core.events import create_logger
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.core.models import ChallengeSpec
from ctf_forge.storage.repository import TaskRepository

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
task_app = typer.Typer(no_args_is_help=True)
platform_app = typer.Typer(no_args_is_help=True)
app.add_typer(task_app, name="task")
app.add_typer(platform_app, name="platform")
console = Console(highlight=False)


def platform_client(root: Path) -> Any:
    """Build the host-side platform client from project configuration."""
    from ctf_forge.platform.rctf import RctfClient

    return RctfClient(load_settings(root).platform, root)


def emit_json(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=True, indent=2))


def guarded[F: Callable[..., Any]](function: F) -> F:
    """Convert expected failures into nonzero, secret-safe CLI errors."""

    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except ValidationError as exc:
            fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
            console.print("Invalid input/configuration fields: " + ", ".join(fields), markup=False)
            raise typer.Exit(2) from exc
        except (ForgeError, OSError, sqlite3.Error) as exc:
            console.print(f"Error: {exc}", markup=False)
            raise typer.Exit(1) from exc

    return cast(F, wrapper)


@dataclass
class Context:
    root: Path
    log_file: Path

    def repository(self) -> TaskRepository:
        return TaskRepository(self.root / ".data" / "tasks.sqlite3")


def context(ctx: typer.Context) -> Context:
    return cast(Context, ctx.obj)


def version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    project: Annotated[
        Path, typer.Option(help="Project root (configuration and task storage)")
    ] = Path("."),
    log_file: Annotated[Path | None, typer.Option(help="Optional JSONL log destination")] = None,
    version: Annotated[
        bool, typer.Option("--version", callback=version_callback, is_eager=True)
    ] = False,
) -> None:
    """CTF-Forge: sandboxed local Reverse workflow for autonomous or external agents."""
    root = project.resolve()
    if not root.is_dir():
        raise typer.BadParameter("Project directory does not exist")
    ctx.obj = Context(root, log_file or root / ".data" / "events.jsonl")


@app.command()
@guarded
def init(ctx: typer.Context) -> None:
    """Validate configuration and initialize local task storage (idempotent)."""
    config = context(ctx)
    load_settings(config.root)
    config.repository()
    for name in ("workspaces", "reports"):
        (config.root / name).mkdir(exist_ok=True)
    create_logger(config.log_file).info("project_initialized", root=str(config.root))
    console.print("Project initialized. No sandbox or model has been started.")


@app.command("config-check")
@guarded
def config_check(ctx: typer.Context) -> None:
    """Validate all configuration and show only non-secret readiness indicators."""
    settings = load_settings(context(ctx).root)
    proof = context(ctx).root / ".data/environment-check.json"
    verified = False
    if proof.exists():
        data = json.loads(proof.read_text(encoding="utf-8"))
        verified = (
            data.get("passed", False)
            and data.get("sandbox_settings") == settings.sandbox.model_dump()
        )
    console.print_json(
        data={
            "valid": True,
            "model_name_configured": bool(settings.model.name),
            "model_endpoint_configured": bool(settings.model.base_url),
            "model_key_configured": bool(
                settings.model.api_key and settings.model.api_key.get_secret_value()
            ),
            "max_tool_calls": settings.agent.max_tool_calls,
            "network": settings.sandbox.network,
            "runtime_implemented": True,
            "runtime_integration_verified": verified,
        }
    )


@app.command()
@guarded
def doctor(ctx: typer.Context) -> None:
    """Check the host Docker CLI/daemon with a bounded, read-only probe."""
    from ctf_forge.sandbox.docker_runtime import docker_command

    settings = load_settings(context(ctx).root)
    try:
        prefix = docker_command(settings.sandbox)
    except ForgeError:
        console.print("Docker CLI missing. Milestone 2 requires Docker with Linux containers.")
        raise typer.Exit(1) from None
    try:
        result = subprocess.run(
            [*prefix, "info", "--format", "{{.OSType}}"],
            capture_output=True,
            timeout=10,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, OSError):
        console.print("Docker daemon probe failed or timed out.")
        raise typer.Exit(1) from None
    if result.returncode != 0 or result.stdout.strip() != "linux":
        console.print("Docker is unavailable or is not running Linux containers.")
        raise typer.Exit(1)
    console.print("Docker Linux daemon reachable; use self-test to verify sandbox policy.")


@task_app.command("add")
@guarded
def task_add(ctx: typer.Context, spec: Path) -> None:
    """Store an authorized challenge JSON; resolves files relative to the manifest."""
    config = context(ctx)
    load_settings(config.root)
    if spec.stat().st_size > 1048576:
        raise ForgeError("Challenge specification exceeds 1 MiB")
    challenge = ChallengeSpec.model_validate_json(spec.read_text(encoding="utf-8-sig"))
    attachments: list[str] = []
    for filename in challenge.files:
        path = (spec.resolve().parent / filename).resolve()
        if not path.is_file():
            raise ForgeError(f"Attachment does not exist or is not a file: {path}")
        attachments.append(str(path))
    challenge = ChallengeSpec.model_validate({**challenge.model_dump(), "files": attachments})
    record = config.repository().add(challenge)
    create_logger(config.log_file).info(
        "task_created",
        task_id=record.task_id,
        challenge_id=challenge.challenge_id,
    )
    console.print(record.task_id)


@task_app.command("list")
@guarded
def task_list(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(min=1, max=1000)] = 50,
) -> None:
    """List persisted tasks, newest first."""
    table = Table("Task ID", "Challenge", "Status")
    for record in context(ctx).repository().list(limit):
        from rich.text import Text

        table.add_row(Text(record.task_id), Text(record.challenge.name), Text(record.status))
    console.print(table)


@task_app.command("show")
@guarded
def task_show(ctx: typer.Context, task_id: str) -> None:
    """Read a persisted task with its counters and verification states."""
    record = context(ctx).repository().get(task_id)
    emit_json(record.model_dump(mode="json"))


@platform_app.command("me")
@guarded
def platform_me(ctx: typer.Context) -> None:
    """Show the authenticated platform identity and division; never prints tokens."""
    data = platform_client(context(ctx).root).me()
    emit_json(
        {
            key: data.get(key)
            for key in ("id", "name", "division", "score", "allowedDivisions", "banned")
        }
    )


@platform_app.command("list")
@guarded
def platform_list(
    ctx: typer.Context,
    category: Annotated[str | None, typer.Option(help="Filter by category name")] = None,
) -> None:
    """List platform challenges (id, name, category, points, solves)."""
    items = platform_client(context(ctx).root).challenges()
    if category:
        wanted = category.lower()
        items = [item for item in items if str(item.get("category", "")).lower() == wanted]
    emit_json(
        [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "category": item.get("category"),
                "points": item.get("points"),
                "solves": item.get("solves"),
            }
            for item in items
        ]
    )


@platform_app.command("pull")
@guarded
def platform_pull(
    ctx: typer.Context,
    challenge: Annotated[str, typer.Argument(help="Challenge name or id")],
    dest: Annotated[Path | None, typer.Option(help="Destination directory")] = None,
) -> None:
    """Download a challenge's attachment(s) on the host and verify declared SHA-256."""
    from ctf_forge.platform.rctf import slug

    config = context(ctx)
    client = platform_client(config.root)
    found = client.find(challenge)
    target = dest or config.root / "challenges" / "platform" / slug(str(found.get("name")))
    manifest = client.pull(str(found.get("id")), target)
    emit_json(manifest)
    if not manifest["all_verified"]:
        raise typer.Exit(1)


@platform_app.command("submit")
@guarded
def platform_submit(
    ctx: typer.Context,
    challenge: Annotated[str, typer.Argument(help="Challenge name or id")],
    flag: Annotated[str, typer.Option(help="Candidate flag value")],
) -> None:
    """Submit one candidate flag to the platform and print its verdict."""
    client = platform_client(context(ctx).root)
    found = client.find(challenge)
    verdict = client.submit(str(found.get("id")), flag)
    emit_json({"challenge": found.get("name"), "challenge_id": found.get("id"), **verdict})


@app.command()
@guarded
def report(ctx: typer.Context, task_id: str) -> None:
    """Read the saved complete/partial JSON report or a pending task snapshot."""
    record = context(ctx).repository().get(task_id)
    if record.report_path:
        emit_json(json.loads(Path(record.report_path).read_text(encoding="utf-8")))
    else:
        emit_json({"kind": "task_snapshot", "task": record.model_dump(mode="json")})


@app.command()
@guarded
def inspect(
    ctx: typer.Context,
    binary: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False)],
) -> None:
    """Run file/readelf/strings inside the restricted Docker container; JSON output."""
    from ctf_forge.tools.analyze import inspect_binary

    config = context(ctx)
    result = inspect_binary(binary, config.root, load_settings(config.root).sandbox)
    create_logger(config.log_file).info("static_inspection_finished", tool_count=3)
    console.print_json(data=result)


@app.command()
def capabilities() -> None:
    """Print the versioned machine-readable discovery contract for any agent."""
    console.print_json(
        data={
            "schema_version": 1,
            "project": "ctf-forge",
            "version": __version__,
            "entrypoint": "uv run ctf-forge",
            "local_commands": [
                "init",
                "config-check",
                "task add",
                "task list",
                "task show",
                "report",
            ],
            "sandbox_commands": ["inspect", "solve", "step", "observe", "close", "resume"],
            "platform_commands": [
                "platform me",
                "platform list",
                "platform pull",
                "platform submit",
            ],
            "sandbox_validation": "see IMPLEMENTATION_STATUS.md for actual verification",
            "unavailable": ["remote_instance_challenges", "non_reverse_categories"],
            "modes": ["autonomous", "external"],
            "tool_schemas_command": "uv run ctf-forge tools",
            "preflight": "uv run ctf-forge doctor",
            "inspection_output": "JSON; static analysis only, no flag verification",
            "exit_codes": {
                "0": "command completed",
                "1": "runtime/dependency failure",
                "2": "invalid input or unavailable feature",
                "3": "autonomous task ended partial/unverified",
            },
            "instructions": "AGENTS.md",
            "state_document": "IMPLEMENTATION_STATUS.md",
            "model_credentials_required_for_inspect": False,
            "network_in_sandbox": "none",
        }
    )


@app.command()
@guarded
def solve(
    ctx: typer.Context,
    binary: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    description: Annotated[Path | None, typer.Option(help="Challenge description file")] = None,
    answer_file: Annotated[
        Path | None, typer.Option(help="Host-only trusted exact answer file")
    ] = None,
    platform_challenge: Annotated[
        str | None,
        typer.Option(help="rCTF challenge id used as the independent verifier"),
    ] = None,
    non_elf: Annotated[
        bool,
        typer.Option(help="Input is not an ELF (bytecode, image); skip the ELF gate"),
    ] = False,
    mode: Literal["autonomous", "external"] = "external",
    max_seconds: Annotated[int | None, typer.Option(min=1, max=86400)] = None,
    max_tools: Annotated[int | None, typer.Option(min=1, max=1000)] = None,
) -> None:
    """Solve through LangGraph or start a durable session driven by any external agent."""
    from ctf_forge.workflow.graph import run_autonomous
    from ctf_forge.workflow.session import Session, task_lock

    config = context(ctx)
    settings = load_settings(config.root)
    if max_seconds is not None:
        settings.agent.max_seconds = max_seconds
    if max_tools is not None:
        settings.agent.max_tool_calls = max_tools
    text = "Authorized local reverse engineering challenge."
    if description:
        if description.stat().st_size > 100000:
            raise ForgeError("Description exceeds 100000 bytes")
        text = description.read_text(encoding="utf-8-sig")
    session = Session.create(config.root, settings, binary, text, answer_file, platform_challenge)
    with task_lock(config.root, session.record.task_id):
        if mode == "autonomous":
            try:
                run_autonomous(session)
            except Exception as exc:
                raise ForgeError(
                    f"Workflow failed ({type(exc).__name__}); task {session.record.task_id}; "
                    "inspect saved report"
                ) from None
        else:
            try:
                session.prepare()
                if non_elf:
                    # Non-ELF inputs (BEAM bytecode, disk images) use strings/python.
                    session.apply("strings", {})
                else:
                    output = session.apply("inspect_elf", {})
                    if output.get("exit_code") != 0:
                        session.finish("invalid_or_unparseable_elf", failed=True)
            except Exception as exc:
                session.finish("prepare_error:" + type(exc).__name__, failed=True)
                raise ForgeError(f"Preparation failed; task {session.record.task_id}") from None
    emit_json(session.view())
    if session.record.status in {"partial", "failed"}:
        raise typer.Exit(3 if session.record.status == "partial" else 1)


@app.command()
@guarded
def observe(ctx: typer.Context, task_id: str) -> None:
    """Get model-visible task context and registered tool schemas as JSON."""
    from ctf_forge.workflow.session import Session

    config = context(ctx)
    emit_json(Session.load(config.root, load_settings(config.root), task_id).view())


@app.command()
@guarded
def step(ctx: typer.Context, task_id: str, action: Annotated[Path, typer.Option()]) -> None:
    """Apply {tool, arguments} JSON from an external agent; verify/report on success."""
    from ctf_forge.workflow.session import Session, task_lock

    config = context(ctx)
    if action.stat().st_size > 20000:
        raise ForgeError("Action exceeds 20000 bytes")
    try:
        data = json.loads(action.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ForgeError("Action must be valid JSON") from exc
    if not isinstance(data, dict) or set(data) != {"tool", "arguments"}:
        raise ForgeError("Action requires exactly tool and arguments")
    if not isinstance(data["tool"], str) or not isinstance(data["arguments"], dict):
        raise ForgeError("Invalid action field types")
    with task_lock(config.root, task_id):
        session = Session.load(config.root, load_settings(config.root), task_id)
        output = session.apply(data["tool"], data["arguments"])
        if session.record.status == "succeeded":
            session.finish("verified")
        emit_json({"result": output, "task": session.view()})


@app.command()
@guarded
def close(ctx: typer.Context, task_id: str) -> None:
    """Stop a session, destroy its sandbox and save a partial report."""
    from ctf_forge.workflow.session import Session, task_lock

    config = context(ctx)
    with task_lock(config.root, task_id):
        session = Session.load(config.root, load_settings(config.root), task_id)
        session.finish("user_closed")
        emit_json(session.view())


@app.command()
@guarded
def resume(ctx: typer.Context, task_id: str) -> None:
    """Explicitly recover a sandbox for external-agent continuation within original budgets."""
    from ctf_forge.workflow.session import Session, task_lock

    config = context(ctx)
    with task_lock(config.root, task_id):
        session = Session.load(config.root, load_settings(config.root), task_id)
        if session.record.status == "succeeded":
            raise ForgeError("Task already verified")
        reason = session.budget_reason(check_model=False)
        if reason:
            raise ForgeError(f"Original budget exhausted ({reason}); start a new task explicitly")
        try:
            session.runtime.destroy()
        except ForgeError:
            raise ForgeError(
                "Cannot verify old sandbox cleanup; inspect Docker before recovery"
            ) from None
        session.prepare()
        emit_json(session.view())


@app.command()
def tools() -> None:
    """Discover all tool names and JSON argument schemas without starting a model."""
    from ctf_forge.tools.registry import tool_schemas

    emit_json({"schema_version": 1, "tools": tool_schemas()})


@app.command("self-test")
@guarded
def self_test(ctx: typer.Context) -> None:
    """Exercise real container isolation, resource limits and timeout cleanup."""
    from ctf_forge.evaluation.environment import check_environment
    from ctf_forge.workflow.session import write_json

    config = context(ctx)
    result = check_environment(config.root, load_settings(config.root))
    (config.root / ".data").mkdir(exist_ok=True)
    write_json(config.root / ".data/environment-check.json", result)
    emit_json(result)
    if not result["passed"]:
        raise typer.Exit(1)


@app.command("build-samples")
@guarded
def build_samples_command(ctx: typer.Context) -> None:
    """Compile ten self-authored ELF smoke fixtures inside Docker, keeping answers separate."""
    from ctf_forge.evaluation.benchmark import build_samples

    config = context(ctx)
    emit_json({"manifest": str(build_samples(config.root, load_settings(config.root)))})


@app.command()
@guarded
def benchmark(
    ctx: typer.Context,
    manifest: Path = Path("challenges/samples/smoke/manifest.json"),
    attempts: Annotated[int, typer.Option(min=1, max=3)] = 1,
    limit: Annotated[int, typer.Option(min=1, max=100)] = 10,
    max_seconds: Annotated[int, typer.Option(min=1, max=3600)] = 120,
) -> None:
    """Run a real model on answer-separated fixtures; save all failures and measured metrics."""
    from ctf_forge.evaluation.benchmark import run_benchmark

    config = context(ctx)
    settings = load_settings(config.root)
    settings.agent.max_seconds = max_seconds
    settings.agent.max_llm_calls = 8
    emit_json(run_benchmark(config.root, settings, manifest.resolve(), attempts, limit))


@app.command("model-check")
@guarded
def model_check(ctx: typer.Context) -> None:
    """Make one real model request to check registered tool calling without a challenge."""
    from langchain_core.messages import HumanMessage

    from ctf_forge.llm.client import ModelClient

    settings = load_settings(context(ctx).root)
    try:
        response = ModelClient(settings.model).invoke(
            [HumanMessage(content="Call the strings tool with no arguments. /no_think")],
            settings.agent.max_tokens,
            settings.model.timeout_seconds,
        )
    except Exception as exc:
        raise ForgeError("Model probe failed: " + type(exc).__name__) from None
    emit_json(
        {
            "tool_calling": bool(response.tool_calls),
            "tools": [c["name"] for c in response.tool_calls],
            "usage": response.usage_metadata,
        }
    )
    if not response.tool_calls:
        raise typer.Exit(1)


@app.command("build-image")
@guarded
def build_image(ctx: typer.Context) -> None:
    """Build the analysis image using native Docker or the configured WSL engine."""
    from ctf_forge.sandbox.docker_runtime import bounded_run, docker_command, mount_path
    from ctf_forge.workflow.session import write_json

    config = context(ctx)
    settings = load_settings(config.root).sandbox
    result = bounded_run(
        [
            *docker_command(settings),
            "build",
            "-t",
            settings.image,
            mount_path(config.root / "docker", settings),
        ],
        600,
        65536,
    )
    (config.root / ".data").mkdir(exist_ok=True)
    write_json(config.root / ".data/image-build.json", vars(result))
    emit_json(
        {
            "success": result.success,
            "image": settings.image,
            "log": str(config.root / ".data/image-build.json"),
        }
    )
    if not result.success:
        raise typer.Exit(1)
