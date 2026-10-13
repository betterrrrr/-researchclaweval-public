#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "error: public boundary check requires a Git worktree" >&2
  exit 2
fi

failed=0
forbidden_path_pattern='^(api|data|external|recovery|\.framework-refresh|\.sdd|automation/(env|runs|state)|real_eval/(run_checks|runs|systemd_runs)|AI-Researcher|AI-Scientist-v2|Auto-claude-code-research-in-sleep|AutoResearchClaw|DeepScientist|dr-claw|EvoScientist)(/|$)'

while IFS= read -r path; do
  if [[ "$path" =~ $forbidden_path_pattern ]]; then
    echo "forbidden tracked path: $path" >&2
    failed=1
  fi
  if [[ -f "$path" ]] && (( $(stat -c %s "$path") > 5242880 )); then
    echo "tracked file exceeds 5 MiB: $path" >&2
    failed=1
  fi
done < <(git ls-files)

if git grep -nE '/home/(jianbiao|guanghao)/researchclaweval' -- . >/dev/null; then
  echo "machine-specific repository path detected" >&2
  git grep -nE '/home/(jianbiao|guanghao)/researchclaweval' -- . >&2
  failed=1
fi

# Bare account names leak the same way a full path does. The two guard files
# mention these names by construction, so they are excluded here.
if git grep -nE '(jianbiao|guanghao)' -- . \
    ':(exclude)scripts/check_public_boundary.sh' \
    ':(exclude)tests/test_public_boundary.py' >/dev/null; then
  echo "machine account name detected" >&2
  git grep -nE '(jianbiao|guanghao)' -- . \
    ':(exclude)scripts/check_public_boundary.sh' \
    ':(exclude)tests/test_public_boundary.py' >&2
  failed=1
fi

secret_pattern='(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{20,}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----)'
if git grep -nE "$secret_pattern" -- . >/dev/null; then
  echo "secret-like tracked content detected" >&2
  git grep -nE "$secret_pattern" -- . >&2
  failed=1
fi

exit "$failed"

