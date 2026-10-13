#!/usr/bin/env bash

autoresearchclaw_validate_run_id() {
  local run_id="${1-}"

  if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
    printf 'invalid REAL_EVAL_RUN_ID: must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}\n' >&2
    return 1
  fi
}

verify_framework_research_idea_json() {
  local workspace_dir="$1"

  python3 - "$workspace_dir" <<'PY'
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

workspace = Path(sys.argv[1])
idea_path = workspace / "research_idea.json"
trace_path = workspace / "experiment_trace.json"
event_path = workspace / "research_idea_lock_event.json"

def fail(message: str) -> None:
    raise SystemExit(f"research idea provenance rejected: {message}")

if not idea_path.is_file():
    fail(f"missing {idea_path}")
if not trace_path.is_file():
    fail(f"missing {trace_path}")
if not event_path.is_file():
    fail(f"missing framework lock event {event_path}")

try:
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    event = json.loads(event_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    fail(f"invalid JSON: {exc}")

if not isinstance(idea, dict) or idea.get("framework") != "AutoResearchClaw":
    fail("artifact is not marked as framework-authored")
if idea.get("idea_locked_before_experiments") is not True:
    fail("idea_locked_before_experiments is not true")
if not idea.get("source_artifact") or not str(idea["source_artifact"]).startswith("stage-08/"):
    fail("source_artifact is not the native Stage 8 synthesis output")
for key in ("hypothesis", "method_rationale", "comparison_logic"):
    value = idea.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"artifact lacks non-empty {key}")
if not isinstance(idea.get("expected_failure_modes"), str) or not idea["expected_failure_modes"].strip():
    fail("artifact lacks non-empty expected_failure_modes")
if not isinstance(event, dict) or event.get("event") != "research_idea_locked":
    fail("lock event is not a native research_idea_locked event")
if event.get("owner") != "framework" or event.get("writer") != "AutoResearchClaw":
    fail("lock event is not framework-owned")
if event.get("artifact") != "research_idea.json" or not event.get("event_id"):
    fail("lock event does not identify the idea artifact")

actual_sha256 = hashlib.sha256(idea_path.read_bytes()).hexdigest()
if event.get("artifact_sha256") != actual_sha256:
    fail("artifact hash does not match the framework lock event")
if idea.get("lock_event_id") != event["event_id"]:
    fail("artifact lock_event_id does not match the framework lock event")
if idea.get("locked_at") != event.get("timestamp"):
    fail("artifact locked_at does not match the framework lock timestamp")

if trace.get("idea_artifact") != "research_idea.json":
    fail("experiment trace does not identify research_idea.json")
if trace.get("idea_locked_before_experiments") is not True:
    fail("experiment trace does not confirm the pre-experiment lock")

def parse_timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        fail(f"missing {name}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"invalid {name}")
    if parsed.tzinfo is None:
        fail(f"timezone missing from {name}")
    return parsed

locked_at = parse_timestamp(event.get("timestamp"), "lock timestamp")
first_experiment_at = parse_timestamp(
    trace.get("first_experiment_started_at"), "first_experiment_started_at"
)
if locked_at >= first_experiment_at:
    fail("framework idea lock did not precede the first experiment")
PY
}

apply_autoresearchclaw_stage8_idea_lock_adapter() {
  local workspace_dir="$1"
  local synthesis_path="$workspace_dir/researchclaw/pipeline/stage_impls/_synthesis.py"

  python3 - "$synthesis_path" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if "def _framework_stage8_idea_fields(" in text:
    raise SystemExit(0)
if "import hashlib\n" not in text:
    if "import json\n" not in text:
        raise SystemExit("AutoResearchClaw Stage 8 JSON import insertion point not found")
    text = text.replace("import json\n", "import hashlib\nimport json\n", 1)

marker = '    (stage_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")\n'
if marker not in text:
    raise SystemExit("AutoResearchClaw Stage 8 hypothesis artifact insertion point not found")

adapter = '''\n\ndef _framework_stage8_idea_fields(hypotheses_text: str) -> dict[str, object]:
    paragraphs = [part.strip() for part in hypotheses_text.split("\\n\\n") if part.strip()]

    def section(*keywords: str) -> str:
        active = False
        collected: list[str] = []
        for line in hypotheses_text.splitlines():
            normalized = line.strip()
            if normalized.startswith("#"):
                active = any(keyword in normalized.lower() for keyword in keywords)
                continue
            if active and normalized:
                collected.append(normalized)
        return "\\n".join(collected).strip()

    hypothesis = section("hypothesis") or (paragraphs[0] if paragraphs else "")
    method = section("method", "approach", "proposal") or hypotheses_text.strip()
    failures = section("failure", "risk", "limitation") or hypotheses_text.strip()
    discrimination = section("discrimin", "comparison", "experiment") or hypotheses_text.strip()
    return {
        "hypothesis": hypothesis,
        "method_rationale": method,
        "expected_failure_modes": failures,
        "comparison_logic": discrimination,
    }
'''
text = text.replace("\n\ndef _execute_hypothesis_gen(", adapter + "\n\ndef _execute_hypothesis_gen(", 1)
native_lock = '''    (stage_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

    locked_at = _utcnow_iso()
    lock_event_id = f"stage-08-research-idea-{locked_at}"
    idea_payload = {
        "framework": "AutoResearchClaw",
        # 2026-10-08: 生成代码要在跑第一个实验前验锁，可能查 framework 也可能查
        # writer。两份文件此前各只带一个键（idea 只有 framework、lock event 只有
        # writer），读错一份就判“无可识别 writer”并提前退出 → zero metrics。
        # 两个键都写，纯接口命名，不改语义。
        "writer": "AutoResearchClaw",
        "framework_writer": "AutoResearchClaw",
        "topic": config.research.topic,
        "source_artifact": "stage-08/hypotheses.md",
        **_framework_stage8_idea_fields(hypotheses_md),
        "idea_locked_before_experiments": True,
        "lock_event_id": lock_event_id,
        "locked_at": locked_at,
    }
    idea_path = Path("/workspace/research_idea.json")
    idea_path.write_text(
        json.dumps(idea_payload, ensure_ascii=False, indent=2) + "\\n",
        encoding="utf-8",
    )
    lock_event = {
        "framework": "AutoResearchClaw",
        # 2026-10-08 二修：模型生成的实验代码校验的是 framework_writer
        # （第三个名字！前两个是 framework 与 writer）。缺它就会
        # raise ValueError("Invalid framework writer in idea lock.")
        # → Stage 12 实验前退出 → zero metrics。三个键全写，纯接口命名。
        "framework_writer": "AutoResearchClaw",
        "event": "research_idea_locked",
        "event_id": lock_event_id,
        "owner": "framework",
        "writer": "AutoResearchClaw",
        "artifact": "research_idea.json",
        "source_artifact": "stage-08/hypotheses.md",
        "timestamp": locked_at,
        "artifact_sha256": hashlib.sha256(idea_path.read_bytes()).hexdigest(),
    }
    Path("/workspace/research_idea_lock_event.json").write_text(
        json.dumps(lock_event, ensure_ascii=False, indent=2) + "\\n",
        encoding="utf-8",
    )
    logger.info("Stage 8 framework-authored research idea locked before experiments")
'''
text = text.replace(marker, native_lock, 1)
path.write_text(text, encoding="utf-8")
PY
}

autoresearchclaw_handoff() {
  local topic_name="${1:?topic name is required}"
  local workspace_dir="${2:-${WORKSPACE:-$PWD}}"
  local artifact_root="${3:?artifact root is required}"
  local deliverables_dir
  local handoff_failed=0
  local handoff_noop=0
  local artifact_root_input="$artifact_root"

  if [[ "$artifact_root" != /* ]]; then
    printf 'AutoResearchClaw handoff [%s]: artifact root must be an explicit absolute path\n' \
      "$topic_name" >&2
    return 1
  fi
  workspace_dir="$(realpath -e -- "$workspace_dir")" || {
    printf 'AutoResearchClaw handoff [%s]: workspace root is missing\n' "$topic_name" >&2
    return 1
  }
  if [[ -L "$artifact_root_input" ]]; then
    printf 'AutoResearchClaw handoff [%s]: artifact root must not be a symlink\n' "$topic_name" >&2
    return 1
  fi
  artifact_root="$(realpath -e -- "$artifact_root_input")" || {
    printf 'AutoResearchClaw handoff [%s]: artifact root is missing\n' "$topic_name" >&2
    return 1
  }
  case "$artifact_root/" in
    "$workspace_dir"/*) ;;
    *)
      printf 'AutoResearchClaw handoff [%s]: artifact root is outside workspace\n' "$topic_name" >&2
      return 1
      ;;
  esac
  deliverables_dir="$artifact_root/deliverables"
  if [[ ! -d "$deliverables_dir" || -L "$deliverables_dir" ]]; then
    printf 'AutoResearchClaw handoff [%s]: missing current deliverables directory %s\n' \
      "$topic_name" "$deliverables_dir" >&2
    return 1
  fi
  if [[ -n "$(find "$artifact_root" -type l -print -quit 2>/dev/null)" ]]; then
    printf 'AutoResearchClaw handoff [%s]: current artifact root contains symlinks\n' "$topic_name" >&2
    return 1
  fi

  _autoresearchclaw_find_artifact() {
    local artifact_name="$1"

    local candidate="$deliverables_dir/$artifact_name"
    [[ -f "$candidate" && ! -L "$candidate" && -s "$candidate" ]] || return 1
    local canonical_candidate
    canonical_candidate="$(realpath -e -- "$candidate")" || return 1
    case "$canonical_candidate" in
      "$deliverables_dir"/*) ;;
      *) return 1 ;;
    esac
    REPLY="$canonical_candidate"
    return 0
  }

  _autoresearchclaw_promote_file() {
    local destination_name="$1"
    local artifact_name
    shift

    for artifact_name in "$@"; do
      if _autoresearchclaw_find_artifact "$artifact_name"; then
        if cp "$REPLY" "$workspace_dir/$destination_name"; then
          printf 'AutoResearchClaw handoff [%s]: promoted %s to %s\n' \
            "$topic_name" "$REPLY" "$workspace_dir/$destination_name"
          return 0
        fi
        printf 'AutoResearchClaw handoff [%s]: could not copy %s to %s\n' \
          "$topic_name" "$REPLY" "$workspace_dir/$destination_name" >&2
        return 1
      fi
    done

    if [[ -f "$workspace_dir/$destination_name" && ! -L "$workspace_dir/$destination_name" && -s "$workspace_dir/$destination_name" ]]; then
      printf 'AutoResearchClaw handoff [%s]: found %s already in workspace root, marking as promoted\n' \
        "$topic_name" "$workspace_dir/$destination_name"
      return 0
    fi

    printf 'AutoResearchClaw handoff [%s]: missing required %s under %s' \
      "$topic_name" "$*" "$deliverables_dir" >&2
    printf ' (not found in workspace root either)\n' >&2
    return 1
  }

  _autoresearchclaw_promote_directory() {
    local directory_name="$1"
    local source_directory="$deliverables_dir/$directory_name"

    [[ -d "$source_directory" && ! -L "$source_directory" ]] || {
      printf 'AutoResearchClaw handoff [%s]: missing required directory %s under %s\n' \
        "$topic_name" "$directory_name" "$deliverables_dir" >&2
      return 1
    }
    if [[ -n "$(find "$source_directory" -type l -print -quit 2>/dev/null)" ]]; then
      printf 'AutoResearchClaw handoff [%s]: required directory %s contains symlinks\n' \
        "$topic_name" "$directory_name" >&2
      return 1
    fi
    if [[ -z "$(find "$source_directory" -type f -print -quit 2>/dev/null)" ]]; then
      printf 'AutoResearchClaw handoff [%s]: required directory %s is empty\n' \
        "$topic_name" "$directory_name" >&2
      return 1
    fi
    if [[ -L "$workspace_dir/$directory_name" ]]; then
      printf 'AutoResearchClaw handoff [%s]: destination %s is a symlink\n' \
        "$topic_name" "$workspace_dir/$directory_name" >&2
      return 1
    fi
    if cp -a -- "$source_directory" "$workspace_dir/$directory_name"; then
      printf 'AutoResearchClaw handoff [%s]: promoted %s\n' \
        "$topic_name" "$deliverables_dir/$directory_name"
      return 0
    fi

    printf 'AutoResearchClaw handoff [%s]: could not copy %s\n' \
      "$topic_name" "$deliverables_dir/$directory_name" >&2
    return 1
  }

  _autoresearchclaw_try_fallback() {
    local destination_name="$1"
    local fallback_path
    fallback_path="$(find "$artifact_root" -path "*/stage-12/experiment/main.py" -type f 2>/dev/null | head -1)"
    if [[ -n "$fallback_path" && -f "$fallback_path" && -s "$fallback_path" ]]; then
      if cp "$fallback_path" "$workspace_dir/$destination_name"; then
        printf 'AutoResearchClaw handoff [%s]: fallback: copied %s → %s\n' \
          "$topic_name" "$fallback_path" "$workspace_dir/$destination_name"
        return 0
      fi
    fi
    printf 'AutoResearchClaw handoff [%s]: %s not available (non-blocking)\n' \
      "$topic_name" "$destination_name" >&2
    return 1
  }

  case "$topic_name" in
    arc_wbe_2026)
      _autoresearchclaw_promote_file estimator.py estimator.py || _autoresearchclaw_try_fallback estimator.py || handoff_noop=1
      _autoresearchclaw_promote_file submission.json submission.json || handoff_noop=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      _autoresearchclaw_promote_file arc_score_evidence.json \
        score_evidence.json validation_score.json score.json || handoff_noop=1
      if [[ -e "$workspace_dir/score.json" ]]; then
        printf 'AutoResearchClaw handoff [%s]: root score.json is host-only and must not exist before host scoring\n' \
          "$topic_name" >&2
        handoff_failed=1
      fi
      ;;
    psydefdetect)
      if _autoresearchclaw_find_artifact predictions.jsonl; then
        _autoresearchclaw_promote_file predictions.jsonl predictions.jsonl || handoff_failed=1
      else
        _autoresearchclaw_promote_file submission.csv submission.csv || handoff_noop=1
      fi
      _autoresearchclaw_promote_file score.json score.json || handoff_noop=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      ;;
    tdc_admet_tox)
      _autoresearchclaw_promote_file predictions.csv predictions.csv submission.csv || handoff_noop=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      if [[ -e "$workspace_dir/score.json" ]]; then
        printf 'AutoResearchClaw handoff [%s]: root score.json is host-only and must not exist before host scoring\n' \
          "$topic_name" >&2
        handoff_failed=1
      fi
      ;;
    babylm)
      _autoresearchclaw_promote_file research_idea.json research_idea.json || handoff_failed=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      if [[ -e "$workspace_dir/score.json" ]]; then
        printf 'AutoResearchClaw handoff [%s]: root score.json is host-only and must not exist before host scoring\n' \
          "$topic_name" >&2
        handoff_failed=1
      fi
      ;;
    topic2)
      _autoresearchclaw_promote_file research_idea.json research_idea.json || handoff_failed=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      if [[ -e "$workspace_dir/score.json" ]]; then
        printf 'AutoResearchClaw handoff [%s]: root score.json is host-only and must not exist before host scoring\n' \
          "$topic_name" >&2
        handoff_failed=1
      fi
      ;;
    gave2_task2)
      _autoresearchclaw_promote_directory submission || handoff_failed=1
      _autoresearchclaw_promote_file experiment_trace.json experiment_trace.json || handoff_failed=1
      _autoresearchclaw_promote_file final_report.md final_report.md || handoff_failed=1
      ;;
    *)
      printf 'AutoResearchClaw handoff: unsupported topic %s\n' "$topic_name" >&2
      return 2
      ;;
  esac

  if [[ "$handoff_failed" -ne 0 ]]; then
    printf 'AutoResearchClaw handoff [%s]: FAILED; required native artifacts were not promoted\n' \
      "$topic_name" >&2
    return 1
  fi

  if [[ "$handoff_noop" -ne 0 ]]; then
    printf 'AutoResearchClaw handoff [%s]: complete (with %d non-blocking warnings)\n' \
      "$topic_name" "$handoff_noop"
    return 0
  fi

  printf 'AutoResearchClaw handoff [%s]: complete\n' "$topic_name"
  return 0
}
