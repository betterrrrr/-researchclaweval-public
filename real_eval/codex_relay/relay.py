from __future__ import annotations

import hmac
import json
import logging
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

CHAT_COMPLETION_PATHS = {"/chat/completions", "/v1/chat/completions"}
RESPONSES_PATHS = {"/responses", "/v1/responses"}
logger = logging.getLogger(__name__)


def normalize_model_name(model: str) -> str:
    if model.startswith(("openai/kimi", "openai/deepseek")):
        return model.removeprefix("openai/")
    return model


def normalize_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    model = normalized.get("model")
    if isinstance(model, str):
        normalized["model"] = normalize_model_name(model)

    if _is_kimi_model(normalized.get("model")):
        if normalized.get("tool_choice") == "required":
            normalized["tool_choice"] = "auto"
        if normalized.get("temperature") == 0:
            normalized["temperature"] = 1
        if normalized.get("response_format") is not None:
            logger.warning(
                "Kimi compatibility: stripping response_format=%s "
                "(not supported by upstream API)",
                normalized["response_format"],
            )
            del normalized["response_format"]

    tool_choice = normalized.get("tool_choice")
    if _is_bianxie_deepseek_v4_flash(normalized.get("model")) and _is_forced_tool_choice(
        tool_choice
    ):
        normalized["tool_choice"] = "auto"
        tool_choice_kind = "required" if tool_choice == "required" else "named_function"
        logger.warning(
            "DeepSeek compatibility rewrite: provider=bianxie model=deepseek-v4-flash "
            "tool_choice=%s->auto tools_count=%d stream=%s "
            "reason=bianxie_required_timeout_or_thinking_mode_incompatible",
            tool_choice_kind,
            len(normalized.get("tools") or []),
            normalized.get("stream"),
        )

    messages = normalized.get("messages")
    if isinstance(messages, list):
        normalized["messages"] = _drop_unmatched_tool_messages(messages)

    return normalized


def _is_kimi_model(model: Any) -> bool:
    return isinstance(model, str) and normalize_model_name(model).startswith("kimi")


def _is_bianxie_deepseek_v4_flash(model: Any) -> bool:
    return (
        os.environ.get("RELAY_UPSTREAM_PROVIDER", "").strip().lower() == "bianxie"
        and isinstance(model, str)
        and normalize_model_name(model).lower() == "deepseek-v4-flash"
    )


def _is_forced_tool_choice(tool_choice: Any) -> bool:
    if tool_choice == "required":
        return True
    if not isinstance(tool_choice, dict) or tool_choice.get("type") != "function":
        return False
    function = tool_choice.get("function")
    return isinstance(function, dict) and isinstance(function.get("name"), str)


def _sanitize_request_path(request_target: str) -> str:
    parsed = urlsplit(request_target)
    if parsed.scheme or parsed.netloc:
        path = parsed.path
    else:
        path = request_target.split("?", 1)[0]
    return path.rstrip("/") or "/"


def _drop_unmatched_tool_messages(messages: list[Any]) -> list[Any]:
    known_tool_call_ids: set[str] = set()
    kept_messages: list[Any] = []

    for message in messages:
        if not isinstance(message, dict):
            kept_messages.append(message)
            continue

        tool_calls = message.get("tool_calls")
        if message.get("role") == "assistant" and isinstance(tool_calls, list):
            for tool_call in tool_calls:
                if isinstance(tool_call, dict) and isinstance(tool_call.get("id"), str):
                    known_tool_call_ids.add(tool_call["id"])

        if message.get("role") == "tool":
            tool_call_id = message.get("tool_call_id")
            if not isinstance(tool_call_id, str) or tool_call_id not in known_tool_call_ids:
                continue

        kept_messages.append(message)

    return kept_messages


def _responses_payload_to_chat(payload: dict[str, Any]) -> dict[str, Any]:
    chat_payload: dict[str, Any] = {}
    model = payload.get("model")
    if model is not None:
        chat_payload["model"] = model
    instructions = payload.get("instructions")
    input_value = payload.get("input")
    if "messages" in payload:
        chat_payload["messages"] = deepcopy(payload["messages"])
    else:
        chat_payload["messages"] = _responses_input_to_messages(instructions, input_value)

    tools = _translate_responses_tools(payload.get("tools"))
    if tools:
        chat_payload["tools"] = tools

    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        function_name = tool_choice.get("name")
        if isinstance(function_name, str) and function_name:
            chat_payload["tool_choice"] = {
                "type": "function",
                "function": {"name": function_name},
            }
        else:
            chat_payload["tool_choice"] = "auto"
    elif tool_choice is not None:
        chat_payload["tool_choice"] = deepcopy(tool_choice)

    for key in (
        "temperature",
        "max_output_tokens",
        "top_p",
        "frequency_penalty",
        "presence_penalty",
    ):
        if key in payload:
            chat_payload[key] = deepcopy(payload[key])

    chat_payload["stream"] = False
    return chat_payload


def _input_to_messages(input_value: Any) -> list[dict[str, Any]]:
    if isinstance(input_value, str):
        return [{"role": "user", "content": input_value}]
    if isinstance(input_value, list):
        messages: list[dict[str, Any]] = []
        for item in input_value:
            if isinstance(item, dict) and "role" in item:
                messages.append(dict(item))
            elif isinstance(item, str):
                messages.append({"role": "user", "content": item})
        if messages:
            return messages
    return [{"role": "user", "content": input_value}]


def _responses_input_to_messages(instructions: Any, input_value: Any) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    if isinstance(input_value, list):
        for item in input_value:
            if not isinstance(item, dict):
                if isinstance(item, str):
                    messages.append({"role": "user", "content": item})
                continue
            item_type = item.get("type")
            if item_type == "message":
                role = item.get("role", "user")
                content = _extract_text_blocks(item.get("content"))
                if content:
                    messages.append({"role": "system" if role == "developer" else role, "content": content})
                continue
            if item_type == "function_call":
                name = str(item.get("name") or "").strip()
                namespace = str(item.get("namespace") or "").strip()
                if namespace and name and not name.startswith(namespace):
                    name = f"{namespace}{name}"
                if not name:
                    continue
                arguments = str(item.get("arguments") or "")
                call_id = str(item.get("call_id") or f"call_{uuid.uuid4().hex}")
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {"name": name, "arguments": arguments},
                            }
                        ],
                    }
                )
                continue
            if item_type == "function_call_output":
                call_id = str(item.get("call_id") or "").strip()
                if not call_id:
                    continue
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(item.get("output") or ""),
                    }
                )
                continue
            if item_type == "custom":
                name = str(item.get("name") or "").strip()
                call_id = str(item.get("call_id") or f"call_{uuid.uuid4().hex}")
                if "output" in item:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": str(item.get("output") or ""),
                        }
                    )
                else:
                    arguments = item.get("arguments")
                    if isinstance(arguments, str):
                        arguments_str = arguments
                    elif arguments is not None:
                        arguments_str = json.dumps(arguments, ensure_ascii=False)
                    else:
                        arguments_str = ""
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": call_id,
                                    "type": "function",
                                    "function": {"name": name, "arguments": arguments_str},
                                }
                            ],
                        }
                    )
                continue
            if item_type == "reasoning":
                continue
            if "role" in item:
                messages.append(dict(item))
        return messages

    if input_value is not None:
        messages.extend(_input_to_messages(input_value))
    return messages


def _extract_text_blocks(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "")
        if block_type in {"input_text", "output_text", "text"}:
            text = str(block.get("text") or "")
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _translate_responses_tools(tools: Any) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return translated
    for item in tools:
        if not isinstance(item, dict):
            continue
        tool_type = str(item.get("type") or "")
        name = str(item.get("name") or "").strip()
        if tool_type == "function":
            if not name:
                continue
            translated.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(item.get("description") or ""),
                        "parameters": item.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
            )
            continue
        if tool_type == "custom":
            if not name:
                continue
            translated.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": str(item.get("description") or ""),
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
            continue
        if tool_type == "namespace":
            namespace_name = name
            if not namespace_name:
                continue
            for sub_tool in item.get("tools") or []:
                if not isinstance(sub_tool, dict):
                    continue
                sub_name = str(sub_tool.get("name") or "").strip()
                if not sub_name:
                    continue
                separator = "__" if not namespace_name.endswith("_") else ""
                translated.append(
                    {
                        "type": "function",
                        "function": {
                            "name": f"{namespace_name}{separator}{sub_name}",
                            "description": str(sub_tool.get("description") or ""),
                            "parameters": sub_tool.get("parameters")
                            or {"type": "object", "properties": {}},
                        },
                    }
                )
    return translated


def _translate_chat_tools(tools: Any) -> list[dict[str, Any]]:
    translated: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return translated
    for item in tools:
        if not isinstance(item, dict) or item.get("type") != "function":
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        translated.append(
            {
                "type": "function",
                "name": name,
                "description": str(function.get("description") or ""),
                "parameters": function.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return translated


def _chat_payload_to_responses(payload: dict[str, Any]) -> dict[str, Any]:
    response_payload: dict[str, Any] = {"model": payload.get("model"), "stream": False}
    messages = payload.get("messages")
    instructions: list[str] = []
    input_items: list[dict[str, Any]] = []
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "user")
            content = message.get("content")
            if role in {"system", "developer"}:
                text = _extract_text_blocks(content) if isinstance(content, list) else str(content or "")
                if text.strip():
                    instructions.append(text.strip())
                continue
            if role == "tool":
                call_id = str(message.get("tool_call_id") or "").strip()
                if call_id:
                    input_items.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": str(content or ""),
                        }
                    )
                continue
            if content not in (None, "", []):
                input_items.append({"role": role, "content": deepcopy(content)})
            tool_calls = message.get("tool_calls")
            if role == "assistant" and isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    if not isinstance(tool_call, dict):
                        continue
                    function = tool_call.get("function")
                    if not isinstance(function, dict):
                        continue
                    name = str(function.get("name") or "").strip()
                    if name:
                        input_items.append(
                            {
                                "type": "function_call",
                                "call_id": str(
                                    tool_call.get("id") or f"call_{uuid.uuid4().hex}"
                                ),
                                "name": name,
                                "arguments": str(function.get("arguments") or ""),
                            }
                        )
    response_payload["input"] = input_items or [{"role": "user", "content": ""}]
    if instructions:
        response_payload["instructions"] = "\n\n".join(instructions)
    tools = _translate_chat_tools(payload.get("tools"))
    if tools:
        response_payload["tools"] = tools
    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        function = tool_choice.get("function")
        if isinstance(function, dict) and function.get("name"):
            response_payload["tool_choice"] = {
                "type": "function",
                "name": function["name"],
            }
    elif tool_choice is not None:
        response_payload["tool_choice"] = deepcopy(tool_choice)
    for source, target in (
        ("temperature", "temperature"),
        ("top_p", "top_p"),
        ("max_tokens", "max_output_tokens"),
        ("max_completion_tokens", "max_output_tokens"),
    ):
        if source in payload:
            response_payload[target] = deepcopy(payload[source])
    return response_payload


def _responses_payload_to_chat_completion(
    request_payload: dict[str, Any], response_payload: dict[str, Any]
) -> dict[str, Any]:
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    output = response_payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                text = _extract_text_blocks(item.get("content"))
                if text:
                    content_parts.append(text)
            elif item.get("type") == "function_call":
                name = str(item.get("name") or "").strip()
                if name:
                    tool_calls.append(
                        {
                            "id": str(item.get("call_id") or f"call_{uuid.uuid4().hex}"),
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": str(item.get("arguments") or ""),
                            },
                        }
                    )
            elif item.get("type") == "custom":
                name = str(item.get("name") or "").strip()
                if name:
                    arguments = item.get("arguments")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments, ensure_ascii=False) if arguments is not None else ""
                    tool_calls.append(
                        {
                            "id": str(item.get("call_id") or f"call_{uuid.uuid4().hex}"),
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    )
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(content_parts) if content_parts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    usage = response_payload.get("usage")
    chat_usage = {}
    if isinstance(usage, dict):
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        chat_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": int(usage.get("total_tokens") or prompt_tokens + completion_tokens),
        }
    return {
        "id": str(response_payload.get("id") or f"chatcmpl_{uuid.uuid4().hex}"),
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": response_payload.get("model") or request_payload.get("model"),
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": chat_usage,
    }


def _chat_completion_stream(payload: dict[str, Any]) -> bytes:
    choice = payload["choices"][0]
    delta = deepcopy(choice["message"])
    chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": choice["finish_reason"],
            }
        ],
    }
    return (
        "data: "
        + json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
        + "\n\ndata: [DONE]\n\n"
    ).encode("utf-8")


def _chunk_text(text: str, *, chunk_size: int = 48) -> list[str]:
    return [text[index : index + chunk_size] for index in range(0, len(text), chunk_size)] if text else []


class ResponsesEventBuilder:
    def __init__(self, *, request_body: dict[str, Any]) -> None:
        self.request_body = deepcopy(request_body)
        self.response_id = f"resp_{uuid.uuid4().hex}"
        self.created_at_epoch = int(datetime.now(timezone.utc).timestamp())
        self.sequence = 1
        self.output_items: list[dict[str, Any]] = []
        self.events: list[str] = []

    def start(self) -> None:
        self._emit("response.created", {"type": "response.created", "response": self.response_payload("in_progress")})

    def add_message(self, *, text: str, phase: str = "final_answer") -> None:
        if not text:
            return
        item_id = f"msg_{uuid.uuid4().hex}"
        output_index = len(self.output_items)
        item_payload = {
            "id": item_id,
            "type": "message",
            "status": "completed",
            "content": [{"type": "output_text", "annotations": [], "logprobs": [], "text": text}],
            "phase": phase,
            "role": "assistant",
        }
        self.output_items.append(item_payload)
        self._emit(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "id": item_id,
                    "type": "message",
                    "status": "in_progress",
                    "content": [],
                    "phase": phase,
                    "role": "assistant",
                },
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )
        self._emit(
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "content_index": 0,
                "item_id": item_id,
                "output_index": output_index,
                "part": {"type": "output_text", "annotations": [], "logprobs": [], "text": ""},
                "sequence_number": self._next_sequence(),
            },
        )
        for chunk in _chunk_text(text):
            self._emit(
                "response.output_text.delta",
                {
                    "type": "response.output_text.delta",
                    "content_index": 0,
                    "delta": chunk,
                    "item_id": item_id,
                    "logprobs": [],
                    "output_index": output_index,
                    "sequence_number": self._next_sequence(),
                },
            )
        self._emit(
            "response.output_text.done",
            {
                "type": "response.output_text.done",
                "content_index": 0,
                "item_id": item_id,
                "logprobs": [],
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
                "text": text,
            },
        )
        self._emit(
            "response.content_part.done",
            {
                "type": "response.content_part.done",
                "content_index": 0,
                "item_id": item_id,
                "output_index": output_index,
                "part": {"type": "output_text", "annotations": [], "logprobs": [], "text": text},
                "sequence_number": self._next_sequence(),
            },
        )
        self._emit(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": item_payload,
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )

    def add_custom_tool_call(self, *, name: str, call_id: str, arguments: Any) -> None:
        item_id = f"ct_{uuid.uuid4().hex}"
        output_index = len(self.output_items)
        if isinstance(arguments, str):
            try:
                parsed_arguments: Any = json.loads(arguments) if arguments.strip() else {}
            except Exception:
                parsed_arguments = arguments
        else:
            parsed_arguments = arguments or {}
        item_payload = {
            "id": item_id,
            "type": "custom",
            "call_id": call_id,
            "name": name,
            "arguments": parsed_arguments,
            "status": "completed",
        }
        self.output_items.append(item_payload)
        self._emit(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "id": item_id,
                    "type": "custom",
                    "call_id": call_id,
                    "name": name,
                    "arguments": parsed_arguments,
                    "status": "in_progress",
                },
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )
        self._emit(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": item_payload,
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )

    def add_function_call(self, *, name: str, call_id: str, arguments: str, namespace: str = "") -> None:
        item_id = f"fc_{uuid.uuid4().hex}"
        output_index = len(self.output_items)
        item_payload: dict[str, Any] = {
            "id": item_id,
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
        }
        if namespace:
            item_payload["namespace"] = namespace
        self.output_items.append(item_payload)
        started_payload: dict[str, Any] = {
            "id": item_id,
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "arguments": "",
        }
        if namespace:
            started_payload["namespace"] = namespace
        self._emit(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": started_payload,
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )
        for chunk in _chunk_text(arguments, chunk_size=32):
            self._emit(
                "response.function_call_arguments.delta",
                {
                    "type": "response.function_call_arguments.delta",
                    "delta": chunk,
                    "item_id": item_id,
                    "output_index": output_index,
                    "sequence_number": self._next_sequence(),
                },
            )
        self._emit(
            "response.function_call_arguments.done",
            {
                "type": "response.function_call_arguments.done",
                "arguments": arguments,
                "item_id": item_id,
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )
        self._emit(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "item": item_payload,
                "output_index": output_index,
                "sequence_number": self._next_sequence(),
            },
        )

    def complete_stream(self) -> bytes:
        self._emit("response.completed", {"type": "response.completed", "response": self.response_payload("completed")})
        self.events.append("data: [DONE]\n\n")
        return "".join(self.events).encode("utf-8")

    def response_payload(self, status: str) -> dict[str, Any]:
        tools = self.request_body.get("tools")
        translated_tools = [item for item in (tools if isinstance(tools, list) else []) if isinstance(item, dict)]
        return {
            "id": self.response_id,
            "object": "response",
            "created_at": self.created_at_epoch,
            "status": status,
            "completed_at": self.created_at_epoch if status == "completed" else None,
            "error": None,
            "instructions": self.request_body.get("instructions"),
            "model": self.request_body.get("model"),
            "output": deepcopy(self.output_items),
            "parallel_tool_calls": bool(self.request_body.get("parallel_tool_calls", True)),
            "previous_response_id": self.request_body.get("previous_response_id"),
            "reasoning": self.request_body.get("reasoning"),
            "store": bool(self.request_body.get("store", False)),
            "text": self.request_body.get("text") or {"format": {"type": "text"}, "verbosity": "low"},
            "tool_choice": self.request_body.get("tool_choice") or "auto",
            "tools": translated_tools,
            "usage": None,
            "metadata": {},
        }

    def _emit(self, event_name: str, payload: dict[str, Any]) -> None:
        self.events.append(f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n")

    def _next_sequence(self) -> int:
        value = self.sequence
        self.sequence += 1
        return value


def _build_responses_output(request_payload: dict[str, Any], upstream_payload: dict[str, Any]) -> ResponsesEventBuilder:
    builder = ResponsesEventBuilder(request_body=request_payload)
    builder.start()
    choices = upstream_payload.get("choices") if isinstance(upstream_payload.get("choices"), list) else []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    if not isinstance(message, dict):
        message = {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        builder.add_message(text=content.strip(), phase="final_answer")
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        call_id = str(tool_call.get("id") or f"call_{uuid.uuid4().hex}")
        arguments = str(function.get("arguments") or "")
        if name.startswith("mcp__") and "__" in name[len("mcp__"):]:
            rest = name[len("mcp__"):]
            server_part, _, tool_part = rest.partition("__")
            if server_part and tool_part:
                builder.add_function_call(
                    name=tool_part,
                    call_id=call_id,
                    arguments=arguments,
                    namespace=f"mcp__{server_part}__",
                )
                continue
        if name.startswith("mcp__"):
            builder.add_custom_tool_call(name=name, call_id=call_id, arguments=arguments)
        else:
            builder.add_function_call(name=name, call_id=call_id, arguments=arguments)
    return builder


class RelayHandler(BaseHTTPRequestHandler):
    server_version = "KimiRelay/1.0"

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = _sanitize_request_path(self.path)
        if path not in CHAT_COMPLETION_PATHS and path not in RESPONSES_PATHS:
            self._send_json(404, {"error": "not found"})
            return
        expected_api_key = os.environ.get("RELAY_CLIENT_API_KEY")
        if expected_api_key:
            authorization = self.headers.get("Authorization", "")
            if not hmac.compare_digest(authorization, f"Bearer {expected_api_key}"):
                self._send_json(401, {"error": "unauthorized"})
                return

        try:
            payload = self._read_json()
            upstream_wire_api = os.environ.get("RELAY_UPSTREAM_WIRE_API", "chat").strip().lower()
            logger.info(
                "relay_request path=%s model=%s upstream_wire_api=%s",
                path,
                payload.get("model"),
                upstream_wire_api,
            )
            if upstream_wire_api == "responses":
                if path in RESPONSES_PATHS:
                    status, body, content_type = _forward_responses_completion(payload)
                    logger.info("relay_response path=%s status=%s", path, status)
                    self._send_bytes(status, body, content_type)
                    return
                request_stream = payload.get("stream") is True
                responses_request = normalize_request_payload(
                    _chat_payload_to_responses(payload)
                )
                status, body, _ = _forward_responses_completion(responses_request)
                logger.info("relay_response path=%s status=%s", path, status)
                if status >= 400:
                    self._send_bytes(status, body, "application/json")
                    return
                upstream_payload = json.loads(body.decode("utf-8"))
                chat_payload = _responses_payload_to_chat_completion(payload, upstream_payload)
                if request_stream:
                    self._send_bytes(
                        200,
                        _chat_completion_stream(chat_payload),
                        "text/event-stream; charset=utf-8",
                    )
                else:
                    self._send_json(200, chat_payload)
                return
            if path in RESPONSES_PATHS:
                request_payload = deepcopy(payload)
                payload = _responses_payload_to_chat(payload)
                normalized = normalize_request_payload(payload)
                status, body, _ = _forward_chat_completion(normalized)
                logger.info("relay_response path=%s status=%s", path, status)
                if status >= 400:
                    self._send_bytes(status, body, "application/json")
                    return
                upstream_payload = json.loads(body.decode("utf-8"))
                _debug_upstream_summary(path, request_payload, upstream_payload)
                builder = _build_responses_output(request_payload, upstream_payload)
                if request_payload.get("stream") is True:
                    self._send_bytes(200, builder.complete_stream(), "text/event-stream; charset=utf-8")
                    return
                response_payload = builder.response_payload("completed")
                self._send_json(200, response_payload)
                return
            normalized = normalize_request_payload(payload)
            status, body, content_type = _forward_chat_completion(normalized)
            logger.info("relay_response path=%s status=%s", path, status)
            self._send_bytes(status, body, content_type)
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except RuntimeError as exc:
            self._send_json(500, {"error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object")
        return payload

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        self._send_bytes(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _forward_chat_completion(payload: dict[str, Any]) -> tuple[int, bytes, str]:
    upstream_base_url = os.environ.get("KIMI_UPSTREAM_BASE_URL")
    api_key = os.environ.get("KIMI_API_KEY")
    if not upstream_base_url:
        raise RuntimeError("KIMI_UPSTREAM_BASE_URL is required")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY is required")

    url = f"{upstream_base_url.rstrip('/')}/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    upstream_timeout = int(os.environ.get("KIMI_UPSTREAM_TIMEOUT_SECONDS", "300"))
    max_retries = int(os.environ.get("RELAY_UPSTREAM_RETRY_COUNT", "2"))

    for attempt in range(max_retries + 1):
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=max(1, upstream_timeout)) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", "application/json"),
                )
        except HTTPError as exc:
            if attempt < max_retries and exc.code >= 500:
                logger.warning(
                    "relay_retry path=chat/completions attempt=%d/%d status=%d",
                    attempt + 1, max_retries, exc.code,
                )
                _relay_retry_backoff(attempt)
                continue
            return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
        except URLError as exc:
            if attempt < max_retries:
                logger.warning(
                    "relay_retry path=chat/completions attempt=%d/%d reason=%s",
                    attempt + 1, max_retries, exc.reason,
                )
                _relay_retry_backoff(attempt)
                continue
            return _upstream_error_response(f"upstream request failed: {exc.reason}")
        except (TimeoutError, OSError) as exc:
            if attempt < max_retries:
                logger.warning(
                    "relay_retry path=chat/completions attempt=%d/%d error=%s",
                    attempt + 1, max_retries, exc,
                )
                _relay_retry_backoff(attempt)
                continue
            return _upstream_error_response(f"upstream request failed: {exc}")
    # Should not be reached
    return _upstream_error_response("upstream request failed: max retries exceeded")


def _forward_responses_completion(payload: dict[str, Any]) -> tuple[int, bytes, str]:
    upstream_base_url = os.environ.get("KIMI_UPSTREAM_BASE_URL")
    api_key = os.environ.get("KIMI_API_KEY")
    if not upstream_base_url:
        raise RuntimeError("KIMI_UPSTREAM_BASE_URL is required")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY is required")
    upstream_timeout = int(os.environ.get("KIMI_UPSTREAM_TIMEOUT_SECONDS", "300"))
    max_retries = int(os.environ.get("RELAY_UPSTREAM_RETRY_COUNT", "2"))

    for attempt in range(max_retries + 1):
        request = Request(
            f"{upstream_base_url.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=max(1, upstream_timeout)) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", "application/json"),
                )
        except HTTPError as exc:
            if attempt < max_retries and exc.code >= 500:
                logger.warning(
                    "relay_retry path=responses attempt=%d/%d status=%d",
                    attempt + 1, max_retries, exc.code,
                )
                _relay_retry_backoff(attempt)
                continue
            return exc.code, exc.read(), exc.headers.get("Content-Type", "application/json")
        except URLError as exc:
            if attempt < max_retries:
                logger.warning(
                    "relay_retry path=responses attempt=%d/%d reason=%s",
                    attempt + 1, max_retries, exc.reason,
                )
                _relay_retry_backoff(attempt)
                continue
            return _upstream_error_response(f"upstream request failed: {exc.reason}")
        except (TimeoutError, OSError) as exc:
            if attempt < max_retries:
                logger.warning(
                    "relay_retry path=responses attempt=%d/%d error=%s",
                    attempt + 1, max_retries, exc,
                )
                _relay_retry_backoff(attempt)
                continue
            return _upstream_error_response(f"upstream request failed: {exc}")
    return _upstream_error_response("upstream request failed: max retries exceeded")


def _upstream_error_response(message: str) -> tuple[int, bytes, str]:
    return 502, json.dumps({"error": message}).encode("utf-8"), "application/json"


def _relay_retry_backoff(attempt: int) -> None:
    import time
    delay = min(1.0 * (2 ** attempt), 15.0)
    time.sleep(delay)


def _debug_upstream_summary(path: str, request_payload: dict[str, Any], upstream_payload: dict[str, Any]) -> None:
    try:
        choices = upstream_payload.get("choices") or []
        choice = choices[0] if choices else {}
        message = choice.get("message") or {}
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []
        usage = upstream_payload.get("usage") or {}
        logger.info(
            "relay_upstream_summary path=%s choices=%d content_len=%d tool_calls=%d names=%s finish=%s usage=%s",
            path,
            len(choices),
            len(content) if isinstance(content, str) else -1,
            len(tool_calls),
            [str(tc.get("function", {}).get("name", "")) for tc in tool_calls][:5],
            choice.get("finish_reason"),
            usage,
        )
    except Exception:  # pragma: no cover - debug helper must never break the relay
        pass


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("RELAY_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    host = os.environ.get("KIMI_RELAY_HOST", "0.0.0.0")
    port = int(os.environ.get("KIMI_RELAY_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), RelayHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
