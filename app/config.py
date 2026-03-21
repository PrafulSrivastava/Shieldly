from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://shieldher:shieldher@localhost:5432/shieldher",
        alias="DATABASE_URL",
    )

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # ── Auth ───────────────────────────────────────────────────────────────────
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=10080, alias="JWT_EXPIRE_MINUTES")

    # ── Firebase ───────────────────────────────────────────────────────────────
    firebase_project_id: str = Field(alias="FIREBASE_PROJECT_ID")
    # Required in production (MOCK_FIREBASE=false); safe to leave blank locally.
    firebase_api_key: str = Field(default="", alias="FIREBASE_API_KEY")

    # ── Twilio ─────────────────────────────────────────────────────────────────
    twilio_account_sid: str = Field(alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(alias="TWILIO_PHONE_NUMBER")

    # ── Google Maps ────────────────────────────────────────────────────────────
    google_maps_api_key: str = Field(alias="GOOGLE_MAPS_API_KEY")

    # ── Gemini ─────────────────────────────────────────────────────────────────
    gemini_api_key: str = Field(alias="GEMINI_API_KEY")

    # ── ElevenLabs ─────────────────────────────────────────────────────────────
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_agent_id: str = Field(default="", alias="ELEVENLABS_AGENT_ID")

    # ── Admin ──────────────────────────────────────────────────────────────────
    admin_api_key: str = Field(alias="ADMIN_API_KEY")

    # ── Mock toggles ───────────────────────────────────────────────────────────
    mock_firebase: bool = Field(default=False, alias="MOCK_FIREBASE")
    mock_sms: bool = Field(default=False, alias="MOCK_SMS")
    mock_maps: bool = Field(default=False, alias="MOCK_MAPS")
    mock_gemini: bool = Field(default=False, alias="MOCK_GEMINI")
    mock_push: bool = Field(default=False, alias="MOCK_PUSH")
    mock_elevenlabs: bool = Field(default=True, alias="MOCK_ELEVENLABS")

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"


settings = Settings()  # type: ignore[call-arg]
