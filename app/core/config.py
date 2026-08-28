from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    debug: bool = False
    frontend_url: str = "http://localhost:5173"
    backend_url: str = "http://localhost:8000"
    cors_allow_all: bool = True
    cors_origins: str = "http://localhost:5173"
    cors_origin_regex: str | None = None
    jwt_secret_key: str = ""
    jwt_access_token_minutes: int = 60
    google_client_id: str = ""
    google_client_secret: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    smtp_use_tls: bool = False
    auth_dev_auto_verify_email: bool = True

    @property
    def allowed_frontend_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]

    @property
    def email_delivery_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
