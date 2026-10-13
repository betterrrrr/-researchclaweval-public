from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from io import BytesIO
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request
from urllib.request import urlopen as urllib_urlopen

import pytest

from real_eval.codex_relay import relay
from real_eval.codex_relay.relay import (
    RelayHandler,
    _sanitize_request_path,
    normalize_model_name,
    normalize_request_payload,
)


def test_normalize_model_name_removes_openai_prefix_for_kimi() -> None:
    assert normalize_model_name("openai/kimi-k2.6") == "kimi-k2.6"
    assert normalize_model_name("kimi-k2.6") == "kimi-k2.6"


def test_normalize_model_name_removes_openai_prefix_for_deepseek() -> None:
    assert normalize_model_name("openai/deepseek-v4-flash") == "deepseek-v4-flash"
    assert normalize_model_name("deepseek-v4-flash") == "deepseek-v4-flash"


def test_sanitize_request_path_removes_query_and_absolute_form_userinfo() -> None:
    assert _sanitize_request_path("/v1/responses?api_key=query-secret") == "/v1/responses"
    assert (
        _sanitize_request_path("https://relay-user:target-secret@example.test/v1/responses?token=query-secret")
        == "/v1/responses"
    )


def test_debug_upstream_summary_excludes_content_and_tool_arguments(caplog: pytest.LogCaptureFixture) -> None:
    request_payload = {
        "tools": [{"function": {"name": "execute", "arguments": '{"secret":"request-secret"}'}}]
    }
    upstream_payload = {
        "choices": [
            {
                "message": {
                    "content": "response-secret and private response text",
                    "tool_calls": [{"function": {"name": "execute", "arguments": '{"secret":"upstream-secret"}'}}],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
    }

    with caplog.at_level("INFO", logger=relay.__name__):
        relay._debug_upstream_summary("/v1/responses", request_payload, upstream_payload)

    message = caplog.records[-1].getMessage()
    assert "content_head" not in message
    assert "response-secret" not in message
    assert "private response text" not in message
    assert "request-secret" not in message
    assert "upstream-secret" not in message
    assert "choices=1" in message
    assert "content_len=41" in message
    assert "tool_calls=1" in message
    assert "execute" in message
    assert "finish=stop" in message
    assert "total_tokens" in message


def test_chat_payload_translates_to_responses_without_losing_tool_history() -> None:
    payload = {
        "model": "gpt-5.4",
        "messages": [
            {"role": "system", "content": "Use the local contract."},
            {"role": "user", "content": "Run an experiment."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "execute", "arguments": '{"cmd":"true"}'},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "execute",
                    "description": "Run a command",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
        "tool_choice": "auto",
        "stream": True,
    }

    translated = relay._chat_payload_to_responses(payload)

    assert translated["model"] == "gpt-5.4"
    assert translated["instructions"] == "Use the local contract."
    assert translated["stream"] is False
    assert translated["tools"][0]["name"] == "execute"
    assert any(item.get("type") == "function_call" for item in translated["input"])
    assert any(item.get("type") == "function_call_output" for item in translated["input"])


def test_responses_payload_translates_to_chat_completion() -> None:
    upstream = {
        "id": "resp_1",
        "model": "gpt-5.4",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            },
            {
                "type": "function_call",
                "call_id": "call_2",
                "name": "execute",
                "arguments": '{"cmd":"true"}',
            },
        ],
        "usage": {"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
    }

    translated = relay._responses_payload_to_chat_completion(
        {"model": "gpt-5.4"}, upstream
    )

    assert translated["choices"][0]["message"]["content"] == "done"
    assert translated["choices"][0]["message"]["tool_calls"][0]["id"] == "call_2"
    assert translated["choices"][0]["finish_reason"] == "tool_calls"
    assert translated["usage"]["total_tokens"] == 7


def test_normalize_request_payload_makes_kimi_tool_choice_safe() -> None:
    payload = {
        "model": "openai/kimi-k2.6",
        "messages": [{"role": "user", "content": "hi"}],
        "tool_choice": "required",
        "temperature": 0,
    }

    normalized = normalize_request_payload(payload)

    assert normalized["model"] == "kimi-k2.6"
    assert normalized["tool_choice"] == "auto"
    assert normalized["temperature"] == 1


def test_normalize_request_payload_rewrites_required_only_for_bianxie_deepseek(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_PROVIDER", "bianxie")
    payload = {
        "model": "openai/deepseek-v4-flash",
        "messages": [{"role": "user", "content": "call a tool"}],
        "tools": [{"type": "function", "function": {"name": "act"}}],
        "tool_choice": "required",
        "stream": False,
    }

    normalized = normalize_request_payload(payload)

    assert normalized["model"] == "deepseek-v4-flash"
    assert normalized["tool_choice"] == "auto"
    assert payload["tool_choice"] == "required"


def test_normalize_request_payload_rewrites_named_function_for_bianxie_deepseek(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_PROVIDER", "bianxie")
    named_function = {"type": "function", "function": {"name": "run_experiment"}}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "run the experiment"}],
        "tools": [{"type": "function", "function": {"name": "run_experiment"}}],
        "tool_choice": named_function,
    }

    normalized = normalize_request_payload(payload)

    assert normalized["tool_choice"] == "auto"
    assert payload["tool_choice"] == named_function


def test_normalize_request_payload_preserves_required_for_other_deepseek_providers(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_PROVIDER", "other")
    payload = {
        "model": "openai/deepseek-v4-flash",
        "messages": [{"role": "user", "content": "call a tool"}],
        "tool_choice": "required",
    }

    normalized = normalize_request_payload(payload)

    assert normalized["model"] == "deepseek-v4-flash"
    assert normalized["tool_choice"] == "required"


def test_normalize_request_payload_preserves_named_function_for_other_providers(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("RELAY_UPSTREAM_PROVIDER", "other")
    named_function = {"type": "function", "function": {"name": "run_experiment"}}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "run the experiment"}],
        "tool_choice": named_function,
    }

    normalized = normalize_request_payload(payload)

    assert normalized["tool_choice"] == named_function


def test_normalize_request_payload_drops_unmatched_tool_messages() -> None:
    payload = {
        "model": "kimi-k2.6",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "tool", "tool_call_id": "missing", "content": "old"},
        ],
    }

    normalized = normalize_request_payload(payload)

    assert normalized["messages"] == [{"role": "user", "content": "hi"}]


def test_unsupported_post_path_returns_404_without_upstream_call(monkeypatch: Any) -> None:
    upstream_calls: list[Request] = []

    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        upstream_calls.append(request)
        return _FakeUpstreamResponse({})

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, body = _post_json("/unsupported", {"model": "kimi-k2.6"})

    assert status == 404
    assert body == {"error": "not found"}
    assert upstream_calls == []


def test_client_bearer_token_is_required_when_configured(monkeypatch: Any) -> None:
    monkeypatch.setenv("RELAY_CLIENT_API_KEY", "client-secret")

    status, body = _post_json(
        "/v1/chat/completions",
        {"model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert status == 401
    assert body == {"error": "unauthorized"}


def test_v1_responses_converts_simple_input_into_chat_messages(monkeypatch: Any) -> None:
    upstream_requests: list[Request] = []

    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        upstream_requests.append(request)
        return _FakeUpstreamResponse({"ok": True})

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, body = _post_json(
        "/v1/responses",
        {"model": "openai/kimi-k2.6", "input": "hello"},
    )

    assert status == 200
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output"] == []
    assert len(upstream_requests) == 1
    forwarded_payload = json.loads(upstream_requests[0].data.decode("utf-8"))
    assert forwarded_payload["model"] == "kimi-k2.6"
    assert forwarded_payload["messages"] == [{"role": "user", "content": "hello"}]
    assert "input" not in forwarded_payload
    assert forwarded_payload["stream"] is False


def test_v1_responses_translates_instructions_and_tools(monkeypatch: Any) -> None:
    upstream_requests: list[Request] = []

    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        upstream_requests.append(request)
        return _FakeUpstreamResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, body = _post_json(
        "/v1/responses",
        {
            "model": "openai/kimi-k2.6",
            "instructions": "follow system",
            "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]}],
            "tools": [
                {
                    "type": "function",
                    "name": "lookup",
                    "description": "find data",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                }
            ],
        },
    )

    assert status == 200
    assert body["status"] == "completed"
    forwarded_payload = json.loads(upstream_requests[0].data.decode("utf-8"))
    assert forwarded_payload["messages"] == [
        {"role": "system", "content": "follow system"},
        {"role": "user", "content": "hello"},
    ]
    assert forwarded_payload["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "find data",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
            },
        }
    ]


def test_forwarding_uses_expected_upstream_url_and_authorization_header(monkeypatch: Any) -> None:
    upstream_requests: list[Request] = []

    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        upstream_requests.append(request)
        return _FakeUpstreamResponse({"ok": True})

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1/")
    monkeypatch.setenv("KIMI_API_KEY", "secret-token")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, body = _post_json(
        "/v1/chat/completions",
        {"model": "kimi-k2.6", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert status == 200
    assert body == {"ok": True}
    assert len(upstream_requests) == 1
    assert upstream_requests[0].full_url == "https://kimi.example/v1/chat/completions"
    assert upstream_requests[0].get_header("Authorization") == "Bearer secret-token"


def test_upstream_socket_failure_returns_502_json(monkeypatch: Any) -> None:
    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        raise TimeoutError("timed out")

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, body = _post_json(
        "/chat/completions",
        {"model": "kimi-k2.6", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert status == 502
    assert body == {"error": "upstream request failed: timed out"}


def test_real_server_unsupported_post_path_returns_404() -> None:
    with _relay_server_url() as base_url:
        request = Request(
            f"{base_url}/unsupported",
            data=json.dumps({"model": "kimi-k2.6"}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            urllib_urlopen(request, timeout=5)
        except HTTPError as exc:
            assert exc.code == 404
            assert json.loads(exc.read().decode("utf-8")) == {"error": "not found"}
        else:
            raise AssertionError("unsupported POST path unexpectedly succeeded")


def test_real_server_healthz_returns_ok() -> None:
    with _relay_server_url() as base_url:
        with urllib_urlopen(f"{base_url}/healthz", timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8")) == {"ok": True}


def test_real_server_v1_responses_forwards_normalized_chat_request(monkeypatch: Any) -> None:
    upstream_requests: list[Request] = []

    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        upstream_requests.append(request)
        return _FakeUpstreamResponse({"id": "relay-response", "ok": True})

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1/")
    monkeypatch.setenv("KIMI_API_KEY", "real-server-token")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    with _relay_server_url() as base_url:
        request = Request(
            f"{base_url}/v1/responses",
            data=json.dumps(
                {
                    "model": "openai/kimi-k2.6",
                    "input": "hello through server",
                    "tool_choice": "required",
                    "temperature": 0,
                }
            ).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        with urllib_urlopen(request, timeout=5) as response:
            assert response.status == 200
            assert json.loads(response.read().decode("utf-8")) == {
                "id": "relay-response",
                "ok": True,
            }

    assert len(upstream_requests) == 1
    assert upstream_requests[0].full_url == "https://kimi.example/v1/chat/completions"
    assert upstream_requests[0].get_header("Authorization") == "Bearer real-server-token"
    forwarded_payload = json.loads(upstream_requests[0].data.decode("utf-8"))
    assert forwarded_payload["model"] == "kimi-k2.6"
    assert forwarded_payload["messages"] == [{"role": "user", "content": "hello through server"}]
    assert forwarded_payload["tool_choice"] == "auto"
    assert forwarded_payload["temperature"] == 1


def test_v1_responses_stream_emits_completed_and_done(monkeypatch: Any) -> None:
    def fake_urlopen(request: Request, timeout: int) -> _FakeUpstreamResponse:
        return _FakeUpstreamResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "relay output",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {"name": "lookup", "arguments": "{\"q\":\"abc\"}"},
                                }
                            ],
                        }
                    }
                ]
            }
        )

    monkeypatch.setenv("KIMI_UPSTREAM_BASE_URL", "https://kimi.example/v1")
    monkeypatch.setenv("KIMI_API_KEY", "secret")
    monkeypatch.setattr(relay, "urlopen", fake_urlopen)

    status, headers, body = _post_json_raw(
        "/v1/responses",
        {"model": "openai/kimi-k2.6", "input": "hello", "stream": True},
    )

    assert status == 200
    assert headers["Content-Type"] == "text/event-stream; charset=utf-8"
    text = body.decode("utf-8")
    assert "event: response.created" in text
    assert "event: response.output_text.delta" in text
    assert "event: response.completed" in text
    assert 'event: response.output_item.done' in text
    assert "data: [DONE]" in text


class _FakeUpstreamResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeUpstreamResponse":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _post_json(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    status, _, body = _post_json_raw(path, payload)
    return status, json.loads(body.decode("utf-8"))


def _post_json_raw(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload).encode("utf-8")
    handler = object.__new__(RelayHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()

    response: dict[str, Any] = {"status": None}
    headers: dict[str, str] = {}

    def send_response(status: int, message: str | None = None) -> None:
        response["status"] = status

    def send_header(name: str, value: str) -> None:
        headers[name] = value

    def end_headers() -> None:
        return None

    handler.send_response = send_response
    handler.send_header = send_header
    handler.end_headers = end_headers

    RelayHandler.do_POST(handler)

    return response["status"], headers, handler.wfile.getvalue()


class _relay_server_url:
    def __enter__(self) -> str:
        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), RelayHandler)
        except PermissionError:
            pytest.skip("local socket binding is blocked in this sandbox")
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __exit__(self, *args: Any) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
