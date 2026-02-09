"""Application configuration via Pydantic Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./dg_core.db"

    # LLM
    llm_provider: str = "mock"  # "openai" | "anthropic" | "mock"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # RAG
    rag_enabled: bool = False
    rag_persist_dir: str = "./chroma_data"
    embedding_provider: str = "local"
    embedding_model: str = "all-MiniLM-L6-v2"

    # Dice
    default_dice_type: int = 6

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
