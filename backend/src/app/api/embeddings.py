from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List

import requests
from app.api.config import settings

logger = logging.getLogger(__name__)


class EmbeddingBackend(ABC):
    """Embedding 后端抽象基类。"""

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为嵌入向量列表。

        Args:
            texts: 待嵌入的文本列表。

        Returns:
            与输入等长的二维浮点向量列表。
        """
        ...

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """返回当前模型输出的向量维度。"""
        ...


class OpenAIEmbeddingBackend(EmbeddingBackend):
    """OpenAI 兼容接口 Embedding 后端。"""

    def __init__(self, api_key: str, base_url: str | None, model: str, vector_size: int):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._vector_size = vector_size
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url or None,
            )
        return self._client

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        client = self._get_client()
        # DashScope 等部分兼容接口限制 batch size <= 10，稳妥起见分批次调用
        batch_size = 10
        results: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            resp = client.embeddings.create(model=self._model, input=batch)
            results.extend([d.embedding for d in resp.data])
        return results

    @property
    def vector_size(self) -> int:
        return self._vector_size


class OllamaEmbeddingBackend(EmbeddingBackend):
    """Ollama 本地 Embedding 后端。"""

    def __init__(self, host: str, model: str, vector_size: int):
        self._host = host.rstrip("/")
        self._model = model
        self._vector_size = vector_size

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        results: List[List[float]] = []
        # Ollama /api/embed 支持单条或批量；为兼容不同版本逐条请求
        for text in texts:
            try:
                resp = requests.post(
                    f"{self._host}/api/embed",
                    json={"model": self._model, "input": text},
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                # Ollama 返回格式: {"embedding": [...]}
                embedding = data.get("embedding")
                if embedding is None:
                    # 某些版本返回 embeddings 列表
                    embeddings = data.get("embeddings", [])
                    embedding = embeddings[0] if embeddings else []
                results.append(embedding)
            except Exception as e:
                logger.error("Ollama embed failed for text %r: %s", text[:50], e)
                raise
        return results

    @property
    def vector_size(self) -> int:
        return self._vector_size


# 全局单例缓存
_embedding_backend: EmbeddingBackend | None = None


def get_embedding_backend() -> EmbeddingBackend:
    """获取（或懒加载）全局 Embedding 后端实例。

    根据 ``EMBEDDING_PROVIDER`` 环境变量自动选择后端：

    - ``openai`` → OpenAI 兼容接口（默认）
    - ``ollama`` → 本地 Ollama 服务
    """
    global _embedding_backend
    if _embedding_backend is not None:
        return _embedding_backend

    provider = (settings.EMBEDDING_PROVIDER or "openai").lower()
    model = settings.EMBEDDING_MODEL_NAME
    dim = settings.EMBEDDING_DIM

    if provider == "ollama":
        host = settings.OLLAMA_HOST or "http://localhost:11434"
        logger.info("Embedding backend: Ollama (%s @ %s, dim=%d)", model, host, dim)
        _embedding_backend = OllamaEmbeddingBackend(
            host=host, model=model, vector_size=dim
        )
    else:
        # OpenAI 兼容接口
        api_key = settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY or ""
        base_url = settings.EMBEDDING_BASE_URL or settings.OPENAI_BASE_URL or settings.LLM_BASE_URL or None
        if not api_key:
            raise RuntimeError(
                "No embedding API key configured. Set EMBEDDING_API_KEY, OPENAI_API_KEY or DEEPSEEK_API_KEY."
            )
        logger.info(
            "Embedding backend: OpenAI-compatible (model=%s, base_url=%s, dim=%d, key_prefix=%s...)",
            model, base_url, dim, api_key[:8] if api_key else "N/A",
        )
        _embedding_backend = OpenAIEmbeddingBackend(
            api_key=api_key,
            base_url=base_url,
            model=model,
            vector_size=dim,
        )

    return _embedding_backend


def reset_embedding_backend() -> None:
    """重置全局 Embedding 后端（主要用于测试）。"""
    global _embedding_backend
    _embedding_backend = None
