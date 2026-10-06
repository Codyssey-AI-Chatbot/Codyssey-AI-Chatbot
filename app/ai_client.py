"""AI 공급자와 라우터 사이의 공통 인터페이스.

라우터는 OpenAI 같은 특정 SDK 대신 이 모듈의 타입에만 의존한다.
테스트에서는 FastAPI의 ``dependency_overrides``를 사용해
``get_ai_client``가 가짜 클라이언트를 반환하도록 바꿀 수 있다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol


ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """AI에 전달할 공급자 독립적인 대화 메시지."""

    role: ChatRole
    content: str


class AIClient(Protocol):
    """AI 답변 생성기가 따라야 하는 비동기 인터페이스."""

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        """대화 메시지를 받아 생성된 텍스트 답변을 반환한다."""
        ...


def get_ai_client() -> AIClient:
    """FastAPI 의존성으로 사용할 AI 클라이언트 팩토리.

    실제 공급자 구현은 B-02에서 연결한다. 그전까지 호출되면 조용히
    실패하거나 가짜 응답을 만들지 않고 설정되지 않았음을 명확히 알린다.
    """

    raise RuntimeError("AI client is not configured")
