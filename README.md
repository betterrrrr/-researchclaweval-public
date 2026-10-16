# ResearchClawEval

[中文说明](README.zh-CN.md)

ResearchClawEval is a public evaluation control plane for research-agent
frameworks. It defines task contracts, pins upstream framework versions,
records adapter patches, validates run evidence, and renders sanitized result
tables without distributing private datasets or framework checkouts.

**Running your own framework?** Start with
[docs/participant_quickstart.md](docs/participant_quickstart.md) — environment,
data, wrapper, first run, in that order.

## Support matrix

| Topic | Maturity | Registered modes |
|---|---|---|
| ARC-WBE-2026 | stable | input pack, smoke, full run |
| PsyDefDetect | beta | smoke, full run |
| BabyLM-10M | legacy | full run |
| TDC-ADMET-Tox | experimental | smoke, full run |
| MountainCar-Continuous | experimental | full run |

"Registered modes" means the registry has a run mapping, which is what `rceval
registry matrix` and `rceval dry-run` read. **BabyLM-10M and
MountainCar-Continuous have fullrun mappings but no smoke mappings** — the
validator mapping in real_eval/scripts/validate_framework_run.py has no entry
for either. Treat their first fullrun as the admission gate instead.

The registry contains 7 framework adapters and 63 topic/framework/mode
mappings. A mapping is not proof of a valid native result. Full-run rows remain
`candidate_requires_runtime_evidence` until launch, provider, trace, and output
evidence pass validation. Generic host `codex exec` mappings are explicitly
`unsupported_non_native`.

## Quick start

Requirements: Linux, Python 3.10-3.12, and `uv`. Docker is required only for
real framework runs.

### One-click setup (for collaborators)

```bash
# Clone this repository
git clone https://github.com/betterrrrr/-researchclaweval-public.git
cd researchclaweval-public

# Clone the frameworks and their pinned patches (all seven by default;
# --quick takes a small subset instead)
bash setup.sh --quick
bash setup.sh --frameworks 03,05,06,07

# Set up your LLM API key
cp .env.example .env
# Edit .env with your API credentials

# Verify the setup
bash scripts/quickstart.sh
```

See [SETUP.md](SETUP.md) for detailed collaboration instructions.

### Minimal validation (no frameworks needed)

These commands do not launch a framework or require datasets:

```bash
uv sync --extra dev
uv run rceval validate registry
uv run rceval registry list
uv run rceval registry matrix --topic arc_wbe_2026 --mode smoke
uv run rceval dry-run --topic arc_wbe_2026 --mode smoke --output-dir /tmp/rceval-plan
uv run rceval leaderboard render
```

## Run your own framework

A **wrapper** is the one file you write to run your own research-agent
framework under this harness. It declares how to launch your framework and
hands off to the shared topic runner — it contains no evaluation logic.

- Interface reference: [real_eval/docs/wrapper_interface.md](real_eval/docs/wrapper_interface.md)
- Skeleton to copy: [real_eval/templates/my_framework_wrapper.sh](real_eval/templates/my_framework_wrapper.sh)
- Generate both: `uv run rceval adapter init --id 08 --name MyFramework --topics tdc_admet_tox`

`adapter init` writes one wrapper per topic plus an adapter manifest. Wrappers
run standalone, so registering in the registry is optional.

The one non-obvious part is the **native-execution proof**: your framework must
echo `FRAMEWORK_NATIVE_LOG_MARKER` from inside its own execution. A run that
exits `0` without that marker in the log is judged non-native and is not scored.

What your framework must *produce* is specified separately, per topic, in
`automation/<topic>_contract.md` — required artifacts, experiment count, and
trace fields.

Datasets are **not stored in this repository**, but you are not left to find
them yourself either — `setup_datasets.sh` downloads each one from its official
source and verifies a pinned sha256 before accepting it:

```bash
bash scripts/setup_datasets.sh --dataset tdc_admet_tox   # Harvard Dataverse, 1.4 MB
bash scripts/setup_datasets.sh --dataset psydefdetect    # HuggingFace,      5.4 MB
bash scripts/setup_datasets.sh --dataset arc_wbe_2026    # HuggingFace,    907 MB
```

Each run prints the `*_DATASET_ROOT` to export. If `huggingface.co` is
unreachable on your network, set `HF_ENDPOINT=https://hf-mirror.com` first —
the script already falls back to a mirror, but only when the direct attempt
fails.

## Repository boundary

This repository contains contracts, registry data, validators, wrappers,
adapter manifests, minimal patches, tests, and public documentation. It does
not contain API credentials, hidden labels, datasets, raw run directories,
local automation state, or full upstream framework sources.

See [CONTRIBUTING.md](CONTRIBUTING.md) for Topic, adapter, and result submission
requirements. `framework_evaluator` is experimental in v0.1 and is not yet a
stable Python API.