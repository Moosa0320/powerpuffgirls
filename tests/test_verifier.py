"""Unit tests for the report verifier (guide task 10 & section 7.6).

Tests prove that:
- a diagnosis sentence is rejected
- an uncited fact is rejected
- a fake event ID is rejected
- valid evidence-cited reports pass
"""
from datetime import date

from harness.engine import TimelineItem, GapReport
from harness.verifier import (
    DISCLAIMER,
    Evidence,
    EventFact,
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
    # Diagnosis phrases in English and Urdu
    for bad_claim in [
        "The yellowing is caused by nitrogen deficiency",
        "The crop is suffering from early blight fungus",
        "Ye bimari fungal infection hai",
        "Definitely a virus problem",
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
