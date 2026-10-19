"""Progressive-disclosure skill loader (guide 7.2).

L1 at startup: only name + description from each SKILL.md frontmatter.
L2 when a task matches: the full SKILL.md body goes into the system prompt.
L3 on demand: references/* through read_reference(name).
Scripts are imported as tool functions (script_tools) and stay runnable from the command line.

Every level used is recorded in loader.log. A loader keeps one log for its lifetime; when one
loader serves several runs, call start_run() at the start of each run so its log starts again
at L1.
"""
from __future__ import annotations

import copy
import functools
import importlib.util
import logging
import re
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any

log = logging.getLogger("fasalnama.skills")
SKILLS_ROOT = Path(__file__).resolve().parents[1] / "skill"
_WORD_RE = re.compile(r"[a-z]{4,}")
# Words that say nothing about the task: function words and the "Use when a user asks ..."
# phrasing that every skill description shares. Only words of 4+ letters are tokens at all.
_STOPWORDS = frozenset(
    "about after also another because been before being between both could does doing done "
    "each every from have having help here into just like make many more most much must need "
    "never only other over please same should show some such tell than that their them then "
    "there these they this those through under until upon user users uses using very want "
    "what when where which while will with within without would your asks asked".split()
)
MIN_MATCH_WORDS = 2  # distinct content words a task must share with a skill's description
_LEVEL_RE = re.compile(r"L(\d):")
# YAML block scalar header: | or > with optional chomping (+/-) and indentation indicators.
_BLOCK_HEADER = re.compile(r"([|>])([1-9][+-]?|[+-][1-9]?)?(?:\s+#.*)?")


@dataclass(frozen=True)
class SkillMeta:
    name: str
    description: str
    path: Path


@dataclass
class DisclosureLog:
    """Levels used, in order: "L1:frontmatter", "L2:body:<skill>", "L3:reference:<file>" and
    "script:<name>"."""

    levels: list[str] = field(default_factory=list)

    def record(self, level: str) -> None:
        self.levels.append(level)
        log.info("skill disclosure: %s", level)

    @property
    def deepest_level(self) -> str:
        """Deepest level reached: "L1", "L2" or "L3" ("" if nothing was recorded). Running a
        script counts as L3, the level of a skill's bundled resources and code."""
        depth = 0
        for entry in self.levels:
            found = _LEVEL_RE.match(entry)
            level = int(found.group(1)) if found else 3 if entry.startswith("script:") else 0
            depth = max(depth, level)
        return f"L{depth}" if depth else ""


# --- frontmatter ---------------------------------------------------------------------------
def read_frontmatter(skill_md: Path) -> dict[str, str]:
    """Read ONLY the frontmatter block (stops at the closing ---). Top-level keys only.

    Handles the YAML subset skill frontmatter uses: plain or quoted scalars (indented
    continuation lines are folded into one line) and literal (|) or folded (>) block scalars
    with optional chomping and indentation indicators. Values are stripped of surrounding
    whitespace, so chomping makes no difference. Nested mappings such as metadata: read as "".
    A UTF-8 byte order mark is ignored.
    """
    lines: list[str] = []
    with skill_md.open(encoding="utf-8-sig") as fh:
        if fh.readline().strip() != "---":
            raise ValueError(f"{skill_md} has no frontmatter")
        for line in fh:
            if _is_marker(line):
                return _top_level(lines)
            lines.append(line.rstrip("\r\n"))
    raise ValueError(f"{skill_md} frontmatter is not closed")


def _is_marker(line: str) -> bool:
    return line.rstrip() == "---"


def _top_level(lines: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if line[:1].isspace() or line.startswith("#") or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        start = i  # the indented and blank lines that follow belong to this key
        while i < len(lines) and (not lines[i].strip() or lines[i][:1].isspace()):
            i += 1
        out[key] = _scalar(value, lines[start:i])
    return out


def _scalar(value: str, block: list[str]) -> str:
    header = _BLOCK_HEADER.fullmatch(value)
    if header:
        return _block_scalar(header.group(1), header.group(2) or "", block)
    if not value:
        return ""  # a nested mapping or list (e.g. metadata:), not read here
    folded = _fold([value, *(line.strip() for line in block)])
    return folded.strip().strip('"').strip("'")


def _block_scalar(style: str, indicators: str, block: list[str]) -> str:
    texts = [line for line in block if line.strip()]
    if not texts:
        return ""
    digits = [c for c in indicators if c.isdigit()]
    indent = int(digits[0]) if digits else len(texts[0]) - len(texts[0].lstrip())
    lines = [line[min(indent, len(line) - len(line.lstrip())):] if line.strip() else ""
             for line in block]
    return ("\n".join(lines) if style == "|" else _fold(lines)).strip()


def _fold(lines: list[str]) -> str:
    """YAML line folding: a single break between text lines becomes a space, each blank line
    becomes a newline, and breaks next to more-indented lines are kept."""
    out, blanks, prev = "", 0, ""
    for line in lines:
        if not line.strip():
            blanks += 1
            continue
        if out:
            kept = line[0].isspace() or prev[0].isspace()
            out += "\n" * (blanks + kept) if blanks or kept else " "
        out += line
        prev, blanks = line, 0
    return out


def _body(skill_md: Path) -> str:
    """Everything after the frontmatter's closing --- (the whole file if there is none)."""
    text = skill_md.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    lines = text.split("\n")
    if lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if _is_marker(lines[i]):
                return "\n".join(lines[i + 1:]).strip()
    return text


def _content_words(text: str) -> set[str]:
    """Lowercase words of 4+ letters minus stopwords, with a trailing plural or third-person
    "s" dropped so that "symptoms" meets "symptom"."""
    words: set[str] = set()
    for word in _WORD_RE.findall(text.lower()):
        if word in _STOPWORDS:
            continue
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return words


# --- scripts as tools ----------------------------------------------------------------------
@dataclass(frozen=True)
class ScriptTool:
    """Functions of a skill script exposed as a tool: JSON-serializable arguments in and a
    JSON-serializable result out. Call it with keyword arguments: tool(**call.arguments)."""

    name: str
    description: str
    parameters: dict[str, Any]
    run: Callable[[Mapping[str, Any]], Any]

    @property
    def spec(self) -> dict[str, Any]:
        """OpenAI-style function spec, the shape harness/investigator.py sends to the LLM."""
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": copy.deepcopy(self.parameters)}}

    def __call__(self, /, **arguments: Any) -> Any:
        return self.run(arguments)


@dataclass(frozen=True)
class _ScriptBinding:
    script: str  # file stem in scripts/, also the tool name
    description: str
    parameters: dict[str, Any]
    call: Callable[[ModuleType, Mapping[str, Any], Path | None], Any]


def _required_str(args: Mapping[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(args: Mapping[str, Any], key: str) -> str | None:
    return None if args.get(key) is None else _required_str(args, key)


def _symptom_date(args: Mapping[str, Any]) -> date:
    try:
        return date.fromisoformat(_required_str(args, "symptom_date"))
    except ValueError:
        raise ValueError("symptom_date must be a YYYY-MM-DD date") from None


def _window_days(args: Mapping[str, Any]) -> int:
    value = args.get("window_days", 14)  # the scripts' --window default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("window_days must be a whole number of days, 0 or more")
    return value


def _csv_path(args: Mapping[str, Any], data_dir: Path | None) -> str:
    path = Path(_required_str(args, "csv_path"))
    if data_dir is not None:
        root = data_dir.resolve()
        path = (root / path).resolve()
        if root not in path.parents:
            raise ValueError("csv_path must be a file inside the data folder")
    return str(path)


# Each adapter calls the same public functions as the script's own main(), so a tool returns
# exactly what the command line prints with JSON output.
def _timeline_tool(module: ModuleType, args: Mapping[str, Any], data_dir: Path | None) -> Any:
    start = end = None
    if args.get("symptom_date") is not None:
        start, end = module.window_bounds(_symptom_date(args), _window_days(args))
    events = module.load_events(_csv_path(args, data_dir))
    items = module.timeline(events, start, end, _optional_str(args, "field"))
    return [module.to_jsonable(e) for e in items]


def _gaps_tool(module: ModuleType, args: Mapping[str, Any], data_dir: Path | None) -> Any:
    events = module.load_events(_csv_path(args, data_dir))
    return module.find_gaps(events, _symptom_date(args), _window_days(args),
                            _optional_str(args, "field"))


def _compare_tool(module: ModuleType, args: Mapping[str, Any], data_dir: Path | None) -> Any:
    events = module.load_events(_csv_path(args, data_dir))
    return module.compare(events, _required_str(args, "type"), _optional_str(args, "field"))


def _schema(required: list[str], **properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required,
            "additionalProperties": False}


_CSV = {"type": "string",
        "description": "Path to a farm-record CSV (columns in references/event-schema.md)."}
_SYMPTOM = {"type": "string", "description": "Date the symptom was first seen, YYYY-MM-DD."}
_WINDOW = {"type": "integer", "minimum": 0, "default": 14,
           "description": "Days before the symptom date to include."}
_FIELD = {"type": "string", "description": "Only records of this field."}
_TYPE = {"type": "string", "description": "Event type to compare.",
         "enum": ["planting", "irrigation", "fertilizer", "pesticide", "weather", "observation",
                  "harvest", "photo_observation"]}

# Tool bindings per skill, in the order SKILL.md's procedure runs the scripts.
_SCRIPT_BINDINGS: dict[str, tuple[_ScriptBinding, ...]] = {
    "farm-record-investigation": (
        _ScriptBinding(
            "timeline",
            "Dated events from a farm-record CSV in date order (scripts/timeline.py). With "
            "symptom_date, only the window_days before it, both days included. Events with no "
            "date are left out.",
            _schema(["csv_path"], csv_path=_CSV, symptom_date=_SYMPTOM, window_days=_WINDOW,
                    field=_FIELD),
            _timeline_tool),
        _ScriptBinding(
            "gaps",
            "Missing records before a symptom (scripts/gaps.py): tracked record types absent "
            "from the window, the longest stretch without irrigation, events with no quantity "
            "and events with no or unknown date.",
            _schema(["csv_path", "symptom_date"], csv_path=_CSV, symptom_date=_SYMPTOM,
                    window_days=_WINDOW, field=_FIELD),
            _gaps_tool),
        _ScriptBinding(
            "compare",
            "Change versus the previous record of the same type and product, converted to kg, "
            "litre or mm (scripts/compare.py).",
            _schema(["csv_path", "type"], csv_path=_CSV, type=_TYPE, field=_FIELD),
            _compare_tool),
    ),
}


_IMPORT_LOCK = threading.Lock()  # imports save and restore process-wide state


def _import_script(module_name: str, path: Path) -> ModuleType:
    """Import a script by file path and leave the interpreter's import state as it was."""
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path.name}")
    module = importlib.util.module_from_spec(spec)
    with _IMPORT_LOCK:
        saved_path, saved_modules = list(sys.path), set(sys.modules)
        saved_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # keep skill/ clean
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = saved_bytecode
            sys.path[:] = saved_path
            for name in set(sys.modules) - saved_modules:
                origin = getattr(sys.modules.get(name), "__file__", None)
                if origin and Path(origin).resolve().parent == path.parent:
                    del sys.modules[name]
    return module


# --- loader --------------------------------------------------------------------------------
class SkillLoader:
    def __init__(self, root: Path = SKILLS_ROOT) -> None:
        self.root = root
        self.log = DisclosureLog()
        self.skills: dict[str, SkillMeta] = {}
        self._modules: dict[Path, ModuleType] = {}
        for skill_md in sorted(root.glob("*/SKILL.md")):
            try:
                fm = read_frontmatter(skill_md)
            except (OSError, ValueError) as exc:  # UnicodeDecodeError is a ValueError
                log.warning("skipping %s: %s", skill_md, exc)
                continue
            name = fm.get("name", "")
            if name != skill_md.parent.name:
                log.warning("skipping %s: name does not match folder", skill_md)
                continue
            self.skills[name] = SkillMeta(name, fm.get("description", ""), skill_md.parent)
        self.log.record("L1:frontmatter")

    def start_run(self) -> DisclosureLog:
        """Start a run: replace the log with a fresh one holding only L1 (the frontmatter read
        at startup, which every run uses) and return it. Earlier logs are left as they were.
        Without this call the log covers the loader's lifetime. Not for concurrent runs."""
        self.log = DisclosureLog()
        self.log.record("L1:frontmatter")
        return self.log

    def match(self, task: str, min_words: int = MIN_MATCH_WORDS) -> SkillMeta | None:
        """The skill whose description shares the most content words with the task, if it
        shares at least min_words of them, else None. Uses the L1 frontmatter only."""
        words = _content_words(task)
        best, best_score = None, max(min_words, 1) - 1
        for meta in self.skills.values():
            score = len(words & _content_words(meta.description))
            if score > best_score:
                best, best_score = meta, score
        return best

    def load_body(self, meta: SkillMeta) -> str:
        self.log.record(f"L2:body:{meta.name}")
        return _body(meta.path / "SKILL.md")

    def list_references(self, meta: SkillMeta) -> list[str]:
        return sorted(p.name for p in (meta.path / "references").glob("*.md"))

    def read_reference(self, meta: SkillMeta, name: str) -> str:
        """A file in the skill's references/ folder by bare file name, with ".md" optional.
        Paths, relative or absolute, are refused."""
        if not name or name != Path(name).name or any(c in name for c in "/\\\x00"):
            raise FileNotFoundError(f"unknown reference: {name}")
        if not name.endswith(".md"):
            name += ".md"
        ref_dir = (meta.path / "references").resolve()
        target = (ref_dir / name).resolve()
        if target.parent != ref_dir or not target.is_file():
            raise FileNotFoundError(f"unknown reference: {name}")
        self.log.record(f"L3:reference:{name}")
        return target.read_text(encoding="utf-8")

    def load_script(self, meta: SkillMeta, script: str) -> ModuleType:
        """Import scripts/<script>.py, the same file its command line runs.

        Modules are cached per loader, so a script's top level runs once; use is logged as
        "script:<name>" once per run. No sys.path entry is needed afterwards: gaps.py and
        compare.py add their own folder to sys.path to import timeline, which only matters
        while they import, so the loader restores sys.path and drops the bare-name sibling
        modules (the importing script keeps references to what it imported). No bytecode is
        written into the skill folder.
        """
        path = (meta.path / "scripts").resolve() / f"{script}.py"
        if not script.isidentifier() or not path.is_file():
            raise FileNotFoundError(f"unknown script: {script}")
        module = self._modules.get(path)
        if module is None:
            module = _import_script(f"skill_{meta.name.replace('-', '_')}_{script}", path)
            self._modules[path] = module
        if f"script:{script}" not in self.log.levels:
            self.log.record(f"script:{script}")
        return module

    def script_tools(self, meta: SkillMeta, data_dir: Path | None = None) -> dict[str, ScriptTool]:
        """The skill's scripts as tools, keyed by tool name (the script's file stem).

        Nothing is imported until a tool is called; the script then loads through load_script
        (cached and logged). Arguments and results are JSON-serializable and match the
        script's command line. csv_path is read as given; pass data_dir to accept only CSV
        files inside that folder, which is advisable when a model chooses the path.
        """
        tools: dict[str, ScriptTool] = {}
        for binding in _SCRIPT_BINDINGS.get(meta.name, ()):
            if (meta.path / "scripts" / f"{binding.script}.py").is_file():
                run = functools.partial(self._run_script_tool, meta, binding, data_dir)
                tools[binding.script] = ScriptTool(binding.script, binding.description,
                                                   binding.parameters, run)
        return tools

    def script_tool_specs(self, meta: SkillMeta) -> list[dict[str, Any]]:
        """OpenAI-style function specs for script_tools(meta), in the same order."""
        return [tool.spec for tool in self.script_tools(meta).values()]

    def _run_script_tool(self, meta: SkillMeta, binding: _ScriptBinding, data_dir: Path | None,
                         args: Mapping[str, Any]) -> Any:
        unexpected = sorted(set(args) - set(binding.parameters["properties"]))
        if unexpected:
            raise ValueError(f"unexpected arguments: {', '.join(unexpected)}")
        return binding.call(self.load_script(meta, binding.script), args, data_dir)
