"""인증된 채팅 API의 입력 검증, AI 호출, 저장 테스트."""

import asyncio
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
import logging
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import httpx2
import pytest
from google.genai import errors as genai_errors
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    OpenAIError,
    RateLimitError,
)
from pydantic import SecretStr
from sqlalchemy import select

from app.ai_client import (
    AICompletion,
    ChatMessage,
    FallbackAIClient,
    GeminiChatClient,
    OpenAIChatClient,
    get_ai_client,
    get_gemini_client,
)
from app.config import settings
from app.db import SessionLocal, get_db
from app.errors import (
    AIConfigurationError,
    AIErrorCategory,
    AIFallbackReason,
    AIProviderAttempt,
    AIProviderFailure,
    AIServiceError,
    AITimeoutError,
)
from app.main import app
from app.models import ChatLog, User

USERNAME = "chat_tester"
PASSWORD = "correct-horse"


def make_openai_client(*, result=None, error: Exception | None = None) -> OpenAIChatClient:
    create = AsyncMock(return_value=result, side_effect=error)
    sdk_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    )
    return OpenAIChatClient(client=sdk_client, model="test-model")


def make_status_error(status_code: int, *, rate_limit: bool = False) -> APIStatusError:
    request = httpx2.Request("POST", "https://provider.invalid/v1/chat/completions")
    response = httpx2.Response(status_code, request=request)
    error_type = RateLimitError if rate_limit else APIStatusError
    return error_type(
        "private provider error containing secret-api-key",
        response=response,
        body={"private": "response body"},
    )


def capture_provider_error(error: Exception):
    async def call_client():
        client = make_openai_client(error=error)
        return await client.complete([ChatMessage(role="user", content="질문 전문")])

    with pytest.raises((AITimeoutError, AIServiceError)) as caught:
        asyncio.run(call_client())
    return caught.value


class FakeGeminiAsyncClient:
    def __init__(self, *, result=None, error: Exception | None = None) -> None:
        self.models = SimpleNamespace(
            generate_content=AsyncMock(return_value=result, side_effect=error),
        )
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        self.closed = True


class FakeGeminiOwner:
    def __init__(self, async_client: FakeGeminiAsyncClient) -> None:
        self.aio = async_client
        self.closed = False

    def close(self) -> None:
        self.closed = True


def make_gemini_client(*, result=None, error: Exception | None = None):
    async_client = FakeGeminiAsyncClient(result=result, error=error)
    owner = FakeGeminiOwner(async_client)
    client = GeminiChatClient(client_factory=lambda: owner, model="test-gemini-model")
    return client, owner, async_client


def make_gemini_api_error(status_code: int) -> genai_errors.APIError:
    error_type = (
        genai_errors.ClientError
        if 400 <= status_code < 500
        else genai_errors.ServerError
    )
    return error_type(
        status_code,
        {
            "error": {
                "status": "PRIVATE_STATUS",
                "message": "private Gemini detail with secret-api-key",
            }
        },
    )


def capture_gemini_error(error: Exception):
    client, owner, async_client = make_gemini_client(error=error)

    with pytest.raises((AITimeoutError, AIServiceError)) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="비밀 질문")]))

    assert owner.closed is True
    assert async_client.closed is True
    return caught.value


def test_ai_error_categories_cover_provider_failure_policy():
    assert {category.value for category in AIErrorCategory} == {
        "configuration",
        "timeout",
        "connection",
        "rate_limit",
        "upstream_4xx",
        "upstream_5xx",
        "invalid_response",
        "unknown",
    }


def test_ai_provider_failure_keeps_only_safe_structured_fields():
    private_detail = "provider response with secret-api-key"
    failure = AIProviderFailure(
        provider="codyssey",
        category=AIErrorCategory.RATE_LIMIT,
        status_code=429,
        retryable=True,
        exception_type="RateLimitError",
    )
    failed_attempt = AIProviderAttempt(
        provider="codyssey",
        attempt=1,
        succeeded=False,
        latency_ms=120,
        failure=failure,
    )
    error = AIServiceError(
        private_detail,
        failure=failure,
        attempts=[failed_attempt],
    )

    assert error.failure == failure
    assert error.attempts == (failed_attempt,)
    assert failure.provider == "codyssey"
    assert failure.category is AIErrorCategory.RATE_LIMIT
    assert failure.status_code == 429
    assert failure.retryable is True
    assert failure.exception_type == "RateLimitError"
    assert private_detail not in repr(failure)
    assert not hasattr(failure, "message")
    assert not hasattr(failure, "response_body")
    assert not hasattr(failure, "headers")


def test_ai_completion_describes_final_provider_and_attempts():
    primary_failure = AIProviderFailure(
        provider="codyssey",
        category=AIErrorCategory.TIMEOUT,
        status_code=None,
        retryable=True,
        exception_type="APITimeoutError",
    )
    attempts = (
        AIProviderAttempt(
            provider="codyssey",
            attempt=1,
            succeeded=False,
            latency_ms=20_000,
            failure=primary_failure,
        ),
        AIProviderAttempt(
            provider="gemini",
            attempt=2,
            succeeded=True,
            latency_ms=1_200,
        ),
    )

    completion = AICompletion(
        text="fallback 답변",
        provider="gemini",
        fallback_used=True,
        attempts=attempts,
    )

    assert completion.text == "fallback 답변"
    assert completion.provider == "gemini"
    assert completion.fallback_used is True
    assert completion.attempts == attempts


def test_codyssey_timeout_is_retryable_without_sensitive_metadata():
    request = httpx2.Request("POST", "https://provider.invalid/v1/chat/completions")
    sdk_error = APITimeoutError(request=request)

    error = capture_provider_error(sdk_error)

    assert isinstance(error, AITimeoutError)
    assert error.__cause__ is sdk_error
    assert error.failure == AIProviderFailure(
        provider="codyssey",
        category=AIErrorCategory.TIMEOUT,
        status_code=None,
        retryable=True,
        exception_type="APITimeoutError",
    )


def test_codyssey_connection_error_is_retryable():
    request = httpx2.Request("POST", "https://provider.invalid/v1/chat/completions")
    error = capture_provider_error(APIConnectionError(request=request))

    assert isinstance(error, AIServiceError)
    assert error.failure is not None
    assert error.failure.category is AIErrorCategory.CONNECTION
    assert error.failure.retryable is True
    assert error.failure.status_code is None


def test_codyssey_rate_limit_error_is_retryable_429():
    error = capture_provider_error(make_status_error(429, rate_limit=True))

    assert isinstance(error, AIServiceError)
    assert error.failure is not None
    assert error.failure.category is AIErrorCategory.RATE_LIMIT
    assert error.failure.status_code == 429
    assert error.failure.retryable is True
    assert error.failure.exception_type == "RateLimitError"
    assert "secret-api-key" not in str(error)
    assert "response body" not in repr(error.failure)


@pytest.mark.parametrize(
    ("status_code", "expected_error", "category", "retryable"),
    [
        (408, AITimeoutError, AIErrorCategory.TIMEOUT, True),
        (429, AIServiceError, AIErrorCategory.RATE_LIMIT, True),
        (500, AIServiceError, AIErrorCategory.UPSTREAM_5XX, True),
        (503, AIServiceError, AIErrorCategory.UPSTREAM_5XX, True),
        (400, AIServiceError, AIErrorCategory.UPSTREAM_4XX, False),
        (401, AIServiceError, AIErrorCategory.CONFIGURATION, False),
        (403, AIServiceError, AIErrorCategory.CONFIGURATION, False),
    ],
)
def test_codyssey_status_errors_are_classified(
    status_code,
    expected_error,
    category,
    retryable,
):
    error = capture_provider_error(make_status_error(status_code))

    assert isinstance(error, expected_error)
    assert error.failure is not None
    assert error.failure.provider == "codyssey"
    assert error.failure.category is category
    assert error.failure.status_code == status_code
    assert error.failure.retryable is retryable
    assert error.failure.exception_type == "APIStatusError"


def test_codyssey_unknown_openai_error_is_not_retryable():
    sdk_error = OpenAIError("private SDK detail with secret-api-key")

    error = capture_provider_error(sdk_error)

    assert error.__cause__ is sdk_error
    assert error.failure is not None
    assert error.failure.category is AIErrorCategory.UNKNOWN
    assert error.failure.retryable is False
    assert "secret-api-key" not in repr(error.failure)
    assert "private SDK detail" not in str(error)


@pytest.mark.parametrize(
    "unexpected_error",
    [RuntimeError("unexpected code bug"), asyncio.CancelledError()],
)
def test_codyssey_unexpected_and_cancelled_errors_are_not_normalized(unexpected_error):
    client = make_openai_client(error=unexpected_error)

    with pytest.raises(type(unexpected_error)) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문 전문")]))

    assert caught.value is unexpected_error


@pytest.mark.parametrize(
    ("result", "exception_type"),
    [
        (SimpleNamespace(choices=[]), "MissingChoices"),
        (
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="   "))],
            ),
            "EmptyContent",
        ),
    ],
)
def test_codyssey_invalid_response_is_retryable(result, exception_type):
    client = make_openai_client(result=result)

    with pytest.raises(AIServiceError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문 전문")]))

    failure = caught.value.failure
    assert failure is not None
    assert failure.category is AIErrorCategory.INVALID_RESPONSE
    assert failure.retryable is True
    assert failure.status_code is None
    assert failure.exception_type == exception_type


def test_gemini_converts_message_roles_order_and_system_instruction(capsys):
    client, owner, async_client = make_gemini_client(
        result=SimpleNamespace(text="정상 답변"),
    )
    messages = [
        ChatMessage(role="system", content="첫 번째 시스템 지시"),
        ChatMessage(role="user", content="첫 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="system", content="두 번째 시스템 지시"),
        ChatMessage(role="user", content="현재 질문"),
    ]

    answer = asyncio.run(client.complete(messages))

    assert answer == "정상 답변"
    call = async_client.models.generate_content.await_args
    assert call.kwargs["model"] == "test-gemini-model"
    assert [content.role for content in call.kwargs["contents"]] == [
        "user",
        "model",
        "user",
    ]
    assert [content.parts[0].text for content in call.kwargs["contents"]] == [
        "첫 질문",
        "이전 답변",
        "현재 질문",
    ]
    assert call.kwargs["config"].system_instruction == [
        "첫 번째 시스템 지시",
        "두 번째 시스템 지시",
    ]
    assert async_client.closed is True
    assert owner.closed is True
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""
    assert "현재 질문" not in output.out + output.err
    assert "정상 답변" not in output.out + output.err
    assert "첫 번째 시스템 지시" not in output.out + output.err


def test_gemini_factory_reads_settings_and_disables_sdk_retries(monkeypatch):
    synthetic_key = "fake-gemini-key-for-test"
    async_client = FakeGeminiAsyncClient(result=SimpleNamespace(text="ok"))
    owner = FakeGeminiOwner(async_client)
    constructor_args = {}

    def fake_client_constructor(**kwargs):
        constructor_args.update(kwargs)
        return owner

    monkeypatch.setattr(settings, "gemini_api_key", SecretStr(synthetic_key))
    monkeypatch.setattr(settings, "gemini_model", "configured-test-model")
    monkeypatch.setattr(settings, "gemini_timeout_seconds", 12.5)
    monkeypatch.setattr("app.ai_client.genai.Client", fake_client_constructor)
    get_gemini_client.cache_clear()
    try:
        client = get_gemini_client()
        answer = asyncio.run(
            client.complete([ChatMessage(role="user", content="설정 확인 질문")])
        )
    finally:
        get_gemini_client.cache_clear()

    assert answer == "ok"
    assert async_client.models.generate_content.await_args.kwargs["model"] == (
        "configured-test-model"
    )
    assert constructor_args["api_key"] == synthetic_key
    assert constructor_args["http_options"].timeout == 12_500
    assert constructor_args["http_options"].retry_options.attempts == 1
    assert owner.closed is True
    assert async_client.closed is True


@pytest.mark.parametrize("text", [None, "   "])
def test_gemini_empty_response_is_retryable_invalid_response(text):
    client, owner, async_client = make_gemini_client(
        result=SimpleNamespace(text=text),
    )

    with pytest.raises(AIServiceError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    failure = caught.value.failure
    assert failure is not None
    assert failure.provider == "gemini"
    assert failure.category is AIErrorCategory.INVALID_RESPONSE
    assert failure.retryable is True
    assert failure.status_code is None
    assert owner.closed is True
    assert async_client.closed is True


def test_gemini_timeout_is_retryable():
    request = httpx.Request("POST", "https://provider.invalid/v1/models")
    sdk_error = httpx.ReadTimeout(
        "private timeout detail with secret-api-key",
        request=request,
    )

    error = capture_gemini_error(sdk_error)

    assert isinstance(error, AITimeoutError)
    assert error.__cause__ is sdk_error
    assert error.failure == AIProviderFailure(
        provider="gemini",
        category=AIErrorCategory.TIMEOUT,
        status_code=None,
        retryable=True,
        exception_type="ReadTimeout",
    )
    assert "secret-api-key" not in str(error)
    assert "private timeout detail" not in repr(error.failure)


def test_gemini_connection_error_is_retryable():
    request = httpx.Request("POST", "https://provider.invalid/v1/models")
    error = capture_gemini_error(
        httpx.ConnectError("private connection detail", request=request)
    )

    assert isinstance(error, AIServiceError)
    assert error.failure is not None
    assert error.failure.category is AIErrorCategory.CONNECTION
    assert error.failure.retryable is True


@pytest.mark.parametrize(
    ("status_code", "expected_error", "category", "retryable"),
    [
        (408, AITimeoutError, AIErrorCategory.TIMEOUT, True),
        (429, AIServiceError, AIErrorCategory.RATE_LIMIT, True),
        (500, AIServiceError, AIErrorCategory.UPSTREAM_5XX, True),
        (503, AIServiceError, AIErrorCategory.UPSTREAM_5XX, True),
        (400, AIServiceError, AIErrorCategory.UPSTREAM_4XX, False),
        (401, AIServiceError, AIErrorCategory.CONFIGURATION, False),
        (403, AIServiceError, AIErrorCategory.CONFIGURATION, False),
    ],
)
def test_gemini_api_errors_are_classified(
    status_code,
    expected_error,
    category,
    retryable,
):
    error = capture_gemini_error(make_gemini_api_error(status_code))

    assert isinstance(error, expected_error)
    assert error.failure is not None
    assert error.failure.provider == "gemini"
    assert error.failure.category is category
    assert error.failure.status_code == status_code
    assert error.failure.retryable is retryable


def test_gemini_does_not_print_content_key_or_provider_error(capsys):
    sdk_error = make_gemini_api_error(429)

    error = capture_gemini_error(sdk_error)

    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == ""
    assert "비밀 질문" not in str(error)
    assert "secret-api-key" not in str(error)
    assert "PRIVATE_STATUS" not in str(error)
    assert "private Gemini detail" not in repr(error.failure)


@pytest.mark.parametrize(
    "unexpected_error",
    [RuntimeError("unexpected Gemini code bug"), asyncio.CancelledError()],
)
def test_gemini_unexpected_and_cancelled_errors_are_not_normalized(unexpected_error):
    client, owner, async_client = make_gemini_client(error=unexpected_error)

    with pytest.raises(type(unexpected_error)) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is unexpected_error
    assert owner.closed is True
    assert async_client.closed is True


class StubProviderClient:
    def __init__(
        self,
        *,
        answer: str = "provider answer",
        error: BaseException | None = None,
    ) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if self.error is not None:
            raise self.error
        return self.answer


def provider_error(
    *,
    provider: str,
    category: AIErrorCategory,
    retryable: bool,
    status_code: int | None = None,
    timeout: bool = False,
    private_message: str = "private provider detail with secret-api-key",
):
    failure = AIProviderFailure(
        provider=provider,
        category=category,
        status_code=status_code,
        retryable=retryable,
        exception_type="SyntheticProviderError",
    )
    error_type = AITimeoutError if timeout else AIServiceError
    return error_type(private_message, failure=failure)


def run_fallback_client(primary, fallback, *, enabled=True):
    client = FallbackAIClient(
        primary=primary,
        fallback=fallback,
        fallback_enabled=enabled,
    )
    messages = [
        ChatMessage(role="user", content="이전 질문"),
        ChatMessage(role="assistant", content="이전 답변"),
        ChatMessage(role="user", content="현재 질문"),
    ]
    return asyncio.run(client.complete(messages)), messages


def test_fallback_primary_success_does_not_call_gemini():
    primary = StubProviderClient(answer="Codyssey 답변")
    fallback = StubProviderClient(answer="호출되면 안 되는 답변")

    result, messages = run_fallback_client(primary, fallback)

    assert isinstance(result, str)
    assert isinstance(result, AICompletion)
    assert result == "Codyssey 답변"
    assert result.text == "Codyssey 답변"
    assert result.provider == "codyssey"
    assert result.fallback_used is False
    assert len(result.attempts) == 1
    assert result.attempts[0].succeeded is True
    assert primary.calls == [messages]
    assert fallback.calls == []


@pytest.mark.parametrize(
    ("category", "status_code", "timeout"),
    [
        (AIErrorCategory.TIMEOUT, None, True),
        (AIErrorCategory.CONNECTION, None, False),
        (AIErrorCategory.RATE_LIMIT, 429, False),
        (AIErrorCategory.UPSTREAM_5XX, 503, False),
        (AIErrorCategory.INVALID_RESPONSE, None, False),
    ],
)
def test_fallback_retryable_primary_failure_uses_gemini_once(
    category,
    status_code,
    timeout,
):
    primary = StubProviderClient(
        error=provider_error(
            provider="codyssey",
            category=category,
            retryable=True,
            status_code=status_code,
            timeout=timeout,
        )
    )
    fallback = StubProviderClient(answer="Gemini fallback 답변")

    result, messages = run_fallback_client(primary, fallback)

    assert result == "Gemini fallback 답변"
    assert result.provider == "gemini"
    assert result.fallback_used is True
    assert [attempt.provider for attempt in result.attempts] == [
        "codyssey",
        "gemini",
    ]
    assert [attempt.succeeded for attempt in result.attempts] == [False, True]
    assert primary.calls == [messages]
    assert fallback.calls == [messages]


@pytest.mark.parametrize(
    ("status_code", "category"),
    [
        (400, AIErrorCategory.UPSTREAM_4XX),
        (401, AIErrorCategory.CONFIGURATION),
        (403, AIErrorCategory.CONFIGURATION),
    ],
)
def test_fallback_non_retryable_primary_status_does_not_call_gemini(
    status_code,
    category,
):
    primary_error = provider_error(
        provider="codyssey",
        category=category,
        retryable=False,
        status_code=status_code,
    )
    primary = StubProviderClient(error=primary_error)
    fallback = StubProviderClient()
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(AIServiceError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is primary_error
    assert caught.value.fallback_reason is AIFallbackReason.NON_RETRYABLE
    assert len(caught.value.attempts) == 1
    assert fallback.calls == []


def test_fallback_primary_configuration_error_preserves_503_meaning():
    primary_error = AIConfigurationError("AI client is not configured")
    primary = StubProviderClient(error=primary_error)
    fallback = StubProviderClient()
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(AIConfigurationError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is primary_error
    assert fallback.calls == []


@pytest.mark.parametrize(
    ("enabled", "reason"),
    [
        (True, AIFallbackReason.NOT_CONFIGURED),
        (False, AIFallbackReason.DISABLED),
    ],
)
def test_fallback_unavailable_preserves_primary_error_with_safe_reason(
    enabled,
    reason,
):
    primary_error = provider_error(
        provider="codyssey",
        category=AIErrorCategory.CONNECTION,
        retryable=True,
    )
    primary = StubProviderClient(error=primary_error)
    client = FallbackAIClient(
        primary=primary,
        fallback=None,
        fallback_enabled=enabled,
    )

    with pytest.raises(AIServiceError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is primary_error
    assert caught.value.failure is primary_error.failure
    assert caught.value.fallback_reason is reason
    assert len(caught.value.attempts) == 1


def test_fallback_failure_contains_two_safe_attempts():
    primary = StubProviderClient(
        error=provider_error(
            provider="codyssey",
            category=AIErrorCategory.RATE_LIMIT,
            retryable=True,
            status_code=429,
        )
    )
    fallback_error = provider_error(
        provider="gemini",
        category=AIErrorCategory.UPSTREAM_5XX,
        retryable=True,
        status_code=503,
        private_message="private Gemini response body with secret-api-key",
    )
    fallback = StubProviderClient(error=fallback_error)
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(AIServiceError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="비밀 질문")]))

    error = caught.value
    assert error.__cause__ is fallback_error
    assert [attempt.provider for attempt in error.attempts] == ["codyssey", "gemini"]
    assert [attempt.succeeded for attempt in error.attempts] == [False, False]
    assert [attempt.failure.category for attempt in error.attempts] == [
        AIErrorCategory.RATE_LIMIT,
        AIErrorCategory.UPSTREAM_5XX,
    ]
    assert "비밀 질문" not in str(error)
    assert "secret-api-key" not in str(error)
    assert "response body" not in repr(error.attempts)


def test_fallback_two_timeouts_preserve_504_meaning():
    primary = StubProviderClient(
        error=provider_error(
            provider="codyssey",
            category=AIErrorCategory.TIMEOUT,
            retryable=True,
            timeout=True,
        )
    )
    fallback = StubProviderClient(
        error=provider_error(
            provider="gemini",
            category=AIErrorCategory.TIMEOUT,
            retryable=True,
            timeout=True,
        )
    )
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(AITimeoutError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert len(caught.value.attempts) == 2
    assert all(
        attempt.failure.category is AIErrorCategory.TIMEOUT
        for attempt in caught.value.attempts
    )


class ProviderAbort(BaseException):
    pass


@pytest.mark.parametrize(
    "unexpected_error",
    [
        RuntimeError("unexpected primary bug"),
        asyncio.CancelledError(),
        ProviderAbort("stop provider"),
    ],
)
def test_fallback_does_not_swallow_unexpected_or_base_exceptions(unexpected_error):
    primary = StubProviderClient(error=unexpected_error)
    fallback = StubProviderClient()
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(type(unexpected_error)) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is unexpected_error
    assert fallback.calls == []


def test_fallback_does_not_hide_unexpected_gemini_error():
    primary = StubProviderClient(
        error=provider_error(
            provider="codyssey",
            category=AIErrorCategory.CONNECTION,
            retryable=True,
        )
    )
    fallback_error = RuntimeError("unexpected Gemini bug")
    fallback = StubProviderClient(error=fallback_error)
    client = FallbackAIClient(primary=primary, fallback=fallback, fallback_enabled=True)

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(client.complete([ChatMessage(role="user", content="질문")]))

    assert caught.value is fallback_error
    assert len(fallback.calls) == 1


def test_get_ai_client_assembles_fallback_without_cache_leak(monkeypatch):
    fallback = StubProviderClient(answer="Gemini 답변")

    with monkeypatch.context() as patch:
        patch.setattr(settings, "ai_api_key", SecretStr("fake-primary-key"))
        patch.setattr(settings, "gemini_api_key", SecretStr("fake-gemini-key"))
        patch.setattr(settings, "gemini_model", "configured-test-model")
        patch.setattr(settings, "ai_fallback_enabled", True)
        patch.setattr("app.ai_client.AsyncOpenAI", lambda **_kwargs: SimpleNamespace())
        patch.setattr("app.ai_client.get_gemini_client", lambda: fallback)
        get_ai_client.cache_clear()

        first = get_ai_client()
        second = get_ai_client()

        assert isinstance(first, FallbackAIClient)
        assert first is second
        assert first._fallback is fallback

    get_ai_client.cache_clear()
    get_gemini_client.cache_clear()
    assert get_ai_client.cache_info().currsize == 0
    assert get_gemini_client.cache_info().currsize == 0


class FakeAIClient:
    """네트워크 요청 없이 답변하거나 지정된 오류를 발생시키는 테스트 대역."""

    def __init__(self) -> None:
        self.answer = "가짜 AI 답변"
        self.error: Exception | None = None
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        self.calls.append(list(messages))
        if self.error is not None:
            raise self.error
        return self.answer


class FailOnceCommitSession:
    """실제 테스트 세션을 사용하되 첫 commit만 실패시키는 프록시."""

    def __init__(self, wrapped) -> None:
        self.wrapped = wrapped
        self.failed = False
        self.rollback_calls = 0

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    def commit(self) -> None:
        if not self.failed:
            self.failed = True
            raise RuntimeError("database detail must stay private")
        self.wrapped.commit()

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.wrapped.rollback()


@pytest.fixture()
def fake_ai() -> FakeAIClient:
    client = FakeAIClient()
    app.dependency_overrides[get_ai_client] = lambda: client
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


@pytest.fixture()
def missing_ai_key(monkeypatch):
    """실제 환경 파일을 건드리지 않고 AI 키 미설정 상태를 격리한다."""

    monkeypatch.setattr(settings, "ai_api_key", SecretStr(""))
    get_ai_client.cache_clear()
    try:
        yield
    finally:
        get_ai_client.cache_clear()


def signup_and_login(client) -> int:
    credentials = {"username": USERNAME, "password": PASSWORD}
    assert client.post("/api/auth/signup", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.username == USERNAME))
    assert user_id is not None
    return user_id


def load_chat_logs() -> list[ChatLog]:
    with SessionLocal() as db:
        return list(db.scalars(select(ChatLog).order_by(ChatLog.id)))


def create_test_user(username: str) -> int:
    with SessionLocal() as db:
        user = User(username=username, password_hash="unused-test-hash")
        db.add(user)
        db.commit()
        return user.id


def add_chat_history(
    user_id: int,
    count: int,
    *,
    prefix: str,
    start: datetime,
) -> None:
    with SessionLocal() as db:
        db.add_all(
            [
                ChatLog(
                    user_id=user_id,
                    question=f"{prefix} 질문 {index}",
                    answer=f"{prefix} 답변 {index}",
                    created_at=start + timedelta(minutes=index),
                )
                for index in range(1, count + 1)
            ]
        )
        db.commit()


def chat_event_messages(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == "app.chat"]


def assert_events_share_request_id(messages: list[str], events: list[str]) -> str:
    assert [message.split(maxsplit=1)[0] for message in messages] == events
    request_ids = []
    for message in messages:
        match = re.search(r"\brequest_id=([0-9a-f]{32})\b", message)
        assert match is not None
        request_ids.append(match.group(1))
    assert len(set(request_ids)) == 1
    return request_ids[0]


def test_chat_requires_login(client, fake_ai):
    response = client.post("/api/chat", json={"message": "안녕하세요"})

    assert response.status_code == 401
    assert response.json()["error"] == "UNAUTHORIZED"
    assert fake_ai.calls == []


def test_chat_rejects_blank_message_before_ai_call(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": " \t\n"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "INVALID_MESSAGE",
        "message": "메시지를 입력해 주세요.",
    }
    assert fake_ai.calls == []
    assert load_chat_logs() == []


def test_chat_accepts_exactly_2000_unicode_characters(client, fake_ai):
    signup_and_login(client)
    message = "가" * 2_000

    response = client.post("/api/chat", json={"message": message})

    assert response.status_code == 200
    assert fake_ai.calls[0] == [ChatMessage(role="user", content=message)]


def test_chat_rejects_more_than_2000_characters_before_ai_call(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": "가" * 2_001})

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_MESSAGE"
    assert fake_ai.calls == []
    assert load_chat_logs() == []


def test_chat_missing_ai_key_still_rejects_blank_message(client, missing_ai_key):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": " \t\n"})

    assert response.status_code == 400
    assert response.json() == {
        "error": "INVALID_MESSAGE",
        "message": "메시지를 입력해 주세요.",
    }
    assert load_chat_logs() == []


def test_chat_missing_ai_key_still_rejects_long_message(client, missing_ai_key):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": "가" * 2_001})

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_MESSAGE"
    assert load_chat_logs() == []


def test_chat_missing_ai_key_returns_503_without_sensitive_details(
    client,
    missing_ai_key,
    caplog,
):
    signup_and_login(client)
    caplog.set_level(logging.INFO, logger="app.chat")

    response = client.post("/api/chat", json={"message": "정상 길이 질문"})

    assert response.status_code == 503
    assert response.json() == {
        "error": "AI_NOT_CONFIGURED",
        "message": "현재 AI 서비스를 사용할 수 없습니다. 관리자에게 문의해 주세요.",
    }
    assert "AI_API_KEY" not in response.text
    assert "AI client is not configured" not in response.text
    assert load_chat_logs() == []

    messages = chat_event_messages(caplog)
    assert_events_share_request_id(
        messages,
        ["request_received", "ai_call_start", "ai_call_fail"],
    )
    log_text = "\n".join(messages)
    assert "AI_API_KEY" not in log_text
    assert "AI client is not configured" not in log_text
    assert "error_type=AIConfigurationError" in log_text


def test_chat_success_returns_answer_and_saves_current_user(client, fake_ai):
    user_id = signup_and_login(client)

    response = client.post("/api/chat", json={"message": "저장할 질문"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == fake_ai.answer
    assert isinstance(body["chat_id"], int)

    logs = load_chat_logs()
    assert len(logs) == 1
    assert logs[0].id == body["chat_id"]
    assert logs[0].user_id == user_id
    assert logs[0].question == "저장할 질문"
    assert logs[0].answer == fake_ai.answer


def test_chat_fallback_success_keeps_response_and_storage_contract(client):
    primary = StubProviderClient(
        error=provider_error(
            provider="codyssey",
            category=AIErrorCategory.CONNECTION,
            retryable=True,
        )
    )
    fallback = StubProviderClient(answer="저장되는 Gemini 답변")
    composite = FallbackAIClient(
        primary=primary,
        fallback=fallback,
        fallback_enabled=True,
    )
    app.dependency_overrides[get_ai_client] = lambda: composite
    try:
        user_id = signup_and_login(client)
        response = client.post("/api/chat", json={"message": "fallback 저장 질문"})
    finally:
        app.dependency_overrides.pop(get_ai_client, None)

    assert response.status_code == 200
    assert response.json()["answer"] == "저장되는 Gemini 답변"
    logs = load_chat_logs()
    assert len(logs) == 1
    assert logs[0].user_id == user_id
    assert logs[0].question == "fallback 저장 질문"
    assert logs[0].answer == "저장되는 Gemini 답변"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_chat_ai_failure_does_not_save_log(client, fake_ai):
    signup_and_login(client)
    fake_ai.error = AIServiceError("test AI failure")

    response = client.post("/api/chat", json={"message": "실패할 질문"})

    assert response.status_code == 502
    assert response.json()["error"] == "AI_SERVICE_ERROR"
    assert len(fake_ai.calls) == 1
    assert load_chat_logs() == []


def test_chat_context_without_history_sends_only_current_question(client, fake_ai):
    signup_and_login(client)

    response = client.post("/api/chat", json={"message": "첫 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [[ChatMessage(role="user", content="첫 질문")]]


def test_chat_context_uses_recent_five_in_chronological_order(client, fake_ai):
    user_id = signup_and_login(client)
    add_chat_history(
        user_id,
        7,
        prefix="내 대화",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    response = client.post("/api/chat", json={"message": "현재 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [
        [
            ChatMessage(role="user", content="내 대화 질문 3"),
            ChatMessage(role="assistant", content="내 대화 답변 3"),
            ChatMessage(role="user", content="내 대화 질문 4"),
            ChatMessage(role="assistant", content="내 대화 답변 4"),
            ChatMessage(role="user", content="내 대화 질문 5"),
            ChatMessage(role="assistant", content="내 대화 답변 5"),
            ChatMessage(role="user", content="내 대화 질문 6"),
            ChatMessage(role="assistant", content="내 대화 답변 6"),
            ChatMessage(role="user", content="내 대화 질문 7"),
            ChatMessage(role="assistant", content="내 대화 답변 7"),
            ChatMessage(role="user", content="현재 질문"),
        ]
    ]
    assert sum(
        message.content == "현재 질문" for message in fake_ai.calls[0]
    ) == 1


def test_chat_context_excludes_other_users_history(client, fake_ai):
    current_user_id = signup_and_login(client)
    other_user_id = create_test_user("other_context_user")
    start = datetime(2026, 2, 1, tzinfo=timezone.utc)
    add_chat_history(current_user_id, 1, prefix="내 대화", start=start)
    add_chat_history(other_user_id, 3, prefix="다른 사용자", start=start)

    response = client.post("/api/chat", json={"message": "격리 확인 질문"})

    assert response.status_code == 200
    assert fake_ai.calls == [
        [
            ChatMessage(role="user", content="내 대화 질문 1"),
            ChatMessage(role="assistant", content="내 대화 답변 1"),
            ChatMessage(role="user", content="격리 확인 질문"),
        ]
    ]
    assert all(
        "다른 사용자" not in message.content for message in fake_ai.calls[0]
    )


def test_chat_timeout_returns_504_and_logs_failure(client, fake_ai, caplog):
    signup_and_login(client)
    fake_ai.error = AITimeoutError("private provider timeout detail")
    caplog.set_level(logging.INFO, logger="app.chat")

    response = client.post("/api/chat", json={"message": "타임아웃 질문"})

    assert response.status_code == 504
    assert response.json()["error"] == "AI_TIMEOUT"
    assert load_chat_logs() == []
    messages = chat_event_messages(caplog)
    assert_events_share_request_id(
        messages,
        ["request_received", "ai_call_start", "ai_call_fail"],
    )
    assert "ai_call_success" not in "\n".join(messages)
    assert "db_save_success" not in "\n".join(messages)


def test_chat_service_failure_returns_502_without_sensitive_logs(
    client,
    fake_ai,
    caplog,
):
    signup_and_login(client)
    question = "로그에 남으면 안 되는 질문 전문"
    api_key = "private-api-key-value"
    provider_detail = f"provider failure with {api_key}"
    fake_ai.error = AIServiceError(provider_detail)
    caplog.set_level(logging.INFO, logger="app.chat")

    response = client.post("/api/chat", json={"message": question})

    assert response.status_code == 502
    assert response.json()["error"] == "AI_SERVICE_ERROR"
    assert provider_detail not in response.text
    messages = chat_event_messages(caplog)
    assert_events_share_request_id(
        messages,
        ["request_received", "ai_call_start", "ai_call_fail"],
    )
    log_text = "\n".join(messages)
    assert question not in log_text
    assert provider_detail not in log_text
    assert api_key not in log_text
    assert load_chat_logs() == []


def test_chat_success_logs_events_without_question_answer_or_key(
    client,
    fake_ai,
    caplog,
):
    signup_and_login(client)
    question = "비공개 성공 질문 전문"
    answer = "비공개 성공 답변 전문"
    api_key = "another-private-api-key"
    fake_ai.answer = answer
    caplog.set_level(logging.INFO, logger="app.chat")

    response = client.post("/api/chat", json={"message": question})

    assert response.status_code == 200
    messages = chat_event_messages(caplog)
    assert_events_share_request_id(
        messages,
        [
            "request_received",
            "ai_call_start",
            "ai_call_success",
            "db_save_success",
        ],
    )
    success_log = next(message for message in messages if message.startswith("ai_call_success "))
    assert re.search(r"\blatency_ms=\d+\b", success_log)
    log_text = "\n".join(messages)
    assert question not in log_text
    assert answer not in log_text
    assert api_key not in log_text


def test_chat_db_failure_rolls_back_and_next_request_succeeds(
    client,
    fake_ai,
    caplog,
):
    signup_and_login(client)
    wrapped_session = SessionLocal()
    failing_session = FailOnceCommitSession(wrapped_session)

    def override_get_db():
        yield failing_session

    app.dependency_overrides[get_db] = override_get_db
    caplog.set_level(logging.INFO, logger="app.chat")
    try:
        failed = client.post("/api/chat", json={"message": "저장 실패 질문"})
        recovered = client.post("/api/chat", json={"message": "복구 후 질문"})
    finally:
        app.dependency_overrides.pop(get_db, None)
        wrapped_session.close()

    assert failed.status_code == 500
    assert failed.json()["error"] == "DB_SAVE_ERROR"
    assert failing_session.rollback_calls == 1
    assert recovered.status_code == 200

    logs = load_chat_logs()
    assert [log.question for log in logs] == ["복구 후 질문"]

    grouped_events: dict[str, list[str]] = {}
    for message in chat_event_messages(caplog):
        match = re.search(r"\brequest_id=([0-9a-f]{32})\b", message)
        assert match is not None
        grouped_events.setdefault(match.group(1), []).append(message.split(maxsplit=1)[0])

    assert list(grouped_events.values()) == [
        ["request_received", "ai_call_start", "ai_call_success", "db_save_fail"],
        ["request_received", "ai_call_start", "ai_call_success", "db_save_success"],
    ]
