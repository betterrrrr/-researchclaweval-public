#!/usr/bin/env python3
"""
Shared AI-Scientist-v2 adapter: patches common to ALL topics and models.

Invoked by the wrapper's FRAMEWORK_RUNTIME_COMMAND as:
    python3 /path/to/patch_ai_scientist_v2_common.py

Environment variables consumed:
    OPENAI_MODEL              — model name to inject
    OPENAI_API_KEY            — API key for the relay
    OPENAI_BASE_URL           — base URL for the relay
    S2_API_KEY                — Semantic Scholar key (optional; placeholder → offline)
    *_NATIVE_RUN=1            — set by each topic wrapper (e.g. TDC_ADMET_TOX_NATIVE_RUN)
"""

from __future__ import annotations

import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
#  Helper: single-occurrence replace with guard
# ──────────────────────────────────────────────────────────────────────────────
def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"AI-Scientist-v2 adapter insertion point changed: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Helper: detect whether the S2 key is a real one or a placeholder
# ──────────────────────────────────────────────────────────────────────────────
def _s2_key_is_placeholder(key: str | None) -> bool:
    if not key:
        return True
    key = key.strip()
    if not key or key.startswith("sk-user-placeholder") or key.startswith("sk-placeholder"):
        return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
#  Robust JSON / action-block parser (extracted from TDC adapter)
# ──────────────────────────────────────────────────────────────────────────────
def _escape_literal_newlines(text: str) -> str:
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch in "\n\r\t":
                out.append({"\\n": "\\\\n", "\\r": "\\\\r", "\\t": "\\\\t"}[ch])
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)
    return "".join(out)


def _scan_json_structure(text: str, stop: int):
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
            if ch == "\\":
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
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def _repair_json(text: str, error_pos: int, message: str) -> str | None:
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
        r"ACTION:\s*([A-Za-z][A-Za-z0-9_]*)\s*ARGUMENTS:\s*",
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


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 1: ideation parser (robust action-block → lenient JSON)
# ──────────────────────────────────────────────────────────────────────────────
def patch_ideation_parser(root: Path) -> None:
    path = root / "ai_scientist/perform_ideation_temp_free.py"

    # 1a. System prompt: enforce mandatory ACTION/ARGUMENTS format
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

    # 1b. Inject helper functions before generate_temp_free_idea
    insertion_point = "\ndef generate_temp_free_idea("
    if text.count(insertion_point) != 1:
        raise SystemExit("AI-Scientist-v2 adapter insertion point changed: action parser helper")
    helper = """
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

"""
    text = text.replace(insertion_point, helper + insertion_point, 1)

    # 1c. Replace the LLM response parsing block with the robust parser
    start_marker = "                # Parse the LLM's response\n"
    end_marker = "\n            if idea_finalized:\n"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    replacement = """                # Parse and execute every complete action emitted by the model.
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
"""
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 2: semantic_scholar — offline/local-catalog bypass + 429 backoff limit
# ──────────────────────────────────────────────────────────────────────────────
def patch_literature(root: Path) -> None:
    s2_path = root / "ai_scientist/tools/semantic_scholar.py"

    s2_text = s2_path.read_text(encoding="utf-8")

    # 2a. use_tool: bypass when S2 key is placeholder
    old = "    def use_tool(self, query: str) -> Optional[str]:\n        papers = self.search_for_papers(query)"
    if old in s2_text:
        new = """    def use_tool(self, query: str) -> Optional[str]:
        s2_key = os.environ.get("S2_API_KEY") or ""
        if not s2_key.strip() or s2_key.strip().startswith("sk-user-placeholder"):
            return (
                "Offline benchmark context: literature search is not available. "
                "Finalize a feasible idea from the supplied task context."
            )
        local_catalog = os.environ.get("AI_SCIENTIST_LOCAL_LITERATURE_CATALOG")
        if local_catalog and Path(local_catalog).is_file():
            return Path(local_catalog).read_text(encoding="utf-8")
        papers = self.search_for_papers(query)"""
        if s2_text.count(old) == 1:
            s2_text = s2_text.replace(old, new, 1)
        else:
            raise SystemExit("AI-Scientist-v2 adapter: semantic_scholar use_tool insertion point changed")
    else:
        raise SystemExit("AI-Scientist-v2 adapter: semantic_scholar use_tool signature not found")

    # 2b. Cap backoff retries for 429
    old_decorator = "@backoff.on_exception(\n        backoff.expo,\n        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),\n        on_backoff=on_backoff,\n    )"
    if old_decorator in s2_text:
        new_decorator = "@backoff.on_exception(\n        backoff.expo,\n        (requests.exceptions.HTTPError, requests.exceptions.ConnectionError),\n        on_backoff=on_backoff,\n        max_tries=5,\n        max_time=120,\n    )"
        s2_text = s2_text.replace(old_decorator, new_decorator, 1)

    s2_path.write_text(s2_text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 3: llm.py — relay + openai error wrapping
# ──────────────────────────────────────────────────────────────────────────────
def patch_llm(root: Path, model: str) -> None:
    path = root / "ai_scientist/llm.py"
    text = path.read_text(encoding="utf-8")

    # 3a. Register the model
    if f'    "{model}",' not in text:
        text = text.replace("AVAILABLE_LLMS = [", f'AVAILABLE_LLMS = [\n    "{model}",', 1)

    # 3b. Replace vanilla OpenAI() with relay client
    text = text.replace(
        "return openai.OpenAI(), model",
        'return openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"]), model',
    )

    # 3c. Wrap all raise-ValueError branches with fallbacks that use the relay
    make_llm_fallback = """    else:
        try:
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
            )
        except openai.OpenAIError as exc:
            raise RuntimeError(f"LLM API error ({type(exc).__name__}): {exc}") from None"""
    text = text.replace(
        '        )\n    \n    else:\n        raise ValueError(f"Model {model} not supported.")',
        '        )\n' + make_llm_fallback,
        1,
    )

    response_fallback = """    else:
        try:
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
            new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]
            return content, new_msg_history
        except openai.OpenAIError as exc:
            raise RuntimeError(f"LLM API error ({type(exc).__name__}): {exc}") from None"""
    text = text.replace(
        '        new_msg_history = new_msg_history + [{"role": "assistant", "content": content}]\n'
        '    else:\n        raise ValueError(f"Model {model} not supported.")',
        response_fallback,
        1,
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
    text = text.replace(
        '            model,\n        )\n    else:\n        raise ValueError(f"Model {model} not supported.")',
        '            model,\n        )\n' + client_fallback,
        1,
    )

    path.write_text(text, encoding="utf-8")

    # 3d. Token tracker None safety
    tracker = root / "ai_scientist/utils/token_tracker.py"
    tracker_text = tracker.read_text(encoding="utf-8")
    tracker_text = tracker_text.replace("+= prompt_tokens", "+= prompt_tokens or 0")
    tracker_text = tracker_text.replace("+= completion_tokens", "+= completion_tokens or 0")
    tracker_text = tracker_text.replace("+= reasoning_tokens", "+= reasoning_tokens or 0")
    tracker_text = tracker_text.replace("+= cached_tokens", "+= cached_tokens or 0")
    tracker.write_text(tracker_text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 4: backend_openai.py — model override, error wrapping
# ──────────────────────────────────────────────────────────────────────────────
def patch_backend(root: Path) -> None:
    backend = root / "ai_scientist/treesearch/backend/backend_openai.py"
    backend_text = backend.read_text(encoding="utf-8")
    if "import os\n" not in backend_text:
        backend_text = backend_text.replace("import logging\n", "import logging\nimport os\n", 1)

    # Override model from env
    old = '    client = get_ai_client(model_kwargs.get("model"), max_retries=0)\n    filtered_kwargs: dict = select_values(notnone, model_kwargs)'
    if old in backend_text:
        new = '    if os.environ.get("OPENAI_MODEL"):\n        model_kwargs["model"] = os.environ["OPENAI_MODEL"]\n    client = get_ai_client(model_kwargs.get("model"), max_retries=0)\n    filtered_kwargs: dict = select_values(notnone, model_kwargs)'
        backend_text = backend_text.replace(old, new, 1)

    # Wrap API errors as RuntimeError (pickle-safe) — for current code that already has BadRequestError handling
    old_2 = "    except openai.BadRequestError as exc:\n        exc_text = str(exc).lower()\n        if (\n            func_spec is not None\n            and \"tool_choice.function\" in exc_text\n            and filtered_kwargs.get(\"tool_choice\") != func_spec.openai_tool_choice_dict\n        ):\n            logger.warning(\n                \"Gateway rejected legacy tool_choice payload for model %s; retrying with OpenAI-standard nested function payload.\",\n                filtered_kwargs.get(\"model\"),\n            )\n            retry_kwargs = dict(filtered_kwargs)\n            retry_kwargs[\"tool_choice\"] = func_spec.openai_tool_choice_dict\n            completion = backoff_create(\n                client.chat.completions.create,\n                OPENAI_TIMEOUT_EXCEPTIONS,\n                messages=messages,\n                **retry_kwargs,\n            )\n            filtered_kwargs = retry_kwargs\n        else:\n            raise\n    req_time = time.time() - t0"
    if old_2 in backend_text:
        new_2 = """    except openai.BadRequestError as exc:
        exc_text = str(exc).lower()
        if (
            func_spec is not None
            and "tool_choice.function" in exc_text
            and filtered_kwargs.get("tool_choice") != func_spec.openai_tool_choice_dict
        ):
            logger.warning(
                "Gateway rejected legacy tool_choice payload for model %s; retrying with OpenAI-standard nested function payload.",
                filtered_kwargs.get("model"),
            )
            retry_kwargs = dict(filtered_kwargs)
            retry_kwargs["tool_choice"] = func_spec.openai_tool_choice_dict
            try:
                completion = backoff_create(
                    client.chat.completions.create,
                    OPENAI_TIMEOUT_EXCEPTIONS,
                    messages=messages,
                    **retry_kwargs,
                )
            except openai.APIStatusError as exc2:
                raise RuntimeError(f"LLM API error ({type(exc2).__name__}): {exc2}") from None
            filtered_kwargs = retry_kwargs
        else:
            raise RuntimeError(f"LLM API error ({type(exc).__name__}): {exc}") from None
    except openai.APIStatusError as exc:
        raise RuntimeError(f"LLM API error ({type(exc).__name__}): {exc}") from None
    req_time = time.time() - t0"""
        backend_text = backend_text.replace(old_2, new_2, 1)
        print("[shared-adapter] P4: backend_openai.py patched (APIStatusError -> RuntimeError)")

    # Also try the original pattern for older code versions
    old = "    t0 = time.time()\n    completion = backoff_create(\n        client.chat.completions.create,\n        OPENAI_TIMEOUT_EXCEPTIONS,\n        messages=messages,\n        **filtered_kwargs,\n    )\n    req_time = time.time() - t0"
    if old in backend_text:
        new = """    t0 = time.time()
    try:
        completion = backoff_create(
            client.chat.completions.create,
            OPENAI_TIMEOUT_EXCEPTIONS,
            messages=messages,
            **filtered_kwargs,
        )
    except openai.APIStatusError as exc:
        raise RuntimeError(f"LLM API error ({type(exc).__name__}): {exc}") from None
    req_time = time.time() - t0"""
        backend_text = backend_text.replace(old, new, 1)

    # Fix function name assertion: use case-insensitive comparison for DeepSeek compatibility
    old_assert = '        assert (\n            choice.message.tool_calls[0].function.name == func_spec.name\n        ), "Function name mismatch"'
    new_assert = """        returned_name = choice.message.tool_calls[0].function.name
        if returned_name != func_spec.name:
            if returned_name.lower() == func_spec.name.lower():
                logger.warning(
                    "Function name case mismatch: returned '%s', expected '%s'. Allowing.",
                    returned_name, func_spec.name,
                )
            else:
                assert False, f"Function name mismatch: returned '{returned_name}', expected '{func_spec.name}'\""""
    if old_assert in backend_text:
        backend_text = backend_text.replace(old_assert, new_assert, 1)
        print("[shared-adapter] P4a: function name assertion relaxed for DeepSeek")
    else:
        # Try alternative formatting (single-line)
        alt_assert = '        assert choice.message.tool_calls[0].function.name == func_spec.name, "Function name mismatch"'
        if alt_assert in backend_text:
            new_alt = """        returned_name = choice.message.tool_calls[0].function.name
        assert returned_name.lower() == func_spec.name.lower(), f"Function name mismatch: returned '{returned_name}', expected '{func_spec.name}'"
        if returned_name != func_spec.name:
            logger.warning("Function name case mismatch: returned '%s', expected '%s'. Allowing.", returned_name, func_spec.name)"""
            backend_text = backend_text.replace(alt_assert, new_alt, 1)
            print("[shared-adapter] P4a: function name assertion relaxed for DeepSeek")

    backend.write_text(backend_text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 5: parallel_agent.py — wrap openai errors in worker callbacks
# ──────────────────────────────────────────────────────────────────────────────
def patch_parallel_agent(root: Path) -> None:
    """Wrap openai.OpenAIError in the worker's step callback so exceptions
    are picklable across the process pool."""
    path = root / "ai_scientist/treesearch/parallel_agent.py"
    text = path.read_text(encoding="utf-8")

    # Add openai import if not present
    if "import openai\n" not in text:
        text = "import openai\n" + text

    # Find each line containing "result_data = future.result(" and wrap it
    # in a try/except that catches openai.OpenAIError.
    # We preserve the exact indentation of the original line.
    import re as _re
    lines = text.split("\n")
    new_lines = []
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("result_data = future.result("):
            indent = line[:len(line) - len(stripped)]
            new_lines.append(f"{indent}try:")
            new_lines.append(f"{indent}    {stripped}")
            new_lines.append(f"{indent}except openai.OpenAIError as exc:")
            new_lines.append(f"{indent}    raise RuntimeError(")
            new_lines.append(f"{indent}        f\"LLM API error in worker ({{type(exc).__name__}}): {{exc}}\"")
            new_lines.append(f"{indent}    ) from None")
        else:
            new_lines.append(line)
    text = "\n".join(new_lines)

    path.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 6: vlm.py — relay support
# ──────────────────────────────────────────────────────────────────────────────
def patch_vlm(root: Path, model: str) -> None:
    vlm = root / "ai_scientist/vlm.py"
    text = vlm.read_text(encoding="utf-8")
    if f'    "{model}",' not in text:
        text = text.replace("AVAILABLE_VLMS = [", f'AVAILABLE_VLMS = [\n    "{model}",', 1)
    old = '        print(f"Using OpenAI API with model {model}.")\n        return openai.OpenAI(), model'
    if old in text:
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
    if old_else in text:
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
        text = text.replace(old_else, new_else, 1)
    vlm.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 7: model routing (log_summarization — hardcoded model name)
# ──────────────────────────────────────────────────────────────────────────────
def patch_model_routing(root: Path, model: str) -> None:
    logsum = root / "ai_scientist/treesearch/log_summarization.py"
    text = logsum.read_text(encoding="utf-8")
    hardcoded = 'model = "gpt-4o-2024-08-06"'
    if text.count(hardcoded) == 2:
        logsum.write_text(
            text.replace(hardcoded, f'model = os.environ.get("OPENAI_MODEL", "{model}")', 2),
            encoding="utf-8",
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 8: generated-program interpreter — set __name__ and __file__
# ──────────────────────────────────────────────────────────────────────────────
def patch_interpreter(root: Path) -> None:
    interpreter = root / "ai_scientist/treesearch/interpreter.py"
    text = interpreter.read_text(encoding="utf-8")
    old = "        global_scope: dict = {}"
    if old in text:
        new = """        global_scope: dict = {
            "__name__": "__main__",
            "__file__": str(self.working_dir / self.agent_file_name),
        }"""
        text = text.replace(old, new, 1)
        interpreter.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Patch 9: write research_idea.json lock after ideation (framework-owned)
# ──────────────────────────────────────────────────────────────────────────────
def patch_research_idea_json(root: Path) -> None:
    """Inject research_idea.json writing into the launcher so the framework
    itself writes the locked idea artifact, not the host."""
    path = root / "launch_scientist_bfts.py"
    text = path.read_text(encoding="utf-8")

    # Insert after "idea = ideas[args.idea_idx]" — the framework's idea loading code
    load_old = "    idea = ideas[args.idea_idx]"
    if load_old in text:
        load_new = """    idea = ideas[args.idea_idx]

    # Framework-owned: write research_idea.json with lock evidence
    _idea = idea if isinstance(idea, dict) else (ideas[0] if isinstance(ideas, list) and ideas else {})
    if isinstance(_idea, dict):
        payload = {
            "hypothesis": _idea.get("Short Hypothesis") or _idea.get("Hypothesis") or _idea.get("Abstract"),
            "method_rationale": _idea.get("Experiments") or [],
            "expected_failure_modes": _idea.get("Risk Factors and Limitations") or _idea.get("Expected Failure Modes") or [],
            "comparison_logic": _idea.get("Experiments") or [],
            "native_idea": _idea,
            "idea_locked": True,
            "locked_at": datetime.now().isoformat(),
        }
        _research_path = os.environ.get("RESEARCH_IDEA_PATH", "/workspace/research_idea.json")
        os.makedirs(os.path.dirname(_research_path), exist_ok=True)
        with open(_research_path, "w") as _f:
            json.dump(payload, _f, ensure_ascii=False, indent=2)
        print(f"Framework wrote research_idea.json lock to {_research_path}")
"""
        text = text.replace(load_old, load_new, 1)
        path.write_text(text, encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
#  Main entry point
# ──────────────────────────────────────────────────────────────────────────────
def main() -> int:
    root = Path.cwd()
    model = os.environ.get("OPENAI_MODEL", "deepseek-v4-flash")

    # P1: Ideation parser (robust)
    patch_ideation_parser(root)
    print("[shared-adapter] P1: ideation parser patched")

    # P2: Literature (offline + 429 capped)
    patch_literature(root)
    print("[shared-adapter] P2: literature patched")

    # P3: LLM (relay + error wrapping)
    patch_llm(root, model)
    print("[shared-adapter] P3: llm.py patched")

    # P4: Backend (model override + error wrapping)
    patch_backend(root)
    print("[shared-adapter] P4: backend_openai.py patched")

    # P5: Parallel agent (openai error wrapping)
    patch_parallel_agent(root)
    print("[shared-adapter] P5: parallel_agent.py patched")

    # P6: VLM (relay)
    patch_vlm(root, model)
    print("[shared-adapter] P6: vlm.py patched")

    # P7: Model routing (log_summarization)
    patch_model_routing(root, model)
    print("[shared-adapter] P7: model routing patched")

    # P8: Interpreter (global scope)
    patch_interpreter(root)
    print("[shared-adapter] P8: interpreter patched")

    # P9: research_idea.json (framework-owned)
    patch_research_idea_json(root)
    print("[shared-adapter] P9: research_idea.json lock injection patched")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())