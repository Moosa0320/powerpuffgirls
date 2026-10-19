"""Unit tests for the report verifier (guide task 10 & section 7.6).

Tests prove that:
- a diagnosis sentence is rejected
- an uncited fact is rejected
- a fake event ID is rejected
- valid evidence-cited reports pass
- diagnosis, cause-as-fact wording and treatment or dosage advice are rejected in every claim
  type, in English, Roman Urdu and Urdu script, while the allowed wording still passes
- DEFAULT_BANNED is a copy of the skill's banned-claims.md, used with a warning as a fallback
"""
import logging
import re
from datetime import date
from pathlib import Path

import pytest

from harness.engine import TimelineItem, GapReport
from harness.verifier import (
    BANNED_CLAIMS_FILE,
    DEFAULT_BANNED,
    DISCLAIMER,
    NONFACT_RECOMMENDATION_PATTERNS,
    RECOMMENDATION_PATTERNS,
    SECTIONS,
    SKILL_DIR,
    Evidence,
    EventFact,
    load_banned_patterns,
    safe_template_report,
    verify_report,
)


def _sample_evidence(gaps_found: bool = False) -> Evidence:
    events = {
        "E-001": EventFact("E-001", date(2026, 2, 1), "planting", "tomato"),
        "E-002": EventFact("E-002", date(2026, 2, 20), "fertilizer", "urea", 2.0, "bori"),
        "E-003": EventFact("E-003", date(2026, 2, 22), "irrigation", None, 1.0, "tanki"),
    }
    photos = {"P-001": True, "P-002": False}
    return Evidence(
        events=events,
        photos=photos,
        gaps_found=gaps_found,
        symptom_date=date(2026, 2, 25),
    )


def test_verifier_rejects_fake_event_id() -> None:
    ev = _sample_evidence()
    report = {
        "sections": {
            "records_show": [
                {"text": "Applied fertilizer on 2026-02-20", "type": "fact", "event_ids": ["E-999"], "photo_ids": []}
            ],
            "worth_investigating": [],
            "questions_next": [],
            "missing_records": [],
            "photo_observations": [],
        },
        "disclaimer": DISCLAIMER,
    }
    res = verify_report(report, ev)
    assert not res.ok
    assert any("cited event E-999 does not exist" in err for err in res.errors)


def test_verifier_rejects_uncited_fact() -> None:
    ev = _sample_evidence()
    report = {
        "sections": {
            "records_show": [
                {"text": "Farmer irrigated the field", "type": "fact", "event_ids": [], "photo_ids": []}
            ],
            "worth_investigating": [],
            "questions_next": [],
            "missing_records": [],
            "photo_observations": [],
        },
        "disclaimer": DISCLAIMER,
    }
    res = verify_report(report, ev)
    assert not res.ok
    assert any("fact has no citation" in err for err in res.errors)


def test_verifier_rejects_diagnosis_sentence() -> None:
    ev = _sample_evidence()
    # Diagnosis phrases in English, Roman Urdu and Urdu script
    for bad_claim in [
        "The yellowing is caused by nitrogen deficiency",
        "The crop is suffering from early blight fungus",
        "Ye bimari fungal infection hai",
        "Definitely a virus problem",
        "This is a fungal infection.",
        "Urea caused the yellowing.",
        "یہ فنگل انفیکشن ہے۔",
        "یہ بیماری ہے۔",
    ]:
        report = {
            "sections": {
                "records_show": [],
                "worth_investigating": [
                    {"text": bad_claim, "type": "possibility", "event_ids": [], "photo_ids": []}
                ],
                "questions_next": [],
                "missing_records": [],
                "photo_observations": [],
            },
            "disclaimer": DISCLAIMER,
        }
        res = verify_report(report, ev)
        assert not res.ok, f"Expected rejection for: {bad_claim}"
        assert any("diagnosis or cause-as-fact wording" in err for err in res.errors)


def test_verifier_rejects_dosage_recommendation() -> None:
    ev = _sample_evidence()
    report = {
        "sections": {
            "records_show": [],
            "worth_investigating": [
                {"text": "Please spray 50 ml per acre pesticide", "type": "possibility", "event_ids": [], "photo_ids": []}
            ],
            "questions_next": [],
            "missing_records": [],
            "photo_observations": [],
        },
        "disclaimer": DISCLAIMER,
    }
    res = verify_report(report, ev)
    assert not res.ok
    assert any("treatment or dosage recommendation" in err for err in res.errors)


def test_verifier_accepts_valid_evidence_cited_report() -> None:
    ev = _sample_evidence(gaps_found=False)
    report = {
        "sections": {
            "records_show": [
                {"text": "On 2026-02-20, applied 2 bori urea", "type": "fact", "event_ids": ["E-002"], "photo_ids": []}
            ],
            "worth_investigating": [
                {"text": "Water schedule change may be worth investigating with an agronomist", "type": "possibility", "event_ids": [], "photo_ids": []}
            ],
            "questions_next": [
                {"text": "Has rainfall occurred nearby recently?", "type": "question", "event_ids": [], "photo_ids": []}
            ],
            "missing_records": [],
            "photo_observations": [
                {"text": "Photo P-001 shows leaf appearance", "type": "fact", "event_ids": [], "photo_ids": ["P-001"]}
            ],
        },
        "disclaimer": DISCLAIMER,
    }
    res = verify_report(report, ev)
    assert res.ok
    assert len(res.errors) == 0


def test_safe_template_report_fallback() -> None:
    timeline = [
        TimelineItem(kind="event", display_id="E-001", occurred_at=date(2026, 2, 1), type="planting", product="tomato"),
        TimelineItem(kind="event", display_id="E-002", occurred_at=date(2026, 2, 20), type="fertilizer", product="urea", quantity=2.0, unit="bori"),
    ]
    gaps = GapReport(missing_irrigation=True, null_quantity_events=["E-001"])
    fallback = safe_template_report(timeline, gaps, window_days=14)

    assert fallback["disclaimer"] == DISCLAIMER
    assert len(fallback["sections"]["records_show"]) == 2
    assert len(fallback["sections"]["missing_records"]) >= 1

    ev = _sample_evidence(gaps_found=True)
    res = verify_report(fallback, ev)
    assert res.ok


# --- Banned wording and treatment advice (task 10.1, requirement 10.3) --------------------
DIAGNOSIS = "diagnosis or cause-as-fact wording"
TREATMENT = "treatment or dosage recommendation"
CLAIM_SECTION = {"fact": "records_show", "possibility": "worth_investigating",
                 "question": "questions_next"}
_EVENT_ID_RE = re.compile(r"\bE-\d{3}\b")
_BANNED_LINE_RE = re.compile(r"^\s*-\s*regex:\s*`(.+)`\s*$")  # the format the verifier reads

# Diagnosis and cause-as-fact wording. The verifier rejects it whatever the claim type.
CAUSE_AND_DIAGNOSIS = [
    # English
    "This is a fungal infection.",
    "The plants have a fungal disease.",
    "The crop is infected.",
    "Urea caused the yellowing.",
    "Urea causes yellowing.",
    "The spray is causing the spots.",
    "The urea increase led to the yellowing.",
    "The spots resulted from the spray.",
    "The spray is responsible for the spots.",
    "The yellowing is due to excess urea.",
    "The spots appeared because of the spray.",
    "The wilting is due to missing irrigation.",  # skipped watering, not a missing record
    # Roman Urdu
    "Ye fungal infection hai.",
    "Ye urea ki wajah se hua.",
    "Fasal ko bimari hai.",
    # Urdu script
    "یہ فنگل انفیکشن ہے۔",
    "یہ یوریا کی وجہ سے ہوا۔",
    "فصل کو بیماری ہے۔",
]
# Treatment and dosage advice. Rejected whatever the claim type, including a "fact" that cites
# an event. Every pattern in RECOMMENDATION_PATTERNS must be exercised by one of these.
TREATMENT_ADVICE = [
    # English
    "Use mancozeb.",
    "Try spraying neem oil.",
    "Consider applying a fungicide.",
    "Spray a fungicide.",
    "If spots spread, spray mancozeb.",
    "Apply 2 bori urea again (E-005).",
    "Please spray 50 ml per acre pesticide.",
    "Drench the soil with fungicide.",
    "The field should be sprayed again.",
    "We recommend a fungicide.",
    "I recommend spraying.",
    "A fungicide spray is recommended.",
    "Spraying is strongly recommended.",
    "We recommend a fungicide before any spray.",
    "It is better to spray in the evening.",
    "A fungicide could be applied.",
    "A fungicide spray may be worth trying.",
    "Double the urea dose.",
    # Roman Urdu
    "Spray kar dein.",
    "Dawai daal do.",
    "Agar dhabbe barhein to spray karein.",
    "Mancozeb ka istemal karein.",
    "Spray karna chahiye.",
    "Urea ki dose kam karein.",
    # Urdu script
    "اسپرے کر دیں۔",
    "چھڑکاؤ کریں۔",
    "دوائی ڈالیں۔",
    "مینکوزیب استعمال کریں۔",
    "اسپرے کرنا چاہیے۔",
    "فنگی سائیڈ چھڑکیں۔",
    "کھاد کم کریں۔",
]
# Dose rates. Rejected in possibilities and questions; a fact may quote a recorded dose.
# Every pattern in NONFACT_RECOMMENDATION_PATTERNS must be exercised by one of these.
DOSE_RATES = [
    "50 ml per acre may be worth asking about.",
    "2 bori fi acre may be worth asking about.",
    "۵۰ ملی لیٹر فی ایکڑ کے بارے میں پوچھنا بہتر ہے۔",
]
# Wording the product rules allow. None of it may be rejected, as a fact or a possibility.
ALLOWED_STATEMENTS = [
    # Records, missing records and possibilities
    "The records show irrigation on 2026-03-08 (E-007).",
    "The urea increase from 1 bori to 2 bori (E-002, E-005) may be worth investigating.",
    "Nitrogen deficiency cannot be concluded because records are missing.",
    "Nitrogen deficiency cannot be concluded due to missing records.",
    "This cannot be concluded because of gaps in the irrigation records.",
    "The cause cannot be concluded because records are missing.",
    "Possible causes of the yellowing may be worth asking the expert about.",
    "There is no infection recorded for this field.",
    "In the days leading to the symptom, the records show a spray on 2026-03-09 (E-008).",
    "Records mojood na hone ki wajah se ye nateeja nahi nikala ja sakta.",
    "Irrigation ka record mojood nahi.",
    "ریکارڈ موجود نہ ہونے کی وجہ سے یہ نتیجہ نہیں نکالا جا سکتا۔",
    "ریکارڈ موجود نہیں۔",
    # Treatment words used as nouns or for recorded events, not as advice
    "Ask an agricultural expert before any spray.",
    "An agricultural expert visit is recommended before any spray.",
    "Spray records are missing and an expert visit is recommended.",
    "The records show 2 bori urea on 2026-03-05 (E-005).",
    "A spray was recorded on 2026-03-09 (E-008).",
    "spray kiya gaya (E-008)",
    "Use of urea was recorded (E-005).",
    "Spray quantity was not recorded (E-008).",
    "Spray and irrigation records are missing.",
    "The pesticide spray on 2026-03-09 (E-008) may be worth investigating.",
    "Add the missing quantity for E-008 to the records.",
    "Spray ke baad dhabbe aaye (E-008).",
    "spray karne ke baad dhabbe aaye (E-008)",
    "اسپرے سے پہلے ماہر سے پوچھیں۔",
    "ریکارڈ کے مطابق 2026-03-09 کو اسپرے کیا گیا (E-008)۔",
    "اسپرے کروایا گیا (E-008)۔",
]
ALLOWED_QUESTIONS = [
    "Which pesticide was used in the spray on 2026-03-09 (E-008)?",
    "Was a pesticide spray done before the spots appeared?",
    "Could spray drift from a neighbouring field explain the spots?",
    "Has the symptom spread to other plants or fields since it was first seen?",
]


def _sample_farm_evidence() -> Evidence:
    """Events from the skill's examples/sample_farm.csv, plus E-011, a recorded mancozeb dose."""
    events = {
        "E-002": EventFact("E-002", date(2026, 2, 20), "fertilizer", "urea", 1.0, "bori"),
        "E-005": EventFact("E-005", date(2026, 3, 5), "fertilizer", "urea", 2.0, "bori"),
        "E-006": EventFact("E-006", date(2026, 3, 6), "weather", "rainfall", 45.0, "mm"),
        "E-007": EventFact("E-007", date(2026, 3, 8), "irrigation", None, 1.0, "tanki"),
        "E-008": EventFact("E-008", date(2026, 3, 9), "pesticide", "spray"),
        "E-011": EventFact("E-011", date(2026, 3, 10), "pesticide", "mancozeb", 50.0, "ml"),
    }
    return Evidence(events=events, photos={}, gaps_found=False, symptom_date=date(2026, 3, 12))


def _claim_errors(text: str, ctype: str) -> list[str]:
    """Verifier errors for a report that holds one claim, in the section for its type. The claim
    cites every event ID its text mentions (a fact that mentions none cites E-008), so only the
    wording can fail."""
    event_ids = _EVENT_ID_RE.findall(text) or (["E-008"] if ctype == "fact" else [])
    sections: dict[str, list[dict[str, object]]] = {name: [] for name in SECTIONS}
    sections[CLAIM_SECTION[ctype]].append(
        {"text": text, "type": ctype, "event_ids": event_ids, "photo_ids": []})
    report = {"sections": sections, "disclaimer": DISCLAIMER}
    return verify_report(report, _sample_farm_evidence()).errors


def _rewrite_rows() -> list[tuple[str, str]]:
    """(banned, allowed) rows of the 'Allowed rewrites' table in banned-claims.md."""
    section = BANNED_CLAIMS_FILE.read_text(encoding="utf-8").split("## Allowed rewrites", 1)[1]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("|")]
    return [(row[0], row[1]) for row in rows[2:]]  # skip header and separator


@pytest.mark.parametrize("text", CAUSE_AND_DIAGNOSIS)
def test_diagnosis_and_cause_wording_is_rejected_in_every_claim_type(text: str) -> None:
    for ctype in CLAIM_SECTION:
        errors = _claim_errors(text, ctype)
        assert any(DIAGNOSIS in e for e in errors), f"{ctype} {text!r} passed: {errors}"


@pytest.mark.parametrize("text", TREATMENT_ADVICE)
def test_treatment_advice_is_rejected_in_every_claim_type(text: str) -> None:
    for ctype in CLAIM_SECTION:
        errors = _claim_errors(text, ctype)
        assert any(TREATMENT in e for e in errors), f"{ctype} {text!r} passed: {errors}"


@pytest.mark.parametrize("text", DOSE_RATES)
def test_dose_rates_are_rejected_in_possibilities_and_questions(text: str) -> None:
    for ctype in ("possibility", "question"):
        errors = _claim_errors(text, ctype)
        assert any(TREATMENT in e for e in errors), f"{ctype} {text!r} passed: {errors}"


@pytest.mark.parametrize("text", [
    "The records show 2 bori urea on 2026-03-05 (E-005).",
    "The records show 50 ml mancozeb per tanki on 2026-03-10 (E-011).",
    "ریکارڈ کے مطابق 2026-03-10 کو 50 ml مینکوزیب فی ٹینکی ڈالی گئی (E-011)۔",
])
def test_recorded_dose_quoted_in_a_fact_passes(text: str) -> None:
    assert _claim_errors(text, "fact") == []


@pytest.mark.parametrize("text", ALLOWED_STATEMENTS)
def test_allowed_wording_passes_as_fact_and_possibility(text: str) -> None:
    for ctype in ("fact", "possibility"):
        assert _claim_errors(text, ctype) == [], f"{ctype} {text!r} was rejected"


def test_allowed_questions_and_question_bank_pass() -> None:
    bank = (SKILL_DIR / "references" / "question-bank.md").read_text(encoding="utf-8")
    questions = [line[2:].strip() for line in bank.splitlines() if line.startswith("- ")]
    assert len(questions) >= 10
    for text in ALLOWED_QUESTIONS + questions:
        assert _claim_errors(text, "question") == [], f"question {text!r} was rejected"


def test_rewrite_table_banned_rows_are_rejected_and_allowed_rows_pass() -> None:
    rows = _rewrite_rows()
    assert len(rows) >= 5
    for banned_text, allowed_text in rows:
        for ctype in ("fact", "possibility"):
            errors = _claim_errors(banned_text, ctype)
            assert any(DIAGNOSIS in e or TREATMENT in e for e in errors), \
                f"{ctype} {banned_text!r} passed: {errors}"
            assert _claim_errors(allowed_text, ctype) == [], \
                f"{ctype} {allowed_text!r} was rejected"


def test_every_treatment_pattern_is_exercised_by_an_example() -> None:
    for pattern in RECOMMENDATION_PATTERNS:
        assert any(pattern.search(t) for t in TREATMENT_ADVICE), \
            f"no TREATMENT_ADVICE example exercises /{pattern.pattern}/"
    for pattern in NONFACT_RECOMMENDATION_PATTERNS:
        assert any(pattern.search(t) for t in DOSE_RATES), \
            f"no DOSE_RATES example exercises /{pattern.pattern}/"


def test_default_banned_is_a_copy_of_the_skill_file() -> None:
    lines = BANNED_CLAIMS_FILE.read_text(encoding="utf-8").splitlines()
    sources = [m.group(1) for m in map(_BANNED_LINE_RE.match, lines) if m]
    assert sources, "banned-claims.md has no pattern lines"
    assert DEFAULT_BANNED == sources


def _verifier_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records
            if r.name == "fasalnama.verifier" and r.levelno == logging.WARNING]


def test_skill_file_loads_without_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="fasalnama.verifier"):
        patterns = load_banned_patterns()
    assert [p.pattern for p in patterns] == DEFAULT_BANNED
    assert _verifier_warnings(caplog) == []


def test_missing_banned_claims_file_falls_back_with_a_warning(
        tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="fasalnama.verifier"):
        patterns = load_banned_patterns(tmp_path / "missing" / "banned-claims.md")
    assert [p.pattern for p in patterns] == DEFAULT_BANNED
    assert len(_verifier_warnings(caplog)) == 1
    # The fallback still covers the English gaps and the Urdu-script patterns.
    for text in ("This is a fungal infection.", "Urea caused the yellowing.", "یہ بیماری ہے۔"):
        assert any(p.search(text) for p in patterns), f"fallback misses {text!r}"


def test_banned_claims_file_without_patterns_falls_back_with_a_warning(
        tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "banned-claims.md"
    path.write_text("# Banned claims\n\nNo pattern lines here.\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="fasalnama.verifier"):
        patterns = load_banned_patterns(path)
    assert [p.pattern for p in patterns] == DEFAULT_BANNED
    assert len(_verifier_warnings(caplog)) == 1
