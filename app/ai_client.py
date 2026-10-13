"""AI 공급자와 라우터 사이의 공통 인터페이스.

라우터는 OpenAI 같은 특정 SDK 대신 이 모듈의 타입에만 의존한다.
테스트에서는 FastAPI의 ``dependency_overrides``를 사용해
``get_ai_client``가 가짜 클라이언트를 반환하도록 바꿀 수 있다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import Literal, Protocol

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
import httpx
import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from app.config import settings
from app.errors import (
    AIConfigurationError,
    AIErrorCategory,
    AIFallbackReason,
    AIProviderAttempt,
    AIProviderFailure,
    AIServiceError,
    AITimeoutError,
)


ChatRole = Literal["system", "user", "assistant"]
CODYSSEY_PROVIDER = "codyssey"
GEMINI_PROVIDER = "gemini"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """AI에 전달할 공급자 독립적인 대화 메시지."""

    role: ChatRole
    content: str


class AICompletion(str):
    """기존 문자열 계약을 유지하는 공급자 메타데이터 포함 답변."""

    def __new__(
        cls,
        text: str,
        provider: str,
        fallback_used: bool,
        attempts: Sequence[AIProviderAttempt],
    ) -> "AICompletion":
        completion = super().__new__(cls, text)
        completion.text = text
        completion.provider = provider
        completion.fallback_used = fallback_used
        completion.attempts = tuple(attempts)
        return completion


class AIClient(Protocol):
    """AI 답변 생성기가 따라야 하는 비동기 인터페이스."""

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        """대화 메시지를 받아 생성된 텍스트 답변을 반환한다."""
        ...


class UnavailableAIClient:
    """설정 누락을 실제 AI 호출 시점에 알리는 클라이언트."""

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        raise AIConfigurationError("AI client is not configured")


class OpenAIChatClient:
    """OpenAI 호환 Chat Completions API를 사용하는 구현체."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    @staticmethod
    def _failure(
        *,
        category: AIErrorCategory,
        retryable: bool,
        exception_type: str,
        status_code: int | None = None,
    ) -> AIProviderFailure:
        """원본 오류의 민감한 내용 없이 fallback 판단 정보만 만든다."""

        return AIProviderFailure(
            provider=CODYSSEY_PROVIDER,
            category=category,
            status_code=status_code,
            retryable=retryable,
            exception_type=exception_type,
        )

    @classmethod
    def _status_failure(cls, exc: APIStatusError) -> AIProviderFailure:
        status_code = exc.status_code
        if status_code == 429:
            category = AIErrorCategory.RATE_LIMIT
            retryable = True
        elif status_code == 408:
            category = AIErrorCategory.TIMEOUT
            retryable = True
        elif status_code in {401, 403}:
            category = AIErrorCategory.CONFIGURATION
            retryable = False
        elif 500 <= status_code < 600:
            category = AIErrorCategory.UPSTREAM_5XX
            retryable = True
        elif 400 <= status_code < 500:
            category = AIErrorCategory.UPSTREAM_4XX
            retryable = False
        else:
            category = AIErrorCategory.UNKNOWN
            retryable = False

        return cls._failure(
            category=category,
            status_code=status_code,
            retryable=retryable,
            exception_type=type(exc).__name__,
        )

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
            )
        except APITimeoutError as exc:
            failure = self._failure(
                category=AIErrorCategory.TIMEOUT,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AITimeoutError("AI service timed out", failure=failure) from exc
        except RateLimitError as exc:
            failure = self._failure(
                category=AIErrorCategory.RATE_LIMIT,
                status_code=429,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AIServiceError("AI service rate limit exceeded", failure=failure) from exc
        except APIConnectionError as exc:
            failure = self._failure(
                category=AIErrorCategory.CONNECTION,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AIServiceError("AI service connection failed", failure=failure) from exc
        except APIStatusError as exc:
            failure = self._status_failure(exc)
            if failure.category is AIErrorCategory.TIMEOUT:
                raise AITimeoutError("AI service timed out", failure=failure) from exc
            raise AIServiceError("AI service request failed", failure=failure) from exc
        except OpenAIError as exc:
            failure = self._failure(
                category=AIErrorCategory.UNKNOWN,
                retryable=False,
                exception_type=type(exc).__name__,
            )
            raise AIServiceError("AI service request failed", failure=failure) from exc

        if not completion.choices:
            failure = self._failure(
                category=AIErrorCategory.INVALID_RESPONSE,
                retryable=True,
                exception_type="MissingChoices",
            )
            raise AIServiceError("AI service returned no choices", failure=failure)

        content = completion.choices[0].message.content
        if content is None or not content.strip():
            failure = self._failure(
                category=AIErrorCategory.INVALID_RESPONSE,
                retryable=True,
                exception_type="EmptyContent",
            )
            raise AIServiceError("AI service returned an empty response", failure=failure)
        return content


class GeminiChatClient:
    """공식 Google Gen AI SDK의 비동기 API를 사용하는 구현체.

    호출마다 SDK 클라이언트를 만들고 닫는다. 이 구조는 앱 종료 훅에
    의존하지 않으면서 비동기 연결 자원이 남지 않게 하고, 테스트에서는
    ``client_factory``를 네트워크 없는 가짜 구현으로 교체할 수 있게 한다.
    """

    def __init__(self, client_factory: Callable[[], genai.Client], model: str) -> None:
        self._client_factory = client_factory
        self._model = model

    @staticmethod
    def _failure(
        *,
        category: AIErrorCategory,
        retryable: bool,
        exception_type: str,
        status_code: int | None = None,
    ) -> AIProviderFailure:
        """원본 응답이나 예외 문자열 없이 안전한 Gemini 실패 정보만 만든다."""

        return AIProviderFailure(
            provider=GEMINI_PROVIDER,
            category=category,
            status_code=status_code,
            retryable=retryable,
            exception_type=exception_type,
        )

    @classmethod
    def _api_failure(cls, exc: genai_errors.APIError) -> AIProviderFailure:
        status_code = exc.code if isinstance(exc.code, int) else None
        if status_code == 429:
            category = AIErrorCategory.RATE_LIMIT
            retryable = True
        elif status_code == 408:
            category = AIErrorCategory.TIMEOUT
            retryable = True
        elif status_code in {401, 403}:
            category = AIErrorCategory.CONFIGURATION
            retryable = False
        elif status_code is not None and 500 <= status_code < 600:
            category = AIErrorCategory.UPSTREAM_5XX
            retryable = True
        elif status_code is not None and 400 <= status_code < 500:
            category = AIErrorCategory.UPSTREAM_4XX
            retryable = False
        else:
            category = AIErrorCategory.UNKNOWN
            retryable = False

        return cls._failure(
            category=category,
            status_code=status_code,
            retryable=retryable,
            exception_type=type(exc).__name__,
        )

    @staticmethod
    def _request_parts(
        messages: Sequence[ChatMessage],
    ) -> tuple[list[genai_types.Content], list[str]]:
        contents: list[genai_types.Content] = []
        system_instructions: list[str] = []

        for message in messages:
            if message.role == "system":
                system_instructions.append(message.content)
                continue

            role = "model" if message.role == "assistant" else "user"
            contents.append(
                genai_types.Content(
                    role=role,
                    parts=[genai_types.Part.from_text(text=message.content)],
                )
            )

        return contents, system_instructions

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        contents, system_instructions = self._request_parts(messages)
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instructions or None,
        )
        owner = self._client_factory()

        try:
            async with owner.aio as async_client:
                response = await async_client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
        except (TimeoutError, httpx.TimeoutException, httpx2.TimeoutException) as exc:
            failure = self._failure(
                category=AIErrorCategory.TIMEOUT,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AITimeoutError("AI service timed out", failure=failure) from exc
        except (ConnectionError, httpx.NetworkError, httpx2.NetworkError) as exc:
            failure = self._failure(
                category=AIErrorCategory.CONNECTION,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AIServiceError("AI service connection failed", failure=failure) from exc
        except genai_errors.APIError as exc:
            failure = self._api_failure(exc)
            if failure.category is AIErrorCategory.TIMEOUT:
                raise AITimeoutError("AI service timed out", failure=failure) from exc
            raise AIServiceError("AI service request failed", failure=failure) from exc
        except genai_errors.UnknownApiResponseError as exc:
            failure = self._failure(
                category=AIErrorCategory.INVALID_RESPONSE,
                retryable=True,
                exception_type=type(exc).__name__,
            )
            raise AIServiceError("AI service returned an invalid response", failure=failure) from exc
        finally:
            owner.close()

        content = response.text
        if content is None or not content.strip():
            failure = self._failure(
                category=AIErrorCategory.INVALID_RESPONSE,
                retryable=True,
                exception_type="EmptyContent",
            )
            raise AIServiceError("AI service returned an empty response", failure=failure)
        return content


class FallbackAIClient:
    """Codyssey 실패가 재시도 가능한 경우 Gemini를 한 번 호출한다."""

    _FALLBACK_CATEGORIES = frozenset(
        {
            AIErrorCategory.TIMEOUT,
            AIErrorCategory.CONNECTION,
            AIErrorCategory.RATE_LIMIT,
            AIErrorCategory.UPSTREAM_5XX,
            AIErrorCategory.INVALID_RESPONSE,
        }
    )

    def __init__(
        self,
        *,
        primary: AIClient,
        fallback: AIClient | None,
        fallback_enabled: bool,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._fallback_enabled = fallback_enabled

    @staticmethod
    def _latency_ms(started_at: float) -> int:
        return round((perf_counter() - started_at) * 1_000)

    @staticmethod
    def _safe_failure(
        error: AIConfigurationError | AIServiceError | AITimeoutError,
        *,
        provider: str,
    ) -> AIProviderFailure:
        if error.failure is not None:
            return error.failure
        if isinstance(error, AITimeoutError):
            return AIProviderFailure(
                provider=provider,
                category=AIErrorCategory.TIMEOUT,
                status_code=None,
                retryable=True,
                exception_type=type(error).__name__,
            )
        if isinstance(error, AIConfigurationError):
            return AIProviderFailure(
                provider=provider,
                category=AIErrorCategory.CONFIGURATION,
                status_code=None,
                retryable=False,
                exception_type=type(error).__name__,
            )
        return AIProviderFailure(
            provider=provider,
            category=AIErrorCategory.UNKNOWN,
            status_code=None,
            retryable=False,
            exception_type=type(error).__name__,
        )

    @staticmethod
    def _set_skipped_fallback(
        error: AIServiceError | AITimeoutError,
        *,
        attempt: AIProviderAttempt,
        reason: AIFallbackReason,
    ) -> None:
        error.attempts = (attempt,)
        error.fallback_reason = reason

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        primary_started_at = perf_counter()
        try:
            primary_text = await self._primary.complete(messages)
        except (AITimeoutError, AIServiceError) as primary_error:
            primary_failure = self._safe_failure(
                primary_error,
                provider=CODYSSEY_PROVIDER,
            )
            primary_attempt = AIProviderAttempt(
                provider=CODYSSEY_PROVIDER,
                attempt=1,
                succeeded=False,
                latency_ms=self._latency_ms(primary_started_at),
                failure=primary_failure,
            )

            can_fallback = (
                primary_failure.provider == CODYSSEY_PROVIDER
                and primary_failure.retryable
                and primary_failure.category in self._FALLBACK_CATEGORIES
            )
            if not can_fallback:
                self._set_skipped_fallback(
                    primary_error,
                    attempt=primary_attempt,
                    reason=AIFallbackReason.NON_RETRYABLE,
                )
                raise
            if not self._fallback_enabled:
                self._set_skipped_fallback(
                    primary_error,
                    attempt=primary_attempt,
                    reason=AIFallbackReason.DISABLED,
                )
                raise
            if self._fallback is None:
                self._set_skipped_fallback(
                    primary_error,
                    attempt=primary_attempt,
                    reason=AIFallbackReason.NOT_CONFIGURED,
                )
                raise

            fallback_started_at = perf_counter()
            try:
                fallback_text = await self._fallback.complete(messages)
            except (AIConfigurationError, AITimeoutError, AIServiceError) as fallback_error:
                fallback_failure = self._safe_failure(
                    fallback_error,
                    provider=GEMINI_PROVIDER,
                )
                fallback_attempt = AIProviderAttempt(
                    provider=GEMINI_PROVIDER,
                    attempt=2,
                    succeeded=False,
                    latency_ms=self._latency_ms(fallback_started_at),
                    failure=fallback_failure,
                )
                attempts = (primary_attempt, fallback_attempt)
                both_timed_out = all(
                    attempt.failure is not None
                    and attempt.failure.category is AIErrorCategory.TIMEOUT
                    for attempt in attempts
                )
                if both_timed_out:
                    raise AITimeoutError(
                        "AI services timed out",
                        failure=fallback_failure,
                        attempts=attempts,
                    ) from fallback_error
                raise AIServiceError(
                    "AI services failed",
                    failure=fallback_failure,
                    attempts=attempts,
                ) from fallback_error

            fallback_attempt = AIProviderAttempt(
                provider=GEMINI_PROVIDER,
                attempt=2,
                succeeded=True,
                latency_ms=self._latency_ms(fallback_started_at),
            )
            return AICompletion(
                text=str(fallback_text),
                provider=GEMINI_PROVIDER,
                fallback_used=True,
                attempts=(primary_attempt, fallback_attempt),
            )

        primary_attempt = AIProviderAttempt(
            provider=CODYSSEY_PROVIDER,
            attempt=1,
            succeeded=True,
            latency_ms=self._latency_ms(primary_started_at),
        )
        return AICompletion(
            text=str(primary_text),
            provider=CODYSSEY_PROVIDER,
            fallback_used=False,
            attempts=(primary_attempt,),
        )


@lru_cache
def get_gemini_client() -> AIClient:
    """설정된 Gemini 클라이언트를 만들되 네트워크 연결은 호출 때까지 미룬다."""

    api_key = settings.gemini_api_key
    model = settings.gemini_model
    if api_key is None or not api_key.get_secret_value() or not model:
        return UnavailableAIClient()

    api_key_value = api_key.get_secret_value()
    timeout_ms = max(1, int(settings.gemini_timeout_seconds * 1000))

    def create_client() -> genai.Client:
        return genai.Client(
            api_key=api_key_value,
            http_options=genai_types.HttpOptions(
                timeout=timeout_ms,
                retry_options=genai_types.HttpRetryOptions(attempts=1),
            ),
        )

    return GeminiChatClient(client_factory=create_client, model=model)


@lru_cache
def get_ai_client() -> AIClient:
    """FastAPI 의존성으로 사용할 AI 클라이언트 팩토리.

    설정은 모듈의 상수나 실제 키로 복제하지 않고 ``app.config.settings``에서
    읽는다. 캐시된 인스턴스를 반환해 요청마다 HTTP 클라이언트를 새로 만들지
    않으며, 테스트에서는 FastAPI의 dependency override로 교체할 수 있다.
    """

    api_key = settings.ai_api_key
    if api_key is None or not api_key.get_secret_value():
        return UnavailableAIClient()

    client = AsyncOpenAI(
        api_key=api_key.get_secret_value(),
        base_url=settings.ai_base_url,
        timeout=settings.ai_timeout_seconds,
        max_retries=0,
    )
    primary = OpenAIChatClient(client=client, model=settings.ai_model)
    gemini_configured = (
        settings.gemini_api_key is not None
        and bool(settings.gemini_api_key.get_secret_value())
        and bool(settings.gemini_model)
    )
    fallback = (
        get_gemini_client()
        if settings.ai_fallback_enabled and gemini_configured
        else None
    )
    return FallbackAIClient(
        primary=primary,
        fallback=fallback,
        fallback_enabled=settings.ai_fallback_enabled,
    )
