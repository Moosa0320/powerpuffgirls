"""Tests for the progressive-disclosure skill loader (guide 7.2, requirement 8).

Level 1 at startup is frontmatter only, level 2 (the SKILL.md body) loads on request and level 3
(references) loads only through read_reference. Scripts are exposed as tools that return what
their command lines print, and the disclosure log can be reset per run. Edge cases use tmp_path
skill roots. No network calls.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.backend.models import Farm, Field
from harness import skill_loader
from harness.investigator import TOOL_SPECS, Investigator
from harness.llm.base import LLMReply, ToolCall
from harness.providers.fakes import FakeLLM
from harness.skill_loader import SkillLoader, SkillMeta, read_frontmatter

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "farm-record-investigation"
SKILL_DIR = ROOT / "skill" / SKILL_NAME
SCRIPTS_DIR = SKILL_DIR / "scripts"
SAMPLE_CSV = SKILL_DIR / "examples" / "sample_farm.csv"
SAMPLE = "examples/sample_farm.csv"  # relative to SKILL_DIR, for the command-line runs
L1 = "L1:frontmatter"
L2 = f"L2:body:{SKILL_NAME}"
REFERENCES = ["banned-claims.md", "event-schema.md", "investigation-method.md", "question-bank.md"]


def _write_skill(root: Path, folder: str, content: str | bytes) -> Path:
    path = root / folder / "SKILL.md"
    path.parent.mkdir(parents=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def _skill(name: str, description: str, body: str = "# Body\n") -> str:
    return f"---\nname: {name}\ndescription: {description}\n---\n{body}"


def _cli(script: str, *args: str) -> Any:
    """Run a skill script from the command line, as an agent without the app would."""
    result = subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=SKILL_DIR,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, encoding="utf-8", timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture()
def loader() -> SkillLoader:
    return SkillLoader()


@pytest.fixture()
def meta(loader: SkillLoader) -> SkillMeta:
    return loader.skills[SKILL_NAME]


@pytest.fixture()
def read_spy(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Every Path.read_text call in the test. The loader reads bodies and references with it."""
    reads: list[Path] = []
    real_read_text = Path.read_text

    def spy(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(self)
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    return reads


# --- L1: startup reads frontmatter only ----------------------------------------------------
def test_startup_reads_only_frontmatter(
    monkeypatch: pytest.MonkeyPatch, read_spy: list[Path]
) -> None:
    body_calls: list[Path] = []
    real_body = skill_loader._body

    def spy_body(skill_md: Path) -> str:
        body_calls.append(skill_md)
        return real_body(skill_md)

    monkeypatch.setattr(skill_loader, "_body", spy_body)
    loader = SkillLoader()
    assert body_calls == [] and read_spy == []  # no body, reference or script was read
    assert loader.log.levels == [L1]
    meta = loader.skills[SKILL_NAME]
    assert meta.path == SKILL_DIR
    assert "never diagnoses" in meta.description.lower()
    loader.load_body(meta)
    assert body_calls == [SKILL_DIR / "SKILL.md"]


def test_frontmatter_read_stops_at_the_closing_marker(tmp_path: Path) -> None:
    _write_skill(tmp_path, "alpha", _skill("alpha", "From the frontmatter.",
                                           body="name: beta\ndescription: From the body.\n"))
    assert SkillLoader(tmp_path).skills["alpha"].description == "From the frontmatter."


def test_name_folder_mismatch_is_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _write_skill(tmp_path, "alpha", _skill("alpha", "Good skill."))
    _write_skill(tmp_path, "beta", _skill("gamma", "Name differs from its folder."))
    with caplog.at_level(logging.WARNING, logger="fasalnama.skills"):
        loader = SkillLoader(tmp_path)
    assert list(loader.skills) == ["alpha"]
    assert "does not match folder" in caplog.text


def test_broken_frontmatter_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_skill(tmp_path, "alpha", _skill("alpha", "Good skill."))
    _write_skill(tmp_path, "no-frontmatter", "# Just a heading\n")
    _write_skill(tmp_path, "unclosed", "---\nname: unclosed\ndescription: Never closed.\n")
    _write_skill(tmp_path, "not-utf8", b"---\nname: not-utf8\ndescription: \xff\n---\n")
    with caplog.at_level(logging.WARNING, logger="fasalnama.skills"):
        loader = SkillLoader(tmp_path)
    assert list(loader.skills) == ["alpha"]
    assert loader.log.levels == [L1]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    for folder in ("no-frontmatter", "unclosed", "not-utf8"):
        assert any(folder in message for message in warnings), folder


def test_frontmatter_with_a_utf8_bom_is_read(tmp_path: Path) -> None:
    content = "\ufeff" + _skill("alpha", "Saved on Windows.")
    _write_skill(tmp_path, "alpha", content.encode("utf-8"))
    assert SkillLoader(tmp_path).skills["alpha"].description == "Saved on Windows."


@pytest.mark.parametrize(("lines", "expected"), [
    (["description: >", "  Builds a timeline", "  of farm events.", "", "  Never diagnoses."],
     "Builds a timeline of farm events.\nNever diagnoses."),
    (["description: >-", "  Folded, with a", "  chomping indicator."],
     "Folded, with a chomping indicator."),
    (["description: |", "  Line one", "  Line two"], "Line one\nLine two"),
    (["description: |+", "  Kept as written.", ""], "Kept as written."),
    (["description: Plain text that", "  continues here."], "Plain text that continues here."),
    (['description: "Quoted text."'], "Quoted text."),
])
def test_frontmatter_scalars(tmp_path: Path, lines: list[str], expected: str) -> None:
    path = tmp_path / "SKILL.md"
    path.write_text("\n".join(["---", "name: alpha", *lines, "metadata:", "  name: nested", "---",
                               "# Body"]) + "\n", encoding="utf-8")
    front = read_frontmatter(path)
    assert front["description"] == expected
    assert front["name"] == "alpha"  # keys nested under metadata never replace top-level ones


# --- matching a task to a skill ------------------------------------------------------------
@pytest.mark.parametrize("task", [
    "what changed in my field before the yellow leaves symptom",
    "prepare a timeline for the agricultural expert visit",
    "show the timeline of events before the symptoms appeared",
])
def test_match_finds_the_skill_for_farm_tasks(loader: SkillLoader, task: str) -> None:
    assert loader.match(task) is loader.skills[SKILL_NAME]
    assert loader.log.levels == [L1]  # matching uses the frontmatter only


@pytest.mark.parametrize("task", [
    "what time is it",  # shares only the stopword "what"
    "write a poem",
    "investigate why my code crashed",  # one shared word is not enough
    "",
])
def test_match_rejects_unrelated_tasks(loader: SkillLoader, task: str) -> None:
    assert loader.match(task) is None


# --- L2: body ------------------------------------------------------------------------------
def test_body_loads_only_on_request_and_is_logged_as_l2(
    loader: SkillLoader, meta: SkillMeta
) -> None:
    assert loader.log.levels == [L1]
    body = loader.load_body(meta)
    assert loader.log.levels == [L1, L2]
    assert body.startswith("# Farm Record Investigation")
    assert "name: farm-record-investigation" not in body  # the frontmatter is not repeated
    assert "references/banned-claims.md" in body  # the body says which reference to read
    assert "regex:" not in body  # but does not inline it


# --- L3: references ------------------------------------------------------------------------
def test_references_load_only_through_read_reference(
    read_spy: list[Path], loader: SkillLoader, meta: SkillMeta
) -> None:
    loader.load_body(meta)
    assert loader.list_references(meta) == REFERENCES
    assert [p for p in read_spy if p.parent.name == "references"] == []
    banned = loader.read_reference(meta, "banned-claims")  # ".md" is optional
    assert banned == (SKILL_DIR / "references" / "banned-claims.md").read_text(encoding="utf-8")
    assert loader.read_reference(meta, "event-schema.md").startswith("# Event schema")
    assert loader.log.levels == [L1, L2, "L3:reference:banned-claims.md",
                                 "L3:reference:event-schema.md"]


@pytest.mark.parametrize("name", [
    "missing", "missing.md", "", "../SKILL.md", "../SKILL", "..\\SKILL.md", "../../README.md",
    "references/banned-claims.md",
    str(SKILL_DIR / "SKILL.md"),
    str(SKILL_DIR / "references" / "banned-claims.md"),  # absolute paths are refused outright
])
def test_read_reference_rejects_unknown_names_and_paths(
    loader: SkillLoader, meta: SkillMeta, name: str
) -> None:
    with pytest.raises(FileNotFoundError):
        loader.read_reference(meta, name)
    assert loader.log.levels == [L1]  # a refused read is not logged as L3


# --- scripts as tools ----------------------------------------------------------------------
def test_script_tools_return_what_the_scripts_print(loader: SkillLoader, meta: SkillMeta) -> None:
    tools = loader.script_tools(meta)
    assert list(tools) == ["timeline", "gaps", "compare"]
    assert loader.log.levels == [L1]  # describing the tools imports nothing
    csv_path = str(SAMPLE_CSV)
    window = tools["timeline"](csv_path=csv_path, symptom_date="2026-03-12", window_days=14)
    everything = tools["timeline"](csv_path=csv_path)
    gaps = tools["gaps"](csv_path=csv_path, symptom_date="2026-03-12")
    changes = tools["compare"](csv_path=csv_path, type="fertilizer")
    # JSON in, JSON out: each result survives a JSON round trip and equals the CLI's output.
    for result, cli_args in (
        (window, ("timeline.py", SAMPLE, "--symptom-date", "2026-03-12", "--window", "14",
                  "--json")),
        (everything, ("timeline.py", SAMPLE, "--json")),
        (gaps, ("gaps.py", SAMPLE, "--symptom-date", "2026-03-12")),
        (changes, ("compare.py", SAMPLE, "--type", "fertilizer")),
    ):
        assert json.loads(json.dumps(result)) == result == _cli(*cli_args), cli_args
    # The signals planted in the sample farm.
    assert [e["event_id"] for e in window] == ["E-005", "E-006", "E-007", "E-008", "E-009"]
    assert changes == [{"event_id": "E-005", "previous_event_id": "E-002", "product": "urea",
                        "previous_value": 50.0, "current_value": 100.0, "unit": "kg",
                        "percent_change": 100.0}]
    assert gaps["longest_irrigation_gap_days"] == 10
    assert gaps["null_quantity_events"] == ["E-008"]
    assert gaps["unknown_date_events"] == ["E-010"]
    assert loader.log.levels == [L1, "script:timeline", "script:gaps", "script:compare"]


def test_script_tool_specs_are_openai_function_specs(loader: SkillLoader, meta: SkillMeta) -> None:
    specs = loader.script_tool_specs(meta)
    assert specs == [tool.spec for tool in loader.script_tools(meta).values()]
    assert [s["function"]["name"] for s in specs] == ["timeline", "gaps", "compare"]
    for spec in specs:
        assert spec["type"] == "function" and spec["function"]["description"]
        params = spec["function"]["parameters"]
        assert params["type"] == "object" and "csv_path" in params["required"]
        assert set(params["required"]) <= set(params["properties"])
    json.dumps(specs)  # sent to a provider as JSON
    # The names can sit next to the investigator's database tools without clashing.
    assert {s["function"]["name"] for s in specs}.isdisjoint(
        {s["function"]["name"] for s in TOOL_SPECS})


def test_script_tools_reject_bad_arguments(loader: SkillLoader, meta: SkillMeta) -> None:
    gaps = loader.script_tools(meta)["gaps"]
    csv_path = str(SAMPLE_CSV)
    for bad in (
        {"csv_path": csv_path},  # gaps needs a symptom date
        {"symptom_date": "2026-03-12"},
        {"csv_path": csv_path, "symptom_date": "12/03/2026"},
        {"csv_path": csv_path, "symptom_date": "2026-03-12", "window_days": -1},
        {"csv_path": csv_path, "symptom_date": "2026-03-12", "window_days": "14"},
        {"csv_path": csv_path, "symptom_date": "2026-03-12", "days": 14},
    ):
        with pytest.raises(ValueError):
            gaps(**bad)
    for script in ("missing", "../SKILL", "scripts/gaps"):
        with pytest.raises(FileNotFoundError):
            loader.load_script(meta, script)


def test_script_tools_can_confine_csv_paths_to_a_folder(
    loader: SkillLoader, meta: SkillMeta
) -> None:
    tools = loader.script_tools(meta, data_dir=SAMPLE_CSV.parent)
    report = tools["gaps"](csv_path="sample_farm.csv", symptom_date="2026-03-12")
    assert report["unknown_date_events"] == ["E-010"]
    for outside in ("../SKILL.md", str(SKILL_DIR / "SKILL.md")):
        with pytest.raises(ValueError):
            tools["timeline"](csv_path=outside)


def test_load_script_is_cached_and_leaves_import_state_alone(
    loader: SkillLoader, meta: SkillMeta
) -> None:
    def skill_files() -> dict[Path, int]:
        return {p: p.stat().st_mtime_ns for p in SKILL_DIR.rglob("*")}

    path_before = list(sys.path)
    timeline_before = sys.modules.get("timeline")
    files_before = skill_files()
    gaps = loader.load_script(meta, "gaps")  # gaps.py adds its folder to sys.path for timeline
    assert loader.load_script(meta, "gaps") is gaps  # cached, not executed again
    assert loader.log.levels == [L1, "script:gaps"]  # and logged once
    assert sys.path == path_before
    assert sys.modules.get("timeline") is timeline_before
    assert skill_files() == files_before  # no bytecode or other file written into the skill
    report = gaps.find_gaps(gaps.load_events(str(SAMPLE_CSV)), date(2026, 3, 12))
    assert report["null_quantity_events"] == ["E-008"]


# --- per-run disclosure log ----------------------------------------------------------------
def test_start_run_gives_each_run_its_own_log(loader: SkillLoader, meta: SkillMeta) -> None:
    loader.load_body(meta)
    loader.read_reference(meta, "banned-claims")
    loader.load_script(meta, "gaps")
    first = loader.log
    first_levels = [L1, L2, "L3:reference:banned-claims.md", "script:gaps"]
    assert first.levels == first_levels  # without start_run the log keeps growing, as before
    assert first.deepest_level == "L3"

    second = loader.start_run()
    assert second is loader.log and second is not first
    assert second.levels == [L1] and second.deepest_level == "L1"
    assert first.levels == first_levels  # the previous run's log is kept as it was
    loader.load_body(meta)
    assert second.deepest_level == "L2"
    loader.load_script(meta, "gaps")  # cached module, but logged again for the new run
    assert second.levels == [L1, L2, "script:gaps"]
    assert second.deepest_level == "L3"


# --- the real skill and the investigator's calls -------------------------------------------
def test_investigator_calls_work_with_the_real_skill(session: Session) -> None:
    farm = Farm(name="Test farm")
    field = Field(farm=farm, name="North")
    session.add_all([farm, field])
    session.commit()
    read = ToolCall("read_reference", {"name": "banned-claims"}, id="call-1")
    llm = FakeLLM([LLMReply(tool_calls=[read])])  # one tool call, then no replies left
    loader = SkillLoader()
    outcome = Investigator(session, llm, loader).run(field.id, date(2026, 3, 12))

    assert outcome.model_info["disclosure"] == [L1, L2, "L3:reference:banned-claims.md"]
    system = llm.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert system["content"].startswith("# Farm Record Investigation")  # body in the system prompt
    tool_message = llm.calls[1]["messages"][-1]
    assert tool_message["role"] == "tool"
    assert "regex:" in json.loads(tool_message["content"])["content"]
