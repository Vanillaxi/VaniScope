from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from webscoper.runtime.llm.client import OpenAICompatibleLLMClient
from webscoper.schemas.llm import LLMClientConfig, LLMMessage, LLMRequest


class FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


@pytest.mark.asyncio
async def test_openai_compatible_llm_client_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> FakeHTTPResponse:
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"tool_calls": []}',
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            base_url="https://example.com/api/v1",
            api_key="secret-token",
            model="example-model",
            timeout_ms=5000,
        )
    )

    response = await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="Build a plan.")],
            model="example-model",
        )
    )

    assert response.content == '{"tool_calls": []}'
    assert response.usage["total_tokens"] == 2
    assert captured["url"] == "https://example.com/api/v1/chat/completions"
    assert captured["timeout"] == 5.0
    assert captured["body"]["model"] == "example-model"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_openai_compatible_llm_client_http_error_hides_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request,
        timeout: float,
    ) -> FakeHTTPResponse:
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    client = OpenAICompatibleLLMClient(
        LLMClientConfig(
            base_url="https://example.com/api/v1",
            api_key="secret-token",
            model="example-model",
        )
    )

    with pytest.raises(RuntimeError) as exc_info:
        await client.generate(LLMRequest())

    assert "401" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
    assert "Authorization" not in str(exc_info.value)
