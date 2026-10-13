# Contributing

All contributions must preserve native framework ownership, run isolation, and
evidence traceability. Open an issue before changing a public schema.

## Add a Topic

1. Add a contract, metric definition, submission format, and public dataset
   acquisition instructions. Do not commit restricted data.
2. Register the Topic with a maturity level and environment-based dataset root.
3. Add validator fixtures and negative tests for cross-topic contamination.
4. Add run mappings only where the referenced wrappers exist.

## Add a framework adapter

1. Pin an upstream HTTPS URL and full 40-character commit.
2. Record the upstream license, documented native entrypoint, required
   environment, and images in an adapter manifest.
3. Submit only minimal patches required by canonical wrappers. Do not vendor the
   upstream repository or include generated framework output.
4. Demonstrate that patches apply to the pinned commit and that the framework,
   rather than a generic host agent, owns planning through final delivery.

## Submit a result

1. Use a registered, admissible run mapping and a fresh physical workspace.
2. Preserve the four independent completion dimensions and use `null` for a
   missing primary score.
3. Link sanitized artifacts and traces. Never submit credentials, hidden labels,
   private datasets, or framework-visible host scoring data.
4. Add the structured result to `leaderboard/results.json`; regenerate Markdown
   with `rceval leaderboard render`.

## Local checks

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest -q
uv run rceval validate registry
bash scripts/check_public_boundary.sh
```

