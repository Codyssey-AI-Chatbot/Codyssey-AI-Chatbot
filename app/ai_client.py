"""AI 공급자와 라우터 사이의 공통 인터페이스.

라우터는 OpenAI 같은 특정 SDK 대신 이 모듈의 타입에만 의존한다.
테스트에서는 FastAPI의 ``dependency_overrides``를 사용해
``get_ai_client``가 가짜 클라이언트를 반환하도록 바꿀 수 있다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
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


@dataclass(frozen=True, slots=True)
class AICompletion:
    """최종 답변과 공급자별 시도 결과.

    F-02에서는 구조만 정의한다. 기존 라우터 호환성을 위해 현재
    ``AIClient.complete``의 문자열 반환 계약은 유지하며, fallback과 라우터
    통합 단계에서 이 결과형을 연결한다.
    """

    text: str
    provider: str
    fallback_used: bool
    attempts: tuple[AIProviderAttempt, ...]


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
    return OpenAIChatClient(client=client, model=settings.ai_model)
