#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

import yaml


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"AI-Scientist-v2 adapter insertion point changed: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_llm(root: Path, model: str) -> None:
    path = root / "ai_scientist/llm.py"
    text = path.read_text(encoding="utf-8")
    if f'    "{model}",' not in text:
        text = text.replace("AVAILABLE_LLMS = [", f'AVAILABLE_LLMS = [\n    "{model}",', 1)
    text = text.replace(
        "return openai.OpenAI(), model",
        'return openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"]), model',
    )
    path.write_text(text, encoding="utf-8")

    make_llm_fallback = """    else:
        return client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *prompt,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
            stop=None,
            seed=0,
        )"""
    replace_once(
        path,
        '        )\n    \n    else:\n        raise ValueError(f"Model {model} not supported.")',
        '        )\n' + make_llm_fallback,
        "make_llm_call fallback branch",
    )

    response_fallback = """    else:
        new_msg_history = msg_history + [{"role": "user", "content": msg}]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_message},
                *new_msg_history,
            ],
            temperature=temperature,
            max_tokens=MAX_NUM_TOKENS,
            n=1,
            stop=None,
        )
        content = response.choices[0].message.content
        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]"""
    replace_once(
        path,
        '        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]\n'
        '    else:\n        raise ValueError(f"Model {model} not supported.")',
        response_fallback,
        "get_response_from_llm fallback branch",
    )

    client_fallback = """    else:
        print(f"Using OpenAI-compatible relay with model {model}.")
        return (
            openai.OpenAI(
                api_key=os.environ["OPENAI_API_KEY"],
                base_url=os.environ["OPENAI_BASE_URL"],
            ),
            model,
        )"""
    replace_once(
        path,
        '            model,\n        )\n    else:\n        raise ValueError(f"Model {model} not supported.")',
        '            model,\n        )\n' + client_fallback,
        "create_client fallback branch",
    )

    tracker = root / "ai_scientist/utils/token_tracker.py"
    tracker_text = tracker.read_text(encoding="utf-8")
    tracker_text = tracker_text.replace("+= prompt_tokens", "+= prompt_tokens or 0")
    tracker_text = tracker_text.replace("+= completion_tokens", "+= completion_tokens or 0")
    tracker_text = tracker_text.replace("+= reasoning_tokens", "+= reasoning_tokens or 0")
    tracker_text = tracker_text.replace("+= cached_tokens", "+= cached_tokens or 0")
    tracker.write_text(tracker_text, encoding="utf-8")


def patch_literature(root: Path) -> None:
    path = root / "ai_scientist/tools/semantic_scholar.py"
    replace_once(
        path,
        '''    def use_tool(self, query: str) -> Optional[str]:
        papers = self.search_for_papers(query)''',
        '''    def use_tool(self, query: str) -> Optional[str]:
        if os.environ.get("TDC_ADMET_TOX_NATIVE_RUN") == "1":
            return (
                "Offline benchmark context: use the mounted TDC-ADMET-Tox contract, "
                "feature-generation contract, and visible SMILES only."
            )
        papers = self.search_for_papers(query)''',
        "offline literature tool",
    )


def patch_ideation_parser(root: Path) -> None:
    path = root / "ai_scientist/perform_ideation_temp_free.py"
    text = path.read_text(encoding="utf-8")
    replace_once(
        path,
        "Note: You should perform at least one literature search before finalizing your idea to ensure it is well-informed by existing research.\"\"\"",
        "Note: You should perform at least one literature search before finalizing your idea to ensure it is well-informed by existing research.\n\n"
        "MANDATORY OUTPUT FORMAT: Every reply must contain exactly one ACTION block of the form \"ACTION: <name>\\n\\nARGUMENTS:\\n<JSON>\". "
        "Never reply with prose only. If the proposal is ready, always emit \"ACTION: FinalizeIdea\" with the IDEA JSON; otherwise call a tool. "
        "Prefer finalizing by the final reflection round.\"\"\"",
        "ideation system prompt output format",
    )
    replace_once(
        path,
        "Results from your last action (if any):\n\n{last_tool_results}\n\"\"\"",
        "Results from your last action (if any):\n\n{last_tool_results}\n\n"
        "MANDATORY OUTPUT FORMAT: Your reply must contain exactly one ACTION block \"ACTION: <name>\\n\\nARGUMENTS:\\n<JSON>\". "
        "Never reply with prose only. If the proposal is refined and ready, emit \"ACTION: FinalizeIdea\" with the IDEA JSON; "
        "otherwise call a tool to gather more information. Prefer finalizing by the final round.\n\"\"\"",
        "ideation reflection prompt output format",
    )
    text = path.read_text(encoding="utf-8")
    insertion_point = "\ndef generate_temp_free_idea("
    if text.count(insertion_point) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: action parser helper")
    helper = '''
def _escape_literal_newlines(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch in "\\n\\r\\t":
                out.append({"\\n": "\\\\n", "\\r": "\\\\r", "\\t": "\\\\t"}[ch])
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _scan_json_structure(text: str, stop: int):
    """Return (bracket_stack, [(str_start, str_end)], colon_positions) inside text[:stop].

    Bracket stack entries are (char, index); string positions are the quoted
    spans of complete JSON strings; colon positions are structural colons that
    sit outside any string literal. This mirrors how json.JSONDecoder consumes
    the same prefix so bracket repairs land at the right place.
    """
    stack: list[tuple[str, int]] = []
    strings: list[tuple[int, int]] = []
    colons: list[int] = []
    in_string = False
    escaped = False
    str_start = 0
    for index, ch in enumerate(text[:stop]):
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
                strings.append((str_start, index))
            continue
        if ch == '"':
            in_string = True
            str_start = index
            continue
        if ch in "[{":
            stack.append((ch, index))
        elif ch == "]":
            if stack and stack[-1][0] == "[":
                stack.pop()
        elif ch == "}":
            if stack and stack[-1][0] == "{":
                stack.pop()
        elif ch == ":":
            colons.append(index)
    return stack, strings, colons


def _next_nonspace(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \\t\\r\\n":
        index += 1
    return index


def _repair_json(text: str, error_pos: int, message: str) -> str | None:
    """Repair one structural LLM mistake inside an ARGUMENTS JSON block.

    Two recurring failure modes are handled iteratively: an unclosed array
    (elements followed by an object key) and a missing array opener after a
    colon (a bare string sequence). Every insertion point is derived from the
    same bracket/string scan that json.JSONDecoder performs, so repairs never
    move inside a string literal.
    """
    stack, strings, colons = _scan_json_structure(text, error_pos)
    if "Expecting ',' delimiter" in message and stack and stack[-1][0] == "[":
        array_start = stack[-1][1]
        in_array = [(s, e) for s, e in strings if s > array_start]
        for index, (start, end) in enumerate(in_array):
            nxt = _next_nonspace(text, end + 1)
            if nxt < len(text) and text[nxt] == ":" and index > 0:
                _, last_end = in_array[index - 1]
                return text[:last_end + 1] + "]" + text[last_end + 1:]
        if in_array:
            _, last_end = in_array[-1]
            return text[:last_end + 1] + "]" + text[last_end + 1:]
        return None
    if "Expecting ':' delimiter" in message and colons:
        position = colons[-1]
        return text[:position + 1] + "[" + text[position + 1:]
    return None


def _parse_json_lenient(arguments_text: str) -> tuple[dict, int]:
    text = _escape_literal_newlines(arguments_text)
    for _ in range(12):
        try:
            return json.JSONDecoder().raw_decode(text)
        except json.JSONDecodeError as exc:
            repaired = _repair_json(text, exc.pos, exc.msg)
            if repaired is None or repaired == text:
                raise
            text = repaired
    raise json.JSONDecodeError("repair loop exhausted", arguments_text, 0)


def _parse_action_blocks(response_text: str) -> list[tuple[str, dict]]:
    pattern = re.compile(
        r"ACTION:\\s*([A-Za-z][A-Za-z0-9_]*)\\s*ARGUMENTS:\\s*",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(response_text))
    if not matches:
        raise ValueError("Failed to parse the LLM response.")

    decoder = json.JSONDecoder()
    blocks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(response_text)
        arguments_text = response_text[match.end():end].strip()
        if arguments_text.startswith("```json"):
            arguments_text = arguments_text[len("```json"):].lstrip()
        arguments, consumed = _parse_json_lenient(arguments_text)
        if not isinstance(arguments, dict):
            raise ValueError("Arguments must be a JSON object.")
        trailing = arguments_text[consumed:].strip()
        if trailing.startswith("```"):
            trailing = trailing[3:].strip()
        if trailing and not trailing.upper().startswith("THOUGHT:"):
            raise ValueError(f"Unexpected trailing content for {match.group(1)}.")
        blocks.append((match.group(1), arguments))
    return blocks

'''
    text = text.replace(insertion_point, helper + insertion_point, 1)
    start_marker = "                # Parse the LLM's response\n"
    end_marker = "\n            if idea_finalized:\n"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    replacement = '''                # Parse and execute every complete action emitted by the model.
                try:
                    action_blocks = _parse_action_blocks(response_text)
                    for action, arguments_json in action_blocks:
                        print(f"Action: {action}")
                        print(f"Arguments: {json.dumps(arguments_json)}")

                        if action in tools_dict:
                            tool = tools_dict[action]
                            try:
                                result = tool.use_tool(**arguments_json)
                                last_tool_results = result
                            except Exception as exc:
                                last_tool_results = f"Error using tool {action}: {str(exc)}"
                        elif action == "FinalizeIdea":
                            idea = arguments_json.get("idea")
                            if not idea:
                                raise ValueError("Missing 'idea' in arguments.")
                            idea_str_archive.append(json.dumps(idea))
                            print(f"Proposal finalized: {idea}")
                            idea_finalized = True
                            break
                        else:
                            raise ValueError(
                                f"Invalid action {action}. Available actions: {tool_names_str}"
                            )
                    if idea_finalized:
                        break
                except Exception:
                    print(
                        f"Failed to parse LLM response. Response text:\\n{response_text}"
                    )
                    traceback.print_exc()
                    continue
'''
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


def patch_bfts(root: Path, model: str) -> None:
    manager = root / "ai_scientist/treesearch/agent_manager.py"
    manager_text = manager.read_text(encoding="utf-8")
    if "import os\n" not in manager_text:
        manager_text = "import os\n" + manager_text
    old = '''        return task_desc

    def _save_checkpoint(self):'''
    new = '''        if os.environ.get("TDC_ADMET_TOX_NATIVE_RUN") == "1":
            task_desc += """

MANDATORY TDC-ADMET-TOX NATIVE CONTRACT:
- The framework must propose and complete 2 to 4 materially distinct molecular-ML configurations using only visible SMILES and installed libraries.
- Each validation candidate counts as one configuration and every trace record has candidate_count=1. Never evaluate a fifth candidate.
- Use /data/tdc_admet_tox/train.csv and validation.csv for development. test.csv is unlabeled and selection uses validation macro AUROC only.
- Use /workspace/automation/scripts/run_tdc_admet_tox_validation_score.py for each complete configuration.
- RDKit is not installed. Do not install packages, download assets, access public internet, use remote chemistry services, or launch background experiments.
- The generated runnable program itself must write /workspace/predictions.csv, experiment_trace.json, environment.json, non-empty logs, configs, validation metrics, and paper.md. It must not create score.json.
- predictions.csv must contain EXACTLY the same (sample_id, endpoint) rows as the visible /data/tdc_admet_tox/test.csv. Read /data/tdc_admet_tox/test.csv with csv.DictReader and build the exact list of (sample_id, endpoint) rows; then generate one probability FOR EACH OF THOSE ROWS ONLY and write only those rows. Do NOT generate three rows per sample_id and do NOT create rows for endpoints that are absent from /data/tdc_admet_tox/test.csv. Every sample_id appears exactly once in test.csv with its assigned endpoint; there are 1,685 rows. Header must be sample_id,endpoint,probability. Never emit smiles, pred, score, label, or y columns.
- Every empirical paper number needs an inline claim marker resolving through the trace to a concrete run.
- Record framework_native_execution=true, consumed_topic_input=true, framework_internal_model from OPENAI_MODEL, and framework_internal_api_base_url from OPENAI_BASE_URL.
- /workspace/experiment_trace.json MUST be a single JSON object that follows the host evaluation schema, not a framework-internal format. Required top-level fields: task_id="tdc_admet_tox", framework_native_execution=true, consumed_topic_input=true, framework_internal_model from OPENAI_MODEL, framework_internal_api_base_url from OPENAI_BASE_URL, selection_metric="validation_macro_average_auroc", final_prediction_file="predictions.csv", selected_experiment_id=<best experiment run_id>, total_wall_seconds=<numeric <=7200>, resource_budget={"cpu_cores":4,"memory_gib":16,"gpu_count":0,"workspace_disk_gib":10,"max_experiment_runtime_seconds":3600,"max_total_wall_seconds":7200,"network_policy":"injected_llm_relay_only"}, environment_file="environment.json", reproduction={"entrypoint":<relative path to the runnable experiment program>, "command":<reproduction command string>, "seed":<integer>}, experiments=<list of 2 to 4 experiment objects>, claims=<list of claim objects>.
- Each object in experiments must contain: run_id, status="complete", hypothesis, model_strategy, feature_strategy, config_file, prediction_file, metrics_file, log_file (those four MUST be RELATIVE paths inside /workspace, never absolute /workspace/... paths), runtime_seconds, seed (integer), candidate_count=1, validation_metrics={"macro_average_auroc":<float>, "per_endpoint":{"AMES":{"auroc":<float>},"hERG":{"auroc":<float>},"DILI":{"auroc":<float>}}}. For the 3rd and 4th experiments include parent_run_id and change_rationale. Each experiment must be one complete configuration; never store epochs, candidates, or repeated evaluations as separate list entries.
- The experiments list must contain between 2 and 4 entries total. selected_experiment_id must be the experiment with the highest validation_metrics.macro_average_auroc.
- /workspace/environment.json MUST be a JSON object with non-empty fields: python_version (use sys.version), platform (use platform.platform()), device ("cpu"), seeds (a non-empty list of the integer seed(s) used), packages (a JSON object mapping at least the installed packages you used (e.g. numpy, pandas, scikit-learn, torch) to their version strings), created_at (a timezone-aware ISO timestamp). Do not use "python" instead of "python_version".
- After the experiments are complete, copy your final runnable experiment program to `/workspace/experiment.py` (the root of the workspace). In the trace set `reproduction.entrypoint` to "experiment.py" and `reproduction.command` to "python3 experiment.py". Never point reproduction.entrypoint at a filename that does not exist.
- Every per-run metrics.json (and any metrics file referenced by claims) must be a JSON object with the exact field "split":"validation" alongside macro_average_auroc and per_endpoint metrics. Never omit or rename that field. validation_metrics in the trace must reproduce its metrics.json values exactly, unrounded.
- Each object in claims must contain: claim_id, endpoint, metric, value, source_run_id, prediction_file, config_file, log_file. claim_id is the part inside the paper marker <!-- claim:<claim_id> -->. endpoint must be one of "AMES", "hERG", "DILI", or "macro". metric must be one of the exact strings "auroc", "auprc", "average_precision", "brier", "brier_score", "ece", "ece_10_bin", "runtime_seconds"; for validation AUROC claims use metric "auroc" and never write "validation AUROC" or "validation macro-average AUROC". value must exactly equal the unrounded source metric from the source experiment metrics.json. prediction_file, config_file, and log_file must be the same relative paths as the source experiment.
- paper.md must include at least one claim marker <!-- claim:<claim_id> --> inline with each quantitative empirical number, and every claim in the trace must be referenced at least once in paper.md.
- Before writing the final handoff, the generated runnable program MUST run exactly this command and keep fixing every reported error inside the generated program until it exits 0:
    python3 /workspace/automation/scripts/validate_tdc_admet_tox_run.py --workspace /workspace --stage framework --public-dataset-root /data/tdc_admet_tox
  The handoff is not complete until that exact command exits 0. Do not omit `--workspace /workspace`.
- Never write /workspace/score.json or mention hidden test labels.
"""
        return task_desc

    def _save_checkpoint(self):'''
    if manager_text.count(old) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: task contract")
    manager_text = manager_text.replace(old, new, 1)
    old = '''        journal = self.journals[stage.name]
        # Terminate if max iterations reached'''
    new = '''        journal = self.journals[stage.name]
        if os.environ.get("TDC_ADMET_TOX_NATIVE_RUN") == "1" and stage.stage_number == 1:
            handoff_complete = all(
                Path("/workspace", name).is_file()
                for name in ("predictions.csv", "experiment_trace.json", "environment.json", "paper.md")
            ) and Path("/workspace/logs").is_dir() and not Path("/workspace/score.json").exists()
            if handoff_complete and len(journal.good_nodes) > 0:
                # Validate predictions.csv schema
                pred_path = Path("/workspace/predictions.csv")
                if pred_path.is_file():
                    try:
                        first_line = pred_path.read_text(encoding="utf-8").split("\\n")[0].strip()
                        expected_header = "sample_id,endpoint,probability"
                        if first_line != expected_header:
                            print(f"TDC completion gate: predictions.csv has wrong header '{first_line}', expected '{expected_header}'")
                            handoff_complete = False
                    except Exception as exc:
                        print(f"TDC completion gate: cannot read predictions.csv: {exc}")
                        handoff_complete = False
                if handoff_complete:
                    self.current_stage = None
                    return True, "Completed native TDC-ADMET-Tox handoff"
        # Terminate if max iterations reached'''
    if manager_text.count(old) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: completion gate")
    manager.write_text(manager_text.replace(old, new, 1), encoding="utf-8")

    # Backend-openai patches (model override, error wrapping) are now handled by
    # the shared adapter (patch_ai_scientist_v2_common.py). Skip them here.
    # Interpreter global_scope patch is also handled by the shared adapter.

    config_path = root / "bfts_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["data_dir"] = "/data/tdc_admet_tox"
    config["copy_data"] = False
    config["exec"]["timeout"] = 3600
    config["agent"]["num_workers"] = 1
    config["agent"]["steps"] = 4
    config["agent"]["stages"] = {
        "stage1_max_iters": 4,
        "stage2_max_iters": 1,
        "stage3_max_iters": 1,
        "stage4_max_iters": 1,
    }
    config["agent"]["multi_seed_eval"]["num_seeds"] = 1
    config["agent"]["code"]["model"] = model
    config["agent"]["feedback"]["model"] = model
    config["agent"]["vlm_feedback"]["model"] = model
    config["report"]["model"] = model
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


def patch_model_routing(root: Path, model: str) -> None:
    logsum = root / "ai_scientist/treesearch/log_summarization.py"
    text = logsum.read_text(encoding="utf-8")
    hardcoded = 'model = "gpt-4o-2024-08-06"'
    if text.count(hardcoded) != 2:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: summary model fallback")
    logsum.write_text(
        text.replace(hardcoded, f'model = os.environ.get("OPENAI_MODEL", "{model}")', 2),
        encoding="utf-8",
    )

    vlm = root / "ai_scientist/vlm.py"
    text = vlm.read_text(encoding="utf-8")
    if f'    "{model}",' not in text:
        text = text.replace("AVAILABLE_VLMS = [", f'AVAILABLE_VLMS = [\n    "{model}",', 1)
    old = '        print(f"Using OpenAI API with model {model}.")\n        return openai.OpenAI(), model'
    if text.count(old) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: vlm client")
    text = text.replace(
        old,
        '        print(f"Using OpenAI-compatible relay with model {model}.")\n'
        '        return (\n'
        '            openai.OpenAI(\n'
        '                api_key=os.environ["OPENAI_API_KEY"],\n'
        '                base_url=os.environ["OPENAI_BASE_URL"],\n'
        "            ),\n"
        "            model,\n"
        "        )",
        1,
    )
    old_else = (
        "    else:\n"
        "        raise ValueError(f\"Model {model} not supported.\")\n"
        "\n"
        "\n"
        "def extract_json_between_markers(llm_output: str) -> dict | None:"
    )
    new_else = (
        "    else:\n"
        '        print(f"Using OpenAI-compatible relay with model {model}.")\n'
        "        return (\n"
        "            openai.OpenAI(\n"
        '                api_key=os.environ["OPENAI_API_KEY"],\n'
        '                base_url=os.environ["OPENAI_BASE_URL"],\n'
        "            ),\n"
        "            model,\n"
        "        )\n"
        "\n"
        "\n"
        "def extract_json_between_markers(llm_output: str) -> dict | None:"
    )
    if text.count(old_else) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: vlm create_client else")
    text = text.replace(old_else, new_else, 1)
    vlm.write_text(text, encoding="utf-8")


def patch_summary_stage_padding(root: Path) -> None:
    """Keep the native summary shape valid when the bounded run has one stage."""
    path = root / "ai_scientist/treesearch/log_summarization.py"
    old = (
        "        )\n"
        "        draft_summary, baseline_summary, research_summary, ablation_summary = results\n\n"
        "    return draft_summary, baseline_summary, research_summary, ablation_summary\n"
    )
    new = (
        "        )\n"
        "        if os.environ.get(\"TDC_ADMET_TOX_NATIVE_RUN\") == \"1\":\n"
        "            results.extend([{} for _ in range(max(0, 4 - len(results)))])\n"
        "        draft_summary, baseline_summary, research_summary, ablation_summary = results[:4]\n\n"
        "    return draft_summary, baseline_summary, research_summary, ablation_summary\n"
    )
    replace_once(path, old, new, "summary stage padding")


def patch_launcher(root: Path) -> None:
    path = root / "launch_scientist_bfts.py"
    old = '''    perform_experiments_bfts(idea_config_path)
    experiment_results_dir = osp.join(idea_dir, "logs/0-run/experiment_results")'''
    new = '''    perform_experiments_bfts(idea_config_path)
    if os.environ.get("TDC_ADMET_TOX_NATIVE_RUN") == "1":
        required = (
            "/workspace/predictions.csv",
            "/workspace/experiment_trace.json",
            "/workspace/environment.json",
            "/workspace/paper.md",
        )
        missing = [item for item in required if not os.path.isfile(item)]
        if missing or os.path.exists("/workspace/score.json"):
            raise RuntimeError(
                "Native TDC-ADMET-Tox BFTS exited without a valid framework handoff: "
                + ", ".join(missing or ["framework-created score.json"])
            )
        save_token_tracker(idea_dir)
        raise SystemExit(0)
    experiment_results_dir = osp.join(idea_dir, "logs/0-run/experiment_results")'''
    replace_once(path, old, new, "native root handoff")


def main() -> int:
    root = Path.cwd()
    model = os.environ["OPENAI_MODEL"]
    # Common patches (ideation parser, literature, llm, vlm, backend, parallel_agent,
    # model_routing, interpreter, research_idea_json) are now handled by
    # real_eval/adapters/ai_scientist_v2/patch_ai_scientist_v2_common.py.
    # Only TDC-specific patches remain:
    patch_bfts(root, model)
    patch_summary_stage_padding(root)
    patch_launcher(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
