from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI-Powered Smart Library Management Assistant"
    environment: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    backend_url: str = "http://127.0.0.1:8000"

    # LLM Provider ("groq" or "local")
    llm_provider: str = "groq"

    # Groq Settings
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Local Ollama Settings
    local_llm_base_url: str = "http://localhost:11434"
    local_llm_model: str = "llama3.2"

    # Local Embeddings Settings
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Storage Settings
    sqlite_db_url: str = "sqlite:///./data/library.db"
    chroma_persist_dir: str = "./data/chroma_db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
