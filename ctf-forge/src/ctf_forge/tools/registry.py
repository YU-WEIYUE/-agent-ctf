"""Model-visible schemas mapped to validated Docker argv only."""

import re
from typing import Any, Literal

from pydantic import Field

from ctf_forge.core.models import StrictModel
from ctf_forge.sandbox.docker_runtime import DockerRuntime


class NoArgs(StrictModel):
    pass


class DisassembleArgs(StrictModel):
    symbol: str = Field(default="main", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")


class PythonArgs(StrictModel):
    code: str = Field(min_length=1, max_length=16000)


class RunArgs(StrictModel):
    arguments: list[str] = Field(default_factory=list, max_length=16)


class GdbArgs(StrictModel):
    action: Literal["info", "registers", "disassemble", "run"] = "info"


class SubmitArgs(StrictModel):
    value: str = Field(min_length=1, max_length=4096)


class FinishArgs(StrictModel):
    reason: str = Field(min_length=1, max_length=2000)


ELF_SCRIPT = """
import json
from elftools.elf.elffile import ELFFile
from elftools.elf.sections import SymbolTableSection
from elftools.elf.relocation import RelocationSection
with open('/input/challenge','rb') as f:
 e=ELFFile(f)
 out={'bits':e.elfclass,'little_endian':e.little_endian,'header':dict(e.header),
 'segments':[dict(s.header) for s in e.iter_segments()],
 'sections':[{'name':s.name,**dict(s.header)} for s in e.iter_sections()],
 'symbols':[], 'relocations':[], 'dynamic':[]}
 for s in e.iter_sections():
  if isinstance(s,SymbolTableSection):
   out['symbols'] += [{'name':v.name,**dict(v.entry)} for v in list(s.iter_symbols())[:1000]]
  if isinstance(s,RelocationSection):
   out['relocations'] += [dict(v.entry) for v in list(s.iter_relocations())[:1000]]
  if s.header.sh_type=='SHT_DYNAMIC':
   out['dynamic'] += [str(v) for v in list(s.iter_tags())[:1000]]
 print(json.dumps(out,default=str))
"""

_FLAG_PREFIXES = (
    "picoCTF",
    "hiCTF",
    "DUCTF",
    "DCTF",
    "HTB",
    "flag",
    "CTF",
    "ictf",
)
CANDIDATE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    + "|".join(re.escape(prefix) for prefix in _FLAG_PREFIXES)
    + r")\{[^\r\n{}]{1,250}\}",
    re.IGNORECASE,
)

TOOLS: dict[str, tuple[type[StrictModel], str]] = {
    "inspect_elf": (NoArgs, "Structured ELF headers, sections, symbols, relocations and imports."),
    "strings": (NoArgs, "Extract printable strings from the challenge ELF."),
    "capstone": (NoArgs, "Decode the first 128 .text instructions of an x86/x86-64 ELF."),
    "disassemble": (DisassembleArgs, "Disassemble a named function with objdump."),
    "python": (
        PythonArgs,
        "Run bounded Python in the offline sandbox to decode data or inspect bytes.",
    ),
    "run_binary": (RunArgs, "Execute the authorized ELF with optional argv in the sandbox."),
    "gdb": (GdbArgs, "Batch GDB; auto-loading disabled. May be restricted by the sandbox profile."),
    "submit_flag": (
        SubmitArgs,
        "Send a candidate to the host verifier; never self-certify success.",
    ),
    "finish": (FinishArgs, "Stop with a partial report when no justified next step remains."),
}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": schema.model_json_schema(),
            },
        }
        for name, (schema, description) in TOOLS.items()
    ]


def validate_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        raise ValueError("Unknown tool")
    parsed = TOOLS[name][0].model_validate(arguments).model_dump()
    if name == "run_binary" and any(len(x) > 4096 or "\x00" in x for x in parsed["arguments"]):
        raise ValueError("Invalid binary argument")
    return parsed


def execute_tool(runtime: DockerRuntime, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = validate_call(name, arguments)
    argv: list[str]
    if name == "inspect_elf":
        argv = ["python3", "-I", "-c", ELF_SCRIPT]
    elif name == "strings":
        argv = ["strings", "-a", "-n", "4", "/input/challenge"]
    elif name == "capstone":
        code = (
            "import json,capstone; from elftools.elf.elffile import ELFFile; "
            "f=open('/input/challenge','rb'); e=ELFFile(f); "
            "assert e.header.e_machine in ('EM_X86_64','EM_386'),'Unsupported architecture'; "
            "s=e.get_section_by_name('.text'); "
            "m=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64 if e.elfclass==64 "
            "else capstone.CS_MODE_32); "
            "print(json.dumps([{'address':i.address,'mnemonic':i.mnemonic,'operands':i.op_str} "
            "for i in m.disasm(s.data(),s.header.sh_addr,count=128)]))"
        )
        argv = ["python3", "-I", "-c", code]
    elif name == "disassemble":
        argv = [
            "objdump",
            "-d",
            "-M",
            "intel",
            f"--disassemble={args['symbol']}",
            "/input/challenge",
        ]
    elif name == "python":
        argv = ["python3", "-I", "-c", args["code"]]
    elif name == "run_binary":
        argv = ["/input/challenge", *args["arguments"]]
    elif name == "gdb":
        actions = {
            "info": "info files",
            "registers": "info registers",
            "disassemble": "disassemble main",
            "run": "run",
        }
        argv = [
            "gdb",
            "-nx",
            "-nh",
            "-batch",
            "-iex",
            "set auto-load off",
            "-ex",
            "set startup-with-shell off",
            "-ex",
            actions[args["action"]],
            "--args",
            "/input/challenge",
        ]
    else:
        raise ValueError("This tool is handled by the host verifier/coordinator")
    result = runtime.execute(argv)
    return {**vars(result), "tool": name, "argv": argv}


def candidate_values(text: str) -> list[str]:
    """Extract whole flag-shaped tokens; the prefix must not be a truncated suffix.

    A bare ``CTF{...}`` pattern would clip the leading characters of prefixes such
    as ``hiCTF{...}``, so known prefixes are matched whole, longest first.
    """
    return list(dict.fromkeys(match.group(0) for match in CANDIDATE_PATTERN.finditer(text)))
