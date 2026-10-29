"""Application settings loaded from environment variables (see .env.example)."""

import ssl
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(url: str) -> str:
    """Ensure postgres URLs use the asyncpg SQLAlchemy driver."""
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    return url


def classify_database_host(hostname: str | None) -> str:
    """Classify DB host for connection settings (no credentials)."""
    if not hostname:
        return "missing"
    if hostname in {"localhost", "127.0.0.1", "db"}:
        return "local"
    if "supabase.co" in hostname or "supabase.com" in hostname:
        return "supabase"
    if hostname.startswith("dpg-") and ".render.com" not in hostname:
        return "render_internal"
    if hostname.endswith(".render.com") or "postgres.render.com" in hostname:
        return "render_external"
    return "other"


def is_supabase_pooler(url: str) -> bool:
    """True when the URL targets Supabase's PgBouncer pooler (transaction mode)."""
    parsed = urlparse(url)
    if classify_database_host(parsed.hostname) != "supabase":
        return False
    port = parsed.port or 5432
    return port == 6543 or "pooler" in (parsed.hostname or "")


def database_connect_args(url: str) -> dict:
    """asyncpg connect_args based on database host (Supabase, Render, local, etc.)."""
    parsed = urlparse(url)
    host_kind = classify_database_host(parsed.hostname)

    if host_kind in {"local", "missing"}:
        return {}

    if host_kind == "render_internal":
        return {"ssl": False}

    if host_kind == "supabase":
        connect_args: dict = {"ssl": "require"}
        if is_supabase_pooler(url):
            connect_args["statement_cache_size"] = 0
            connect_args["prepared_statement_cache_size"] = 0
            connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"
        return connect_args

    return {"ssl": ssl.create_default_context()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sms_service"
    test_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sms_service_test"
    environment: str = "development"

    nedarim_mosad_id: str = "7018669"
    nedarim_api_password: str = ""
    nedarim_webhook_secret: str = ""
    nedarim_hmac_max_skew_seconds: int = 300

    yemot_api_key: str = ""
    yemot_sms_from: str = ""
    yemot_api_base_url: str = "https://www.call2all.co.il/ym/api"

    greenapi_id_instance: str = ""
    greenapi_api_token: str = ""
    greenapi_api_url: str = "https://api.green-api.com"

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def ensure_async_postgres_driver(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value


settings = Settings()
