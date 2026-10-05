from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    jwt_algorithm: str = "HS256"
    log_level: str = "INFO"
    log_json: bool = False
    enable_docs: bool = False
    rate_limit_backend: str = "postgres"
    rate_limit_login_attempts: int = 5
    rate_limit_login_window_seconds: int = 900  # 15 minutes
    rate_limit_register_attempts: int = 3
    rate_limit_register_window_seconds: int = 3600  # 1 hour
    rate_limit_refresh_attempts: int = 20
    rate_limit_refresh_window_seconds: int = 900
    rate_limit_login_account_attempts: int = 10
    rate_limit_login_account_window_seconds: int = 900  # 15 minutes
    gcs_bucket_name: str = ""
    gcs_signer_service_account: str = ""
    attachment_upload_url_expire_minutes: int = 15
    attachment_download_url_expire_minutes: int = 15
    attachment_max_size_mb: int = 25

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
