from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Fabric Warehouse"
    env: str = "dev"
    secret_key: str = "change-me"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/fabric_warehouse"
    fabric_db_path: str = r"D:\Data Analyst\Python\Visual Code Studio\Hello\fabric.db"


settings = Settings()
