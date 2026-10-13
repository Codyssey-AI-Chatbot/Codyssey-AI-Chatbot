"""AI 챗봇 파이프라인에서 사용하는 내부 예외와 안전한 실패 정보."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class AIErrorCategory(str, Enum):
    """공급자와 무관하게 로그와 fallback 판단에 사용하는 오류 범주."""

    CONFIGURATION = "configuration"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    UPSTREAM_4XX = "upstream_4xx"
    UPSTREAM_5XX = "upstream_5xx"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


class AIFallbackReason(str, Enum):
    """Fallback을 호출하지 않은 안전한 내부 사유."""

    DISABLED = "disabled"
    NOT_CONFIGURED = "not_configured"
    NON_RETRYABLE = "non_retryable"


@dataclass(frozen=True, slots=True)
class AIProviderFailure:
    """공급자 실패에서 로그에 남겨도 되는 필드만 보관한다.

    SDK 예외 메시지, 응답 본문, 헤더, URL, API 키는 의도적으로 필드에
    포함하지 않는다. ``exception_type``에는 예외 클래스 이름만 넣는다.
    """

    provider: str
    category: AIErrorCategory
    status_code: int | None
    retryable: bool
    exception_type: str


@dataclass(frozen=True, slots=True)
class AIProviderAttempt:
    """AI 공급자 한 번의 시도 결과를 나타내는 안전한 메타데이터."""

    provider: str
    attempt: int
    succeeded: bool
    latency_ms: int
    failure: AIProviderFailure | None = None


class AIError(Exception):
    """AI 처리 중 발생한 예상 가능한 오류의 기본 클래스."""

    def __init__(
        self,
        message: str,
        *,
        failure: AIProviderFailure | None = None,
        attempts: Sequence[AIProviderAttempt] = (),
        fallback_reason: AIFallbackReason | None = None,
    ) -> None:
        super().__init__(message)
        self.failure = failure
        self.attempts = tuple(attempts)
        self.fallback_reason = fallback_reason


class AIConfigurationError(AIError):
    """AI 서비스에 필요한 서버 설정이 준비되지 않은 경우."""


class AITimeoutError(AIError):
    """AI 공급자가 제한 시간 안에 응답하지 않은 경우."""


class AIServiceError(AIError):
    """AI 공급자 호출 또는 응답 형식이 올바르지 않은 경우."""
