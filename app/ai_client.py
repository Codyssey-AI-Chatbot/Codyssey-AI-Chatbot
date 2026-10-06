"""AI 공급자와 라우터 사이의 공통 인터페이스.

라우터는 OpenAI 같은 특정 SDK 대신 이 모듈의 타입에만 의존한다.
테스트에서는 FastAPI의 ``dependency_overrides``를 사용해
``get_ai_client``가 가짜 클라이언트를 반환하도록 바꿀 수 있다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

from openai import AsyncOpenAI

from app.config import settings


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


class OpenAIChatClient:
    """OpenAI 호환 Chat Completions API를 사용하는 구현체."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(self, messages: Sequence[ChatMessage]) -> str:
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": message.role, "content": message.content}
                for message in messages
            ],
        )
        return completion.choices[0].message.content or ""


@lru_cache
def get_ai_client() -> AIClient:
    """FastAPI 의존성으로 사용할 AI 클라이언트 팩토리.

    설정은 모듈의 상수나 실제 키로 복제하지 않고 ``app.config.settings``에서
    읽는다. 캐시된 인스턴스를 반환해 요청마다 HTTP 클라이언트를 새로 만들지
    않으며, 테스트에서는 FastAPI의 dependency override로 교체할 수 있다.
    """

    api_key = settings.ai_api_key
    if api_key is None or not api_key.get_secret_value():
        raise RuntimeError("AI_API_KEY is not configured")

    client = AsyncOpenAI(
        api_key=api_key.get_secret_value(),
        base_url=settings.ai_base_url,
    )
    return OpenAIChatClient(client=client, model=settings.ai_model)
