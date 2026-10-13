from __future__ import annotations

from typing import Any


def _mark(value: bool) -> str:
    return "yes" if value else "no"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ResearchClawEval Leaderboard",
        "",
        "Only sanitized, evidence-linked native observations are listed here.",
        "",
        "| Campaign | Topic | Framework | Model | Research | Scored | Contract | "
        "Engineering | Primary score | Evidence |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["results"]:
        score = "N/A" if row["primary_score"] is None else f"{row['primary_score']:.6g}"
        evidence = row["trace_url"] or row["artifacts_url"] or "N/A"
        if evidence != "N/A":
            evidence = f"[evidence]({evidence})"
        lines.append(
            "| {campaign} | {topic} | {framework} | {model} | {research} | {scored} | "
            "{contract} | {engineering} | {score} | {evidence} |".format(
                campaign=row["campaign_id"],
                topic=row["topic_id"],
                framework=row["framework_id"],
                model=row["model"],
                research=_mark(row["research_completed"]),
                scored=_mark(row["scored"]),
                contract=_mark(row["contract_complete"]),
                engineering=_mark(row["engineering_complete"]),
                score=score,
                evidence=evidence,
            )
        )
    if not payload["results"]:
        lines.extend(["", "No public results have passed the release audit yet."])
    return "\n".join(lines) + "\n"
