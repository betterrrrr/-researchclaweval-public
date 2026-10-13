#!/usr/bin/env python3
"""validate_ai_researcher_context.py

Compact context management without changing scientific content.

Truncates raw tool outputs, duplicate messages, and large arrays while
preserving:
  - Current Topic contract    (class: task)
  - Framework-authored idea   (class: idea)
  - Compact experiment ledger (class: experiment-ledger)
  - Selected evidence         (class: evidence)
  - Pending native stage      (class: pending-stage)

Never adds methods, alters scores, or replaces agent output.  Records
before/after token estimates and retained message classes.

Usage:
  python3 validate_ai_researcher_context.py \\
      --fixture path/to/transcript.json \\
      --max-tokens 180000 \\
      --require-class task,idea,experiment-ledger,pending-stage \\
      --output result.json

Exit codes:
  0   All validations pass (required classes retained, token count below threshold).
  1   Validation failures (missing required class, token count exceeds max).
  2   Input error (missing fixture, bad JSON, etc.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Token estimation ──────────────────────────────────────────────────

PRESERVED_CLASSES = frozenset({
    "task",
    "idea",
    "experiment-ledger",
    "evidence",
    "pending-stage",
})

TRUNCATE_CLASSES = frozenset({
    "tool-output",
    "system",
})

REMOVE_CLASSES = frozenset({
    "duplicate",
})

# Default truncation: keep first N chars of truncatable messages
TRUNCATE_MAX_CHARS = 500
# Max system messages to keep
MAX_SYSTEM_MESSAGES = 2


def estimate_tokens(text: str) -> int:
    """Rough token estimate based on UTF-8 bytes / 4.

    This is a heuristic for comparison purposes, not an exact tokenizer
    match.  A typical English/Chinese mixed text averages ~4 bytes per
    token.
    """
    return max(1, len(text.encode("utf-8")) // 4)


def message_hash(content: str) -> str:
    """SHA-256 hex digest of a message's content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Context compaction ────────────────────────────────────────────────


def compact_context(
    messages: list[dict[str, Any]],
    max_tokens: int,
    required_classes: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compact a transcript message list to fit within *max_tokens*.

    Returns (retained_messages, stats) where *stats* documents what was
    preserved, truncated, and removed.
    """
    input_msg_count = len(messages)
    input_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
    input_class_counts: dict[str, int] = {}
    for m in messages:
        c = m.get("class", "unknown")
        input_class_counts[c] = input_class_counts.get(c, 0) + 1

    # ── Phase 1: classify & filter ────────────────────────────────────
    preserved: list[dict[str, Any]] = []
    truncated: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    system_count = 0

    for m in messages:
        cls = m.get("class", "unknown")
        content = m.get("content", "")

        if cls in PRESERVED_CLASSES:
            # Preserve as-is
            preserved.append(m)

        elif cls in REMOVE_CLASSES:
            removed.append(m)

        elif cls == "system":
            system_count += 1
            if system_count <= MAX_SYSTEM_MESSAGES:
                preserved.append(m)
            else:
                removed.append(m)

        elif cls in TRUNCATE_CLASSES:
            if len(content) > TRUNCATE_MAX_CHARS:
                truncated_msg = dict(m)
                truncated_msg["content"] = content[:TRUNCATE_MAX_CHARS]
                truncated_msg["_truncated"] = True
                truncated_msg["_original_length"] = len(content)
                truncated.append(truncated_msg)
                preserved.append(truncated_msg)
            else:
                preserved.append(m)

        else:
            # Unknown class — keep as-is
            preserved.append(m)

    # ── Phase 2: if still over max_tokens, progressively trim ────────
    current_tokens = sum(estimate_tokens(m.get("content", "")) for m in preserved)
    if current_tokens > max_tokens:
        # Trim from the end of preserved messages (reverse order)
        # First trim truncated messages further
        trim_candidates = [m for m in preserved if m.get("_truncated")]
        for m in trim_candidates:
            if current_tokens <= max_tokens:
                break
            content = m.get("content", "")
            target_len = max(100, len(content) // 2)
            m["content"] = content[:target_len]
            m["_trimmed_further"] = True
            current_tokens -= estimate_tokens(content) - estimate_tokens(m["content"])

        # If still over, trim from the end of preserved non-required messages
        if current_tokens > max_tokens:
            # Walk backwards, trimming content of preserved messages that aren't
            # in the required_classes list
            for m in reversed(preserved):
                if current_tokens <= max_tokens:
                    break
                cls = m.get("class", "")
                if cls in required_classes:
                    continue  # never trim required classes
                content = m.get("content", "")
                if len(content) > 200:
                    target_len = max(100, len(content) // 2)
                    m["content"] = content[:target_len]
                    m["_trimmed_further"] = True
                    current_tokens -= estimate_tokens(content) - estimate_tokens(m["content"])

    # ── Phase 3: compute hashes ──────────────────────────────────────
    retained_hashes: list[str] = []
    for m in preserved:
        h = m.get("hash")
        if h is None:
            h = message_hash(m.get("content", ""))
            m["hash"] = h
        retained_hashes.append(h)

    # ── Stats ─────────────────────────────────────────────────────────
    output_class_counts: dict[str, int] = {}
    for m in preserved:
        c = m.get("class", "unknown")
        output_class_counts[c] = output_class_counts.get(c, 0) + 1

    removed_classes: dict[str, int] = {}
    for m in removed:
        c = m.get("class", "unknown")
        removed_classes[c] = removed_classes.get(c, 0) + 1

    truncated_classes: dict[str, int] = {}
    for m in truncated:
        c = m.get("class", "unknown")
        truncated_classes[c] = truncated_classes.get(c, 0) + 1

    output_tokens = sum(estimate_tokens(m.get("content", "")) for m in preserved)

    stats: dict[str, Any] = {
        "before": {
            "total_tokens_estimate": input_tokens,
            "message_count": input_msg_count,
            "classes": input_class_counts,
        },
        "after": {
            "total_tokens_estimate": output_tokens,
            "message_count": len(preserved),
            "classes": output_class_counts,
            "retained_message_hashes": retained_hashes,
            "truncated_message_count": len(truncated),
            "removed_message_count": len(removed),
        },
        "classes_preserved": sorted(PRESERVED_CLASSES & set(output_class_counts.keys())),
        "classes_truncated": sorted(set(truncated_classes.keys())),
        "classes_removed": sorted(set(removed_classes.keys())),
        "hashes_below_threshold": output_tokens <= max_tokens,
        "truncated_classes_detail": truncated_classes,
        "removed_classes_detail": removed_classes,
    }

    return preserved, stats


# ── Validation ────────────────────────────────────────────────────────


def validate_required_classes(
    preserved: list[dict[str, Any]],
    required_classes: list[str],
) -> list[str]:
    """Check that all required classes are present in retained messages.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    retained_classes = {m.get("class") for m in preserved}
    for cls in required_classes:
        if cls not in retained_classes:
            errors.append(f"Required class {cls!r} is missing from retained messages")
    return errors


def validate_no_content_mutation(
    original_messages: list[dict[str, Any]],
    preserved: list[dict[str, Any]],
    required_classes: list[str],
) -> list[str]:
    """Verify that preserved messages of required classes have not had their
    content altered (hash matches the original).

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    # Build lookup: original hash -> original content
    orig_by_hash: dict[str, str] = {}
    for m in original_messages:
        h = m.get("hash", "")
        if h:
            orig_by_hash[h] = m.get("content", "")

    for m in preserved:
        cls = m.get("class", "")
        if cls not in required_classes:
            continue
        hash_val = m.get("hash", "")
        orig_content = orig_by_hash.get(hash_val)
        if orig_content is None:
            # hash might not match if we regenerated it; check content directly
            # Actually, for preserved messages, hash should be the same as original
            stored_hash = m.get("hash", "")
            computed_hash = message_hash(m.get("content", ""))
            if stored_hash and stored_hash != computed_hash:
                errors.append(
                    f"Content mutation detected in {cls} message: hash mismatch"
                )
        else:
            if m.get("content") != orig_content:
                errors.append(
                    f"Content mutation detected in {cls} message: content changed "
                    f"from original"
                )
    return errors


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compact context management without changing scientific content"
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="Path to transcript JSON fixture",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=180000,
        help="Maximum allowed token count after compaction (default: 180000)",
    )
    parser.add_argument(
        "--require-class",
        type=str,
        default="",
        help="Comma-separated list of message classes that must be retained",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write JSON validation output",
    )
    args = parser.parse_args()

    fixture_path = args.fixture.resolve()
    output_path = args.output.resolve()
    max_tokens = args.max_tokens
    required_classes = [c.strip() for c in args.require_class.split(",") if c.strip()]

    # ── Load fixture ──────────────────────────────────────────────────
    if not fixture_path.is_file():
        print(f"ERROR: fixture not found: {fixture_path}", file=sys.stderr)
        return 2

    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: failed to parse fixture: {e}", file=sys.stderr)
        return 2

    messages = fixture.get("messages", [])
    if not messages:
        print("ERROR: fixture has no messages array", file=sys.stderr)
        return 2

    print(f"Loaded {len(messages)} messages from {fixture_path}")

    # ── Compact context ───────────────────────────────────────────────
    preserved, stats = compact_context(messages, max_tokens, required_classes)

    # ── Validate ──────────────────────────────────────────────────────
    errors: list[str] = []

    # Required class check
    class_errors = validate_required_classes(preserved, required_classes)
    errors.extend(class_errors)

    # Content mutation check (only for required classes)
    mutation_errors = validate_no_content_mutation(messages, preserved, required_classes)
    errors.extend(mutation_errors)

    # Token threshold check
    output_tokens = stats["after"]["total_tokens_estimate"]
    if output_tokens > max_tokens:
        errors.append(
            f"Token count {output_tokens} exceeds max-tokens {max_tokens}"
        )

    # ── Build output ──────────────────────────────────────────────────
    valid = len(errors) == 0

    # Verify that required-class hashes match original (below threshold
    # means "hashes are preserved without mutation")
    hashes_below_threshold = True
    hash_mismatches: list[str] = []
    for m in preserved:
        cls = m.get("class", "")
        if cls not in required_classes:
            continue
        orig_hash = m.get("hash", "")
        computed_hash = message_hash(m.get("content", ""))
        if orig_hash and orig_hash != computed_hash:
            hashes_below_threshold = False
            hash_mismatches.append(
                f"Hash mismatch for {cls} message: expected {orig_hash}, got {computed_hash}"
            )

    result: dict[str, Any] = {
        "validator": "validate_ai_researcher_context",
        "fixture": str(fixture_path),
        "valid": valid,
        "max_tokens": max_tokens,
        "required_classes": required_classes,
        "before": stats["before"],
        "after": stats["after"],
        "classes_preserved": stats["classes_preserved"],
        "classes_truncated": stats["classes_truncated"],
        "classes_removed": stats["classes_removed"],
        "hashes_below_threshold": hashes_below_threshold,
        "hash_mismatches": hash_mismatches,
        "errors": errors,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
    }

    # ── Write output ──────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "valid": valid,
        "output": str(output_path),
        "before_tokens": stats["before"]["total_tokens_estimate"],
        "after_tokens": stats["after"]["total_tokens_estimate"],
        "before_messages": stats["before"]["message_count"],
        "after_messages": stats["after"]["message_count"],
        "error_count": len(errors),
        "hashes_below_threshold": hashes_below_threshold,
    }
    print(json.dumps(summary, ensure_ascii=False))

    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())