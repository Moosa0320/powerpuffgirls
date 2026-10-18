"""Placeholder test so CI is green on an empty baseline (guide task 1)."""
from pathlib import Path


def test_repo_layout_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    for expected in [
        "skill/farm-record-investigation",
        "harness/providers",
        "app/backend",
        "app/frontend",
        "eval",
        "render.yaml",
        "LICENSE",
        ".env.example",
        "MODEL_LICENSES.md",
    ]:
        assert (root / expected).exists(), f"missing {expected}"


def test_truth() -> None:
    assert True