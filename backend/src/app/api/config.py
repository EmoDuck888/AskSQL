"""NL2SQL API 配置 — 环境变量驱动。"""
import os
from typing import List

# Ensure .env is loaded even when this module is imported before main.py
from dotenv import load_dotenv
_script_dir = os.path.dirname(os.path.abspath(__file__))
for _env_path in (
    os.path.join(_script_dir, ".env"),
    os.path.join(_script_dir, "..", ".env"),
    os.path.join(_script_dir, "..", "..", ".env"),
):
    if os.path.exists(_env_path):
        load_dotenv(_env_path, override=True)
        break

class Settings:
    HOST: str = os.getenv("API_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("API_PORT", "8000"))
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    FALKORDB_HOST: str = os.getenv("FALKORDB_HOST", "localhost")
    FALKORDB_PORT: int = int(os.getenv("FALKORDB_PORT", "6379"))
    FALKORDB_USERNAME: str = os.getenv("FALKORDB_USERNAME", "")
    FALKORDB_PASSWORD: str = os.getenv("FALKORDB_PASSWORD", "")

    # --- LLM 配置（与大模型独立） ---
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", os.getenv("LLM_API_KEY", ""))

    # --- Embedding 配置（与大模型完全独立） ---
    # 提供商：openai | ollama
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "openai")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "")
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "1024"))
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    GENERAL_PREFIX: str = os.getenv("GENERAL_PREFIX", "general_")

    @property
    def falkordb_url(self) -> str:
        return f"redis://{self.FALKORDB_HOST}:{self.FALKORDB_PORT}"

settings = Settings()