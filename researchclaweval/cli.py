from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .leaderboard import render_markdown as render_leaderboard
from .registry import config_for, load_json, load_registry, matrix_rows, render_matrix_markdown
from .scaffold import scaffold, slugify
from .validation import validate_leaderboard, validate_registry, validate_run


def _dump(payload: Any, *, compact: bool = False) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=None if compact else 2)


def _registry_list(args: argparse.Namespace) -> int:
    registry = load_registry()
    payload: dict[str, Any] = {"schema_version": 1}
    if args.kind in {"all", "topics"}:
        payload["topics"] = list(registry.topics.values())
    if args.kind in {"all", "frameworks"}:
        payload["frameworks"] = list(registry.frameworks.values())
    if args.format == "json":
        print(_dump(payload))
        return 0

    lines = []
    if "topics" in payload:
        lines.extend(
            [
                "| Topic ID | Label | Maturity | Modes |",
                "|---|---|---|---|",
                *[
                    f"| {row['id']} | {row['label']} | {row['maturity']} | "
                    f"{', '.join(row['supported_modes'])} |"
                    for row in payload["topics"]
                ],
            ]
        )
    if "frameworks" in payload:
        if lines:
            lines.append("")
        lines.extend(
            [
                "| Framework ID | Name | Upstream commit | License |",
                "|---|---|---|---|",
                *[
                    f"| {row['id']} | {row['name']} | `{row['upstream_commit']}` | "
                    f"{row['license_spdx']} |"
                    for row in payload["frameworks"]
                ],
            ]
        )
    print("\n".join(lines))
    return 0


def _registry_matrix(args: argparse.Namespace) -> int:
    registry = load_registry()
    if args.topic is not None and args.topic not in registry.topics:
        raise ValueError(f"unknown topic: {args.topic}")
    if args.mode is not None and args.mode not in {row["mode"] for row in registry.runs}:
        raise ValueError(f"unknown mode: {args.mode}")
    if args.framework is not None and args.framework not in registry.frameworks:
        raise ValueError(f"unknown framework: {args.framework}")
    runs = registry.matching_runs(topic=args.topic, mode=args.mode, framework=args.framework)
    if not runs and any((args.topic, args.mode, args.framework)):
        raise ValueError("no run mappings match the requested filters")
    rows = matrix_rows(registry, runs)
    rendered = (
        _dump({"schema_version": 1, "rows": rows})
        if args.format == "json"
        else render_matrix_markdown(rows)
    )
    print(rendered)
    return 0


def _registry_export(args: argparse.Namespace) -> int:
    registry = load_registry()
    print(_dump(config_for(registry, args.topic, args.mode), compact=args.compact))
    return 0


def _validate_registry(_args: argparse.Namespace) -> int:
    registry = load_registry()
    errors = validate_registry(registry)
    payload = {"schema_version": 1, "ok": not errors, "errors": errors}
    print(_dump(payload))
    return 0 if not errors else 2


def _validate_run(args: argparse.Namespace) -> int:
    registry = load_registry()
    payload = validate_run(
        registry,
        topic=args.topic,
        framework=args.framework,
        mode=args.mode,
        run_dir=Path(args.run_dir),
    )
    print(_dump(payload))
    return 0 if payload["ok"] else 13


def _dry_run(args: argparse.Namespace) -> int:
    registry = load_registry()
    rows = matrix_rows(
        registry,
        registry.matching_runs(topic=args.topic, mode=args.mode, framework=args.framework),
    )
    if not rows:
        raise ValueError(f"no run mappings for topic={args.topic} mode={args.mode}")
    payload = {
        "schema_version": 1,
        "status": "dry_run",
        "topic_id": args.topic,
        "mode": args.mode,
        "framework_count": len(rows),
        "rows": rows,
    }
    rendered = _dump(payload)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError(f"refusing to reuse non-empty output directory: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "dry_run.json").write_text(rendered + "\n", encoding="utf-8")
        (output_dir / "dry_run.md").write_text(
            render_matrix_markdown(rows) + "\n", encoding="utf-8"
        )
    print(rendered)
    return 0


def _leaderboard_render(args: argparse.Namespace) -> int:
    root = load_registry().root
    input_path = Path(args.input) if args.input else root / "leaderboard" / "results.json"
    payload = load_json(input_path)
    errors = validate_leaderboard(root, payload)
    if errors:
        raise ValueError("invalid leaderboard: " + "; ".join(errors))
    rendered = render_leaderboard(payload)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


def _adapter_init(args: argparse.Namespace) -> int:
    out_dir = Path(args.out_dir).resolve()
    try:
        written = scaffold(
            framework_id=args.id,
            name=args.name,
            topics=[t.strip() for t in args.topics.split(",") if t.strip()],
            upstream_url=args.upstream_url,
            license_spdx=args.license,
            image=args.image,
            entrypoint=args.entrypoint,
            out_dir=out_dir,
            force=args.force,
        )
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for path in written:
        print(f"created {path.relative_to(out_dir)}")

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    print(
        "\nNext steps:\n"
        "  1. Fill in the TODO markers in the generated wrapper(s) — the runtime\n"
        "     command is a stub, and FRAMEWORK_ENTRY_PATHS may need files that\n"
        "     live inside your framework checkout.\n"
        "  2. Put a real 40-character commit in upstream_commit.\n"
        "  3. Read real_eval/docs/wrapper_interface.md, especially the\n"
        "     native-execution proof.\n"
        f"  4. Run one topic:\n"
        f"       export PROVIDER_CONFIG=/path/to/your_provider.toml\n"
        f"       export {topics[0].upper()}_DATASET_ROOT=/path/to/dataset\n"
        f"       bash real_eval/scripts/{args.id}_{slugify(args.name)}_{topics[0]}_fullrun.sh\n"
        "  Registering the adapter in real_eval/registry/frameworks.json and\n"
        "  runs.json is optional: wrappers run standalone. It is only needed for\n"
        "  `rceval registry` / `rceval dry-run` to know about your framework."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rceval", description="ResearchClawEval public CLI")
    commands = parser.add_subparsers(dest="command", required=True)

    registry = commands.add_parser("registry", help="Inspect the public registry")
    registry_commands = registry.add_subparsers(dest="registry_command", required=True)
    listing = registry_commands.add_parser("list")
    listing.add_argument("--kind", choices=["all", "topics", "frameworks"], default="all")
    listing.add_argument("--format", choices=["markdown", "json"], default="markdown")
    listing.set_defaults(handler=_registry_list)

    matrix = registry_commands.add_parser("matrix")
    matrix.add_argument("--topic")
    matrix.add_argument("--mode")
    matrix.add_argument("--framework")
    matrix.add_argument("--format", choices=["markdown", "json"], default="markdown")
    matrix.set_defaults(handler=_registry_matrix)

    export = registry_commands.add_parser("export")
    export.add_argument("--topic", required=True)
    export.add_argument("--mode", required=True)
    export.add_argument("--compact", action="store_true")
    export.set_defaults(handler=_registry_export)

    validate = commands.add_parser("validate", help="Validate registry or run evidence")
    validate_commands = validate.add_subparsers(dest="validate_command", required=True)
    validate_registry_parser = validate_commands.add_parser("registry")
    validate_registry_parser.set_defaults(handler=_validate_registry)
    validate_run_parser = validate_commands.add_parser("run")
    validate_run_parser.add_argument("--topic", required=True)
    validate_run_parser.add_argument("--framework", required=True)
    validate_run_parser.add_argument("--mode", required=True)
    validate_run_parser.add_argument("--run-dir", required=True)
    validate_run_parser.set_defaults(handler=_validate_run)

    dry_run = commands.add_parser("dry-run", help="Render a plan without executing a framework")
    dry_run.add_argument("--topic", required=True)
    dry_run.add_argument("--mode", required=True)
    dry_run.add_argument("--framework")
    dry_run.add_argument("--output-dir")
    dry_run.set_defaults(handler=_dry_run)

    leaderboard = commands.add_parser("leaderboard", help="Render sanitized public results")
    leaderboard_commands = leaderboard.add_subparsers(dest="leaderboard_command", required=True)
    render = leaderboard_commands.add_parser("render")
    render.add_argument("--input")
    render.add_argument("--output")
    render.set_defaults(handler=_leaderboard_render)

    adapter = commands.add_parser("adapter", help="Work with framework adapters")
    adapter_commands = adapter.add_subparsers(dest="adapter_command", required=True)
    init = adapter_commands.add_parser(
        "init", help="Scaffold a wrapper per topic plus an adapter manifest"
    )
    init.add_argument("--id", required=True, help="two-digit framework id")
    init.add_argument("--name", required=True, help="framework display name")
    init.add_argument("--topics", required=True, help="comma-separated topic ids")
    init.add_argument("--upstream-url", default="https://github.com/OWNER/REPO.git")
    init.add_argument("--license", default="TODO", help="SPDX license identifier")
    init.add_argument("--image", default="TODO:runtime-ready", help="container image tag")
    init.add_argument("--entrypoint", default="TODO", help="native entrypoint command")
    init.add_argument("--out-dir", default=".", help="directory to write into")
    init.add_argument("--force", action="store_true", help="overwrite existing files")
    init.set_defaults(handler=_adapter_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
