"""application settings using pydantic-settings.

loads configuration from environment variables (or .env file).
validates types at startup—fail fast if config is invalid.

usage:
    from src.config import get_settings
    settings = get_settings()
    print(settings.database_url)

environment variables are loaded with these priorities:
1. actual environment variables
2. .env file in project root
3. default values defined here
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """application settings loaded from environment."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # --- app ---
    app_name: str = "FuelFlow"
    debug: bool = False
    
    # --- database ---
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fuelflow"
    
    # --- redis ---
    redis_url: str = "redis://localhost:6379/0"
    
    # --- whatsapp cloud api ---
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_webhook_secret: str = ""
    whatsapp_api_version: str = "v18.0"
    
    # --- security ---
    secret_key: str = "change-me-in-production"
    
    # --- business rules ---
    order_min_liters: float = 10.0
    order_max_liters: float = 10000.0
    session_ttl_seconds: int = 3600
    
    # --- feature flags ---
    enable_signature_verification: bool = True
    enable_iot_endpoints: bool = False


@lru_cache
def get_settings() -> Settings:
    """get cached settings instance."""
    return Settings()