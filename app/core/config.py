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
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "deepseek-ai/deepseek-v4-pro-0813"
    nvidia_timeout_seconds: float = 120
    nvidia_max_tokens: int = 16384
    market_baseline_admin_key: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    smtp_use_tls: bool = False
    auth_dev_auto_verify_email: bool = True
    supabase_storage_endpoint: str = ""
    supabase_storage_region: str = ""
    supabase_storage_access_key_id: str = ""
    supabase_storage_secret_access_key: str = ""
    supabase_storage_bucket: str = "career-evidence"

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

    @property
    def evidence_storage_configured(self) -> bool:
        return bool(
            self.supabase_storage_endpoint
            and self.supabase_storage_region
            and self.supabase_storage_access_key_id
            and self.supabase_storage_secret_access_key
            and self.supabase_storage_bucket
        )

    @property
    def nvidia_configured(self) -> bool:
        return bool(self.nvidia_api_key and self.nvidia_base_url and self.nvidia_model)

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
