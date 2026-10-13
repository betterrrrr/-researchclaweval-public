from __future__ import annotations

import json
from pathlib import Path

from researchclaweval.leaderboard import render_markdown
from researchclaweval.validation import validate_leaderboard

ROOT = Path(__file__).resolve().parents[1]


def test_empty_leaderboard_is_valid_and_explicit() -> None:
    payload = json.loads((ROOT / "leaderboard" / "results.json").read_text(encoding="utf-8"))
    assert validate_leaderboard(ROOT, payload) == []
    rendered = render_markdown(payload)
    assert "No public results have passed" in rendered


def test_missing_score_renders_as_na() -> None:
    payload = {
        "schema_version": 1,
        "results": [
            {
                "run_id": "example-run",
                "campaign_id": "example-campaign",
                "topic_id": "gave2_task2",
                "framework_id": "01",
                "model": "example-model",
                "provider": "example-provider",
                "adapter_commit": "0" * 40,
                "research_completed": True,
                "scored": False,
                "contract_complete": False,
                "engineering_complete": True,
                "primary_score": None,
                "artifacts_url": None,
                "trace_url": None,
                "recorded_at": "2026-08-04T00:00:00Z",
            }
        ],
    }
    assert validate_leaderboard(ROOT, payload) == []
    assert "| N/A | N/A |" in render_markdown(payload)

