"""환경 변수 로딩. 모든 설정 값은 여기서 한 번만 읽습니다."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"

    # .env 에 다른 팀원의 키(AI API 키 등)가 있어도 오류 없이 무시한다.
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
