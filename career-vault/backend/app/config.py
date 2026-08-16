from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Career Vault"
    environment: str = "local"
    ollama_base_url: str = "http://127.0.0.1:11434"
    generation_model: str = "qwen3:4b"
    embedding_model: str = "embeddinggemma:300m-qat-q4_0"
    database_url: str = "sqlite:///../../data/career-vault.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
project_root = Path(__file__).resolve().parents[2]
data_directory = project_root / "data"
database_path = data_directory / "career-vault.db"
