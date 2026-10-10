"""환경 변수 로딩. 모든 설정 값은 여기서 한 번만 읽습니다."""
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"

    # 세션 쿠키 서명용 키. 기본값을 두지 않아 .env 에 없으면 시작 시 오류가 난다.
    secret_key: str
    session_max_age_seconds: int = 60 * 60 * 24
    # HTTPS 로 서비스할 때만 true. HTTP 배포에서 true 로 두면 쿠키가 전송되지 않아 로그인이 안 된다.
    session_cookie_secure: bool = False

    # AI 키는 앱의 인증/헬스체크 기능까지 막지 않도록 설정 단계에서는 선택값으로 읽는다.
    # 실제 AI 호출에 키가 반드시 필요한지는 AI 클라이언트를 생성할 때 검사한다.
    ai_api_key: SecretStr | None = None
    ai_base_url: str = "https://copa.codyssey.kr/v1"
    ai_model: str = "gpt-5.4"
    ai_timeout_seconds: float = 20

    # .env 에 아직 정의하지 않은 다른 팀원의 설정이 있어도 오류 없이 무시한다.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
