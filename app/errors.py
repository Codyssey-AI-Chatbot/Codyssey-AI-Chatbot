"""AI 챗봇 파이프라인에서 사용하는 내부 예외."""


class AIError(Exception):
    """AI 처리 중 발생한 예상 가능한 오류의 기본 클래스."""


class AITimeoutError(AIError):
    """AI 공급자가 제한 시간 안에 응답하지 않은 경우."""


class AIServiceError(AIError):
    """AI 공급자 호출 또는 응답 형식이 올바르지 않은 경우."""
