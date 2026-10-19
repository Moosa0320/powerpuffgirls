"""Tests for the standalone Agent Skill in skill/farm-record-investigation (guide task 7).

The skill must stay usable without the app, so its stdlib scripts are exercised both as
imported functions and as command-line tools against examples/sample_farm.csv. The sample
has planted signals: urea doubled (E-002 -> E-005), a 10-day irrigation gap before the
2026-03-12 symptom, a spray with no quantity (E-008) and a DAP event with no date (E-010).
No network calls.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import random
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from harness.verifier import BANNED_CLAIMS_FILE, DISCLAIMER, load_banned_patterns

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill" / "farm-record-investigation"
SCRIPTS_DIR = SKILL_DIR / "scripts"
SAMPLE_CSV = SKILL_DIR / "examples" / "sample_farm.csv"
SYMPTOM = date(2026, 3, 12)
BUNDLED_FILES = (
    "references/event-schema.md", "references/investigation-method.md",
    "references/banned-claims.md", "references/question-bank.md",
    "scripts/timeline.py", "scripts/gaps.py", "scripts/compare.py",
    "assets/report-template.md", "examples/sample_farm.csv",
)
# Agent Skills specification (agentskills.io): the only frontmatter keys a skill may use.
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "compatibility", "metadata",
                            "allowed-tools"}
# The line format harness/verifier.py reads from references/banned-claims.md.
VERIFIER_LINE_RE = re.compile(r"^\s*-\s*regex:\s*`(.+)`\s*$")
# Rows of the rewrite table that are treatment advice. The verifier rejects those with its
# separate recommendation check, not with the banned-claims patterns.
TREATMENT_ROWS = {"Spray a fungicide."}

BANNED_EXAMPLES = (
    # English
    "The yellowing is caused by urea.",
    "Urea caused the yellowing.",
    "Urea causes yellowing.",
    "The urea increase led to the yellowing.",
    "The spots resulted from the spray.",
    "The spray is responsible for the spots.",
    "The yellowing is due to excess urea.",
    "The spots appeared because of the spray.",
    "Urea definitely changed the leaf colour.",
    "The spray certainly burned the leaves.",
    "The leaves show a deficiency of nitrogen.",
    "This is nitrogen deficiency.",
    "The crop has blight.",
    "This is a fungal infection.",
    "The plants are infected with a virus.",
    "The cause is excess urea.",
    # Roman Urdu
    "Ye bimari hai.",
    "Fasal ko bimari hai.",
    "Ye bimari fungal infection hai.",
    "Ye urea ki wajah se hua.",
    "Ye dhabbe spray ki wajah se hain.",
    "Pakka paani zyada tha.",
    "Nitrogen ki kami hai.",
    # Urdu script
    "یہ بیماری ہے۔",
    "فصل کو بیماری ہے۔",
    "یہ فنگل انفیکشن ہے۔",
    "یہ یوریا کی وجہ سے ہوا۔",
    "یہ دھبے اسپرے کی وجہ سے ہیں۔",
    "یقیناً پانی زیادہ تھا۔",
    "یقینا پانی زیادہ تھا۔",
    "نائٹروجن کی کمی ہے۔",
)
# Wording the product rules allow ("the records show", "cannot be concluded because records
# are missing"), in all three languages. None of it may be rejected.
ALLOWED_EXAMPLES = (
    "The records show irrigation on 2026-03-08 (E-007).",
    "Nitrogen deficiency cannot be concluded because records are missing.",
    "Nitrogen deficiency cannot be concluded due to missing records.",
    "This cannot be concluded because of gaps in the irrigation records.",
    "The cause cannot be concluded because records are missing.",
    "Possible causes of the yellowing may be worth asking the expert about.",
    "There is no deficiency test in the records.",
    "There is no infection recorded for this field.",
    "The leaves are not infected in the photo.",
    "In the days leading to the symptom, the records show a spray on 2026-03-09 (E-008).",
    "Records mojood na hone ki wajah se ye nateeja nahi nikala ja sakta.",
    "Irrigation ka record mojood nahi.",
    "ریکارڈ موجود نہ ہونے کی وجہ سے یہ نتیجہ نہیں نکالا جا سکتا۔",
    "یقین سے نہیں کہا جا سکتا۔",
)


def _load_script(name: str) -> ModuleType:
    """Import a skill script by file path, the way an agent harness would."""
    spec = importlib.util.spec_from_file_location(f"skill_script_{name}", SCRIPTS_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # keep the skill folder clean
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


timeline_py = _load_script("timeline")
gaps_py = _load_script("gaps")
compare_py = _load_script("compare")


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a skill script as a CLI from the skill folder, decoding its output as UTF-8."""
    result = subprocess.run(
        [sys.executable, f"scripts/{script}", *args], cwd=SKILL_DIR,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, encoding="utf-8", timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    return result


def _event(event_id: str, type_: str, day: date | None, field: str = "North") -> dict[str, Any]:
    return {"event_id": event_id, "field": field, "type": type_, "date": day,
            "date_certainty": "exact" if day else "unknown", "product": None, "quantity": None,
            "unit": None, "symptom": None, "source": "farmer_text"}


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse the flat frontmatter this skill uses: top-level scalars plus one nested mapping.
    Stdlib only; CI also runs the agentskills.io reference validator on the folder."""
    lines = text.split("\n")
    assert lines[0] == "---", "SKILL.md must start with a frontmatter block"
    assert "---" in lines[1:], "frontmatter block is not closed"
    end = lines.index("---", 1)
    data: dict[str, Any] = {}
    parent: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, value = line.strip().partition(":")
        assert sep, f"frontmatter line is not 'key: value': {line!r}"
        value = value.strip()
        if line[0].isspace():
            assert parent is not None, f"indented line outside a mapping: {line!r}"
            data[parent][key] = value
        elif value:
            data[key], parent = value, None
        else:
            data[key], parent = {}, key
    return data, "\n".join(lines[end + 1:])


def _rewrite_table() -> list[tuple[str, str]]:
    """(banned, allowed) rows of the 'Allowed rewrites' table in banned-claims.md."""
    section = BANNED_CLAIMS_FILE.read_text(encoding="utf-8").split("## Allowed rewrites", 1)[1]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("|")]
    return [(banned, allowed) for banned, allowed in rows[2:]]  # skip header and separator


@pytest.fixture(scope="module")
def banned() -> list[re.Pattern[str]]:
    return load_banned_patterns(BANNED_CLAIMS_FILE)


# --- SKILL.md and bundled files ------------------------------------------------------------
def test_frontmatter_follows_agent_skills_spec() -> None:
    meta, body = _frontmatter((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    assert set(meta) <= ALLOWED_FRONTMATTER_KEYS
    assert meta["name"] == SKILL_DIR.name == "farm-record-investigation"
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", meta["name"]) and len(meta["name"]) <= 64
    assert 0 < len(meta["description"]) <= 1024
    assert "never diagnoses" in meta["description"].lower()
    assert meta["license"] == "Apache-2.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["metadata"]["version"])
    assert body.strip()


def test_skill_md_points_to_every_bundled_file() -> None:
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for rel in BUNDLED_FILES:
        assert (SKILL_DIR / rel).is_file(), f"missing {rel}"
        assert rel in text, f"SKILL.md never mentions {rel}, so an agent would not find it"


def test_report_template_has_five_sections_and_ends_with_disclaimer() -> None:
    text = (SKILL_DIR / "assets" / "report-template.md").read_text(encoding="utf-8")
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings == ["What the records show", "What may be worth investigating",
                        "Questions to ask next", "Missing records",
                        "Photo observations (unconfirmed)"]
    assert text.rstrip().endswith(DISCLAIMER)


def test_scripts_import_only_stdlib_and_their_own_folder() -> None:
    allowed = set(sys.stdlib_module_names) | {"__future__", "timeline"}
    for script in sorted(SCRIPTS_DIR.glob("*.py")):
        for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            assert names <= allowed, f"{script.name} imports {sorted(names - allowed)}"


# --- timeline.py ---------------------------------------------------------------------------
def test_timeline_cli_runs_standalone_on_sample() -> None:
    lines = _run("timeline.py", "examples/sample_farm.csv").stdout.splitlines()
    assert [line.split()[1] for line in lines] == [f"E-{i:03d}" for i in range(1, 10)]
    assert lines[0] == "2026-02-01  E-001  planting  tomato  [exact]"
    assert "E-010" not in "\n".join(lines)  # unknown date: cannot be placed on the timeline


def test_timeline_cli_json_window_before_symptom() -> None:
    out = _run("timeline.py", "examples/sample_farm.csv", "--symptom-date", "2026-03-12",
               "--window", "14", "--json").stdout
    items = json.loads(out)
    assert [e["event_id"] for e in items] == ["E-005", "E-006", "E-007", "E-008", "E-009"]
    assert items[0] == {"event_id": "E-005", "field": "North", "type": "fertilizer",
                        "date": "2026-03-05", "date_certainty": "exact", "product": "urea",
                        "quantity": 2.0, "unit": "bori", "symptom": None,
                        "source": "farmer_voice"}


def test_timeline_cli_keeps_urdu_text(tmp_path: Path) -> None:
    csv_path = tmp_path / "urdu.csv"
    csv_path.write_text(
        "event_id,field,type,date,date_certainty,product,quantity,unit,symptom,source\n"
        "E-001,شمالی,observation,2026-03-12,exact,,,,پتے پیلے ہو گئے,farmer_voice\n",
        encoding="utf-8",
    )
    out = _run("timeline.py", str(csv_path), "--field", "شمالی").stdout
    assert 'symptom="پتے پیلے ہو گئے"' in out


def test_timeline_window_is_inclusive_and_skips_undated_events() -> None:
    events = timeline_py.load_events(str(SAMPLE_CSV))
    e010 = next(e for e in events if e["event_id"] == "E-010")
    assert e010["date"] is None and e010["date_certainty"] == "unknown"
    assert "E-010" not in [e["event_id"] for e in timeline_py.timeline(events)]

    def ids(window_days: int) -> list[str]:
        start, end = timeline_py.window_bounds(SYMPTOM, window_days)
        return [e["event_id"] for e in timeline_py.timeline(events, start, end)]

    assert ids(7) == ["E-005", "E-006", "E-007", "E-008", "E-009"]  # E-005 is on the start day
    assert ids(6) == ["E-006", "E-007", "E-008", "E-009"]
    assert ids(0) == ["E-009"]
    assert timeline_py.timeline(events, field="South") == []


def test_timeline_returns_exactly_the_dated_events_in_window_sorted() -> None:
    """Seeded random inputs (stdlib only): every dated event inside [start, end] is returned,
    nothing else, sorted by date then ID."""
    rng = random.Random(20260312)
    base = date(2026, 1, 1)
    for _ in range(300):
        events = [
            _event(f"E-{n:03d}", rng.choice(["irrigation", "fertilizer", "weather"]),
                   None if rng.random() < 0.2 else base + timedelta(days=rng.randrange(60)))
            for n in rng.sample(range(1, 200), rng.randrange(25))
        ]
        end = base + timedelta(days=rng.randrange(60))
        start = end - timedelta(days=rng.choice([0, 7, 14, 30]))
        result = timeline_py.timeline(events, start, end)
        expected = {e["event_id"] for e in events
                    if e["date"] is not None and start <= e["date"] <= end}
        assert {e["event_id"] for e in result} == expected
        assert result == sorted(result, key=lambda e: (e["date"], e["event_id"]))


# --- gaps.py -------------------------------------------------------------------------------
def test_gaps_cli_finds_planted_gaps() -> None:
    report = json.loads(_run("gaps.py", "examples/sample_farm.csv",
                             "--symptom-date", "2026-03-12").stdout)
    assert report["window"] == {"start": "2026-02-26", "end": "2026-03-12", "days": 14}
    assert report["longest_irrigation_gap_days"] == 10  # window start -> E-007 on 2026-03-08
    assert report["null_quantity_events"] == ["E-008"]  # spray with no quantity
    assert report["unknown_date_events"] == ["E-010"]  # DAP with no date
    assert report["missing_types"] == []


def test_gaps_short_window_lists_missing_record_types() -> None:
    events = timeline_py.load_events(str(SAMPLE_CSV))
    report = gaps_py.find_gaps(events, SYMPTOM, window_days=3)
    assert report["missing_types"] == ["irrigation", "fertilizer", "weather"]
    assert report["longest_irrigation_gap_days"] == 3
    assert report["null_quantity_events"] == ["E-008"]


# --- compare.py ----------------------------------------------------------------------------
def test_compare_cli_finds_urea_doubling() -> None:
    rows = json.loads(_run("compare.py", "examples/sample_farm.csv",
                           "--type", "fertilizer").stdout)
    # 1 bori -> 2 bori, normalized to kg. The undated DAP record (E-010) is never compared.
    assert rows == [{"event_id": "E-005", "previous_event_id": "E-002", "product": "urea",
                     "previous_value": 50.0, "current_value": 100.0, "unit": "kg",
                     "percent_change": 100.0}]


# --- references/banned-claims.md -----------------------------------------------------------
def test_banned_claims_lines_use_the_verifier_format_and_compile() -> None:
    lines = [line for line in BANNED_CLAIMS_FILE.read_text(encoding="utf-8").splitlines()
             if line.lstrip().startswith("- regex")]
    sources: list[str] = []
    for line in lines:
        match = VERIFIER_LINE_RE.match(line)
        assert match, f"harness/verifier.py would skip this line: {line!r}"
        sources.append(match.group(1))
    for source in sources:
        try:
            re.compile(source, re.I)
        except re.error as exc:
            pytest.fail(f"banned pattern {source!r} does not compile: {exc}")
    assert len(sources) >= 15
    # Loaded from the file, not the verifier's built-in fallback list.
    assert [p.pattern for p in load_banned_patterns(BANNED_CLAIMS_FILE)] == sources


def test_every_banned_pattern_catches_an_intended_example(banned: list[re.Pattern[str]]) -> None:
    for text in BANNED_EXAMPLES:
        assert any(p.search(text) for p in banned), f"no banned pattern rejects {text!r}"
    for pattern in banned:
        assert any(pattern.search(text) for text in BANNED_EXAMPLES), \
            f"no example exercises /{pattern.pattern}/"


def test_rewrite_table_banned_rows_are_caught(banned: list[re.Pattern[str]]) -> None:
    rows = _rewrite_table()
    assert len(rows) >= 4
    for banned_text, _ in rows:
        if banned_text not in TREATMENT_ROWS:
            assert any(p.search(banned_text) for p in banned), \
                f"table lists {banned_text!r} as banned but no pattern rejects it"


def test_allowed_wording_is_never_rejected(banned: list[re.Pattern[str]]) -> None:
    for text in [allowed for _, allowed in _rewrite_table()] + list(ALLOWED_EXAMPLES):
        hits = [p.pattern for p in banned if p.search(text)]
        assert not hits, f"allowed wording {text!r} is rejected by {hits}"
