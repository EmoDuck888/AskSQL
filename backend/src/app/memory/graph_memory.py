from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import typing
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from app.graphdb.client import get_falkordb
from app.api.embeddings import get_embedding_backend
from app.core.settings import settings
from app.api.config import settings as api_settings

logger = logging.getLogger(__name__)

# Optional TTL (seconds) for the memory graph Redis key.
MEMORY_TTL_SECONDS: Optional[int] = (
    int(os.environ["MEMORY_TTL_SECONDS"])
    if os.environ.get("MEMORY_TTL_SECONDS")
    else None
)

# graphiti_core may not be installed in all environments; degrade gracefully.
try:
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client import LLMConfig, LLMClient
    from graphiti_core.llm_client.config import DEFAULT_MAX_TOKENS, ModelSize
    from graphiti_core.llm_client.errors import RateLimitError
    from graphiti_core.embedder import OpenAIEmbedder, OpenAIEmbedderConfig
    from graphiti_core.cross_encoder import OpenAIRerankerClient
    from graphiti_core.search.search_config import SearchConfig, SearchResults
    from graphiti_core.search.search_config_recipes import (
        COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
    )
    from graphiti_core.prompts.models import Message
    from pydantic import BaseModel

    _GRAPHITI_AVAILABLE = True
except ImportError:
    _GRAPHITI_AVAILABLE = False
    logger.warning("graphiti_core not installed; memory will be disabled.")

# LangChain for robust structured output across providers (DeepSeek, etc.)
try:
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Monkey-patch: graphiti-core OpenAIRerankerClient.rank() uses zip(..., strict=True)
# which crashes when the LLM returns fewer scores than passages (logprobs=None).
# Replace with a safe version that pads missing scores with 0.0.
# ---------------------------------------------------------------------------
if _GRAPHITI_AVAILABLE:
    import numpy as np
    from graphiti_core.cross_encoder.openai_reranker_client import (
        OpenAIRerankerClient as _OpenAIRerankerClient,
    )
    from graphiti_core.helpers import semaphore_gather
    from graphiti_core.prompts import Message

    _original_rank = _OpenAIRerankerClient.rank

    async def _patched_rank(self, query: str, passages: list[str]) -> list[tuple[str, float]]:
        openai_messages_list = [
            [
                Message(
                    role='system',
                    content='You are an expert tasked with determining whether the passage is relevant to the query',
                ),
                Message(
                    role='user',
                    content=f"""
                           Respond with "True" if PASSAGE is relevant to QUERY and "False" otherwise.
                           <PASSAGE>
                           {passage}
                           </PASSAGE>
                           <QUERY>
                           {query}
                           </QUERY>
                           """,
                ),
            ]
            for passage in passages
        ]
        try:
            responses = await semaphore_gather(
                *[
                    self.client.chat.completions.create(
                        model=self.config.model or 'gpt-4.1-nano',
                        messages=openai_messages,
                        temperature=0,
                        max_tokens=1,
                        logit_bias={'6432': 1, '7983': 1},
                        logprobs=True,
                        top_logprobs=2,
                    )
                    for openai_messages in openai_messages_list
                ]
            )

            responses_top_logprobs = [
                response.choices[0].logprobs.content[0].top_logprobs
                if response.choices[0].logprobs is not None
                and response.choices[0].logprobs.content is not None
                else []
                for response in responses
            ]
            scores: list[float] = []
            for top_logprobs in responses_top_logprobs:
                if len(top_logprobs) == 0:
                    scores.append(0.0)
                    continue
                norm_logprobs = np.exp(top_logprobs[0].logprob)
                if top_logprobs[0].token.strip().split(' ')[0].lower() == 'true':
                    scores.append(norm_logprobs)
                else:
                    scores.append(1 - norm_logprobs)

            # Safe zip: pad missing scores with 0.0 instead of crashing
            if len(scores) < len(passages):
                scores.extend([0.0] * (len(passages) - len(scores)))
            results = [(passage, score) for passage, score in zip(passages, scores)]
            results.sort(reverse=True, key=lambda x: x[1])
            return results
        except Exception as e:
            logger.error(f'Error in generating LLM response: {e}')
            raise

    _OpenAIRerankerClient.rank = _patched_rank

    # -----------------------------------------------------------------------
    # Helpers: robust JSON extraction and brute-force field normalization.
    # These are used by CompatibleLLMClient to handle reasoning models that
    # do not follow exact schema field names (e.g. DeepSeek R1).
    # -----------------------------------------------------------------------

    def _extract_json(text: str) -> Any:
        """Extract the largest JSON object or array from CoT-wrapped / markdown text."""
        if not text:
            return {}
        # 1. fenced ```json ... ```
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except json.JSONDecodeError:
                    pass
        # 2. fenced ``` ... ```
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                candidate = text[start:end].strip()
                if candidate.startswith("{") or candidate.startswith("["):
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
        # 3. outermost brackets [ ... ] — checked before braces so arrays win
        depth = 0
        start_idx = None
        for i, ch in enumerate(text):
            if ch == "[":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0 and start_idx is not None:
                    try:
                        result = json.loads(text[start_idx : i + 1])
                        if isinstance(result, list):
                            return {"extracted_entities": result}
                        return result
                    except json.JSONDecodeError:
                        pass
        # 4. outermost braces { ... }
        depth = 0
        start_idx = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start_idx is not None:
                    try:
                        return json.loads(text[start_idx : i + 1])
                    except json.JSONDecodeError:
                        pass
        return {}

    # Recursive key aliases — applied to *every* dict at *every* nesting level.
    _KEY_ALIASES: dict[str, str] = {
        "entity_name": "name",
        "node_name": "name",
        "entity_type": "entity_type_id",
        "type_id": "entity_type_id",
        "episode_index": "episode_indices",
        "source": "source_entity_name",
        "target": "target_entity_name",
        "relation": "relation_type",
        "candidate_id": "duplicate_candidate_id",
    }

    # Top-level key aliases — only applied at the root object level.
    _TOP_LEVEL_ALIASES: dict[str, str] = {
        "entities": "extracted_entities",
        "entity_nodes": "extracted_entities",
        "nodes": "extracted_entities",
        "extracted_nodes": "extracted_entities",
        "node_list": "extracted_entities",
        "entity_list": "extracted_entities",
        "named_entities": "extracted_entities",
        "recognized_entities": "extracted_entities",
        "resolutions": "entity_resolutions",
        "duplicate_resolutions": "entity_resolutions",
        "node_resolutions": "entity_resolutions",
        "duplicates": "entity_resolutions",
        "resolution_list": "entity_resolutions",
        "entity_duplicates": "entity_resolutions",
        "merged_entities": "entity_resolutions",
        "summary_list": "summaries",
        "entity_summaries": "summaries",
        "summarized_entities": "summaries",
        "summary_updates": "summaries",
        "updated_summaries": "summaries",
        "facts": "edges",
        "relationships": "edges",
        "extracted_edges": "edges",
        "edge_list": "edges",
        "relations": "edges",
        "connections": "edges",
        "links": "edges",
        "timestamp_list": "timestamps",
        "edge_timestamps": "timestamps",
        "temporal_bounds": "timestamps",
        "date_ranges": "timestamps",
    }

    def _normalize_keys(obj: Any) -> Any:
        """Recursively replace known alias keys with canonical field names."""
        if isinstance(obj, dict):
            return {_KEY_ALIASES.get(k, k): _normalize_keys(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_normalize_keys(item) for item in obj]
        return obj

    def _normalize_top_level(data: dict) -> dict:
        """Apply top-level field aliases."""
        for alias, canonical in _TOP_LEVEL_ALIASES.items():
            if alias in data and canonical not in data:
                data[canonical] = data.pop(alias)
        return data

    def _remap_fields_by_content(data: dict) -> dict:
        """Heuristic remapping: when LLM returns `extracted_entities` but the
        inner items match a different expected model, fix the top-level key.

        This compensates for providers (e.g. DeepSeek) that ignore the exact
        schema field name when `json_schema` is unavailable and fall back to a
        generic `extracted_entities` wrapper.
        """
        if "extracted_entities" not in data:
            return data

        items = data["extracted_entities"]
        if not isinstance(items, list) or not items:
            return data

        first = items[0]
        if not isinstance(first, dict):
            return data

        # Edge data contains source/target entity names or relation types
        if "edges" not in data and any(
            k in first for k in ("source_entity_name", "target_entity_name", "relation_type")
        ):
            data["edges"] = data.pop("extracted_entities")
            return data

        # Node-resolution data contains duplicate_candidate_id
        if "entity_resolutions" not in data and "duplicate_candidate_id" in first:
            data["entity_resolutions"] = data.pop("extracted_entities")
            return data

        # Node-extraction data: keep as extracted_entities (already correct)
        return data

    def _normalize_response(data: Any) -> Any:
        """Full normalization: recursive key aliases + top-level aliases +
        heuristic content-based remapping."""
        data = _normalize_keys(data)
        if isinstance(data, dict):
            data = _normalize_top_level(data)
            data = _remap_fields_by_content(data)
        return data

    # -----------------------------------------------------------------------
    # CompatibleLLMClient — custom LLM client for DeepSeek / reasoning models.
    #
    # Architecture (same pattern as OpenAIGenericClient):
    #   - Inherits LLMClient directly.
    #   - Implements _generate_response only.
    #   - Reasoning models: NO response_format, free-form output + robust JSON
    #     extraction + brute-force field name normalization.
    #   - Regular models: json_schema -> json_object fallback.
    #   - No monkey-patching required.
    # -----------------------------------------------------------------------
    class CompatibleLLMClient(LLMClient):
        """OpenAI-compatible LLM client with explicit reasoning-model support."""

        MAX_RETRIES = 2

        def __init__(
            self,
            config: LLMConfig | None = None,
            cache: bool = False,
            client: typing.Any = None,
            max_tokens: int = DEFAULT_MAX_TOKENS,
            force_non_reasoning: bool = False,
        ):
            if cache:
                raise NotImplementedError("Caching is not implemented for CompatibleLLMClient")

            if config is None:
                config = LLMConfig()

            super().__init__(config, cache)
            self.max_tokens = max_tokens
            self.force_non_reasoning = force_non_reasoning

            if client is None:
                self.client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
            else:
                self.client = client

        def _is_reasoning_model(self, model: str) -> bool:
            if self.force_non_reasoning:
                return False
            m = model.lower()
            return any(x in m for x in ("r1", "reasoner", "o1", "o3", "deepseek-reasoner"))

        def _convert_messages(self, messages: list[Message]) -> list[dict]:
            """Convert internal Message format to OpenAI-compatible dicts."""
            return [
                {"role": m.role, "content": self._clean_input(m.content)}
                for m in messages
                if m.role in ("user", "system")
            ]

        async def _generate_response(
            self,
            messages: list[Message],
            response_model: type[BaseModel] | None = None,
            max_tokens: int = DEFAULT_MAX_TOKENS,
            model_size: ModelSize = ModelSize.medium,
        ) -> dict[str, typing.Any]:
            if not _LANGCHAIN_AVAILABLE:
                raise RuntimeError(
                    "langchain-openai is required for CompatibleLLMClient. "
                    "Install it with: pip install langchain-openai"
                )

            model = self.model or "gpt-4.1-mini"
            if model_size == ModelSize.small:
                model = self.small_model or model

            reasoning = self._is_reasoning_model(model)

            # Extract credentials from the existing AsyncOpenAI client
            base_url = str(self.client.base_url) if self.client.base_url else None

            # LangChain ChatOpenAI handles provider differences (json_schema vs
            # function_calling vs json_mode) automatically via with_structured_output.
            llm = ChatOpenAI(
                model=model,
                api_key=self.client.api_key,
                base_url=base_url,
                temperature=0.0 if reasoning else self.temperature,
                max_tokens=max_tokens or self.max_tokens,
            )

            # Convert graphiti Message → LangChain messages
            lc_messages: list[SystemMessage | HumanMessage] = []
            for m in messages:
                cleaned = self._clean_input(m.content)
                if m.role == "system":
                    lc_messages.append(SystemMessage(content=cleaned))
                elif m.role == "user":
                    lc_messages.append(HumanMessage(content=cleaned))

            if response_model is not None and not reasoning:
                # Providers like DeepSeek do NOT support json_schema but DO support
                # function calling. For known non-OpenAI providers we force
                # method="function_calling" so LangChain skips the json_schema probe
                # and goes straight to tool-calling, avoiding the 400 error.
                model_lower = model.lower()
                force_function_calling = any(
                    p in model_lower
                    for p in ("deepseek", "groq", "qwen", "llama", "mistral")
                )
                method: str | None = "function_calling" if force_function_calling else None

                structured_llm = llm.with_structured_output(
                    response_model,
                    method=method,  # type: ignore[arg-type]
                )
                result = await structured_llm.ainvoke(lc_messages)
                return result.model_dump()
            else:
                # Reasoning models or free-form output
                result = await llm.ainvoke(lc_messages)
                parsed = _extract_json(result.content)
                if not parsed and response_model is not None:
                    raise json.JSONDecodeError(
                        f"No valid JSON found in model response. Raw content: {result.content[:500]}",
                        result.content,
                        0,
                    )
                parsed = _normalize_response(parsed)
                if isinstance(parsed, list):
                    raise json.JSONDecodeError(
                        f"Model returned JSON array instead of object: {result.content[:500]}",
                        result.content,
                        0,
                    )
                return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Module-level cache for AsyncOpenAI clients to avoid connection leaks.
_OPENAI_CLIENT_CACHE: Dict[str, AsyncOpenAI] = {}


def _get_async_openai_client(
    api_key: str | None = None, base_url: str | None = None
) -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client."""
    cache_key = f"{base_url or 'default'}:{api_key or 'default'}"
    if cache_key not in _OPENAI_CLIENT_CACHE:
        key = api_key or settings.LLM_API_KEY or api_settings.OPENAI_API_KEY or ""
        url = base_url or settings.LLM_BASE_URL or api_settings.OPENAI_BASE_URL or None
        _OPENAI_CLIENT_CACHE[cache_key] = AsyncOpenAI(api_key=key, base_url=url)
    return _OPENAI_CLIENT_CACHE[cache_key]


def _strip_provider_prefix(model_name: str) -> str:
    """Remove provider prefix like 'openai/' or 'azure/' from model name."""
    if "/" in model_name:
        return model_name.split("/", 1)[1]
    return model_name


def _create_graphiti_client(memory_db_name: str) -> Optional[Graphiti]:
    """Build a Graphiti client wired to the backend's FalkorDB / LLM / embedder."""
    if not _GRAPHITI_AVAILABLE:
        return None

    # -- Graph driver --
    falkordb = get_falkordb().db
    driver = FalkorDriver(falkor_db=falkordb, database=memory_db_name)

    # -- Dedicated non-reasoning model for Graphiti structured extraction --
    # Graphiti's entity/edge extraction relies on strict Pydantic structured output.
    # Reasoning models (R1, o1, o3) do not support response_format/json_schema well.
    # We therefore default to a lightweight non-reasoning model (deepseek-chat).
    # Override via GRAPHITI_LLM_MODEL env var if desired.
    llm_model = _strip_provider_prefix(
        os.environ.get("GRAPHITI_LLM_MODEL", "deepseek-chat")
    )
    aoai = _get_async_openai_client()

    llm_client = CompatibleLLMClient(
        config=LLMConfig(model=llm_model),
        client=aoai,
        force_non_reasoning=True,
    )

    # -- Embedder --
    embed_backend = get_embedding_backend()
    embed_model = _strip_provider_prefix(api_settings.EMBEDDING_MODEL_NAME)

    if api_settings.EMBEDDING_PROVIDER == "ollama":
        embed_base = api_settings.OLLAMA_HOST.rstrip("/") + "/v1"
        embed_key = api_settings.EMBEDDING_API_KEY or "ollama"
    else:
        embed_base = api_settings.EMBEDDING_BASE_URL or settings.LLM_BASE_URL
        embed_key = api_settings.EMBEDDING_API_KEY or settings.LLM_API_KEY or ""

    embed_aoai = _get_async_openai_client(base_url=embed_base, api_key=embed_key)
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model=embed_model,
            embedding_dim=embed_backend.vector_size,
        ),
        client=embed_aoai,
    )

    # -- Reranker (uses the same LLM) --
    reranker = OpenAIRerankerClient(
        config=LLMConfig(model=llm_model),
        client=aoai,
    )

    return Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=reranker,
        max_coroutines=5,
    )


async def _call_llm(messages: list[dict], temperature: float = 0.0) -> str:
    """Call the configured LLM via OpenAI-compatible API."""
    client = _get_async_openai_client()
    resp = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# 进程级缓存：每个 (user_id, graph_id) 组合只初始化一次 GraphMemoryTool。
# Graphiti 客户端是长生命周期对象（自带 max_coroutines 并发控制），
# 重复 init 只会白白重复建索引/建实体节点等幂等操作，没有任何语义变化。
_TOOL_CACHE: Dict[tuple, "GraphMemoryTool"] = {}
_CACHE_LOCK = asyncio.Lock()


class GraphMemoryTool:
    """Persistent memory backed by Graphiti temporal knowledge graphs."""

    def __init__(self, user_id: str, graph_id: str):
        self.user_id = user_id
        self.graph_id = graph_id
        self.group_id = f"{user_id}_{graph_id}"
        # Graphiti uses group_id as the database name in FalkorDB.
        # Keep memory_db_name in sync so reads/writes target the same graph.
        self.memory_db_name = self.group_id
        self._graphiti: Optional[Graphiti] = None
        self._embedding = get_embedding_backend()
        self._memory_enabled = _GRAPHITI_AVAILABLE

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    # ---- 旧实现（已废弃，保留备查）----
    # 每次请求都重新初始化：重复执行 build_indices_and_constraints /
    # CREATE VECTOR INDEX / MERGE 实体节点等幂等操作，浪费多个远程往返。
    # @classmethod
    # async def create(cls, user_id: str, graph_id: str) -> "GraphMemoryTool":
    #     """Async factory: build Graphiti client and ensure indices / entities."""
    #     self = cls(user_id, graph_id)
    #     if not self._memory_enabled:
    #         return self
    #
    #     try:
    #         self._graphiti = _create_graphiti_client(self.memory_db_name)
    #         if self._graphiti is None:
    #             self._memory_enabled = False
    #             return self
    #
    #         # P0: Build graphiti indices and constraints
    #         await self._graphiti.build_indices_and_constraints(delete_existing=False)
    #     except Exception as e:
    #         logger.error("Graphiti initialization failed: %s", e, exc_info=True)
    #         self._memory_enabled = False
    #         return self
    #
    #     await self._ensure_vector_index()
    #     await self._ensure_entity_nodes()
    #     if MEMORY_TTL_SECONDS is not None:
    #         await self._refresh_ttl()
    #     return self

    @classmethod
    async def create(cls, user_id: str, graph_id: str) -> "GraphMemoryTool":
        """Return a cached tool per (user_id, graph_id), initializing on first use.

        缓存命中时零远程往返，直接复用已就绪的 Graphiti 客户端；
        首次（或进程重启后）调用 _init_once 完成完整初始化。
        """
        key = (user_id, graph_id)
        async with _CACHE_LOCK:
            cached = _TOOL_CACHE.get(key)
            if cached is not None:
                return cached
            tool = await cls._init_once(user_id, graph_id)
            _TOOL_CACHE[key] = tool
            return tool

    @classmethod
    async def _init_once(cls, user_id: str, graph_id: str) -> "GraphMemoryTool":
        """完整初始化（原 create 的逻辑）：建 Graphiti 客户端并确保索引/实体节点。

        每个 (user_id, graph_id) 组合在整个进程生命周期内只执行一次。
        """
        self = cls(user_id, graph_id)
        if not self._memory_enabled:
            return self

        try:
            self._graphiti = _create_graphiti_client(self.memory_db_name)
            if self._graphiti is None:
                self._memory_enabled = False
                return self

            # P0: Build graphiti indices and constraints
            await self._graphiti.build_indices_and_constraints(delete_existing=False)
        except Exception as e:
            logger.error("Graphiti initialization failed: %s", e, exc_info=True)
            self._memory_enabled = False
            return self

        await self._ensure_vector_index()
        await self._ensure_entity_nodes()
        if MEMORY_TTL_SECONDS is not None:
            await self._refresh_ttl()
        return self

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute(self, cypher: str, params: dict | None = None) -> Any:
        """Run Cypher via Graphiti's underlying FalkorDriver."""
        if self._graphiti is None:
            return ([], [], None)
        try:
            return await self._graphiti.driver.execute_query(cypher, **(params or {}))
        except Exception as e:
            logger.error("Memory graph query failed: %s", e, exc_info=True)
            raise

    async def _refresh_ttl(self) -> None:
        try:
            falkor = get_falkordb()
            await falkor.db.execute_command(
                "EXPIRE", self.memory_db_name, MEMORY_TTL_SECONDS
            )
        except Exception as e:
            logger.warning("Failed to refresh TTL for %s: %s", self.memory_db_name, e)

    async def _ensure_vector_index(self) -> None:
        """Create vector index on Query.embeddings if it does not exist."""
        dim = self._embedding.vector_size
        try:
            await self._graphiti.driver.execute_query(
                """
                CREATE VECTOR INDEX FOR (q:Query) ON (q.embeddings)
                OPTIONS {dimension: $dim, similarityFunction: 'cosine'}
                """,
                dim=dim,
            )
            logger.info("Created vector index for Query nodes (dim=%d)", dim)
        except Exception as e:
            err = str(e).lower()
            if "already indexed" in err or "already exists" in err or "index already exists" in err:
                logger.debug("Vector index already exists, skipping creation.")
            else:
                logger.warning("Vector index creation failed: %s", e)

    async def _ensure_entity_nodes(self) -> None:
        """Create user and database Entity nodes with proper group_id."""
        user_name = self.user_id
        db_name = f"Database {self.graph_id}"

        await self._ensure_single_entity(
            name=user_name,
            summary=f"User {user_name} is using the NL2SQL system.",
        )
        await self._ensure_single_entity(
            name=db_name,
            summary=f"Database {self.graph_id} available for querying by user {user_name}.",
        )

        # Relationship
        await self._execute(
            """
            MATCH (u:Entity {name: $user_name, group_id: $group_id})
            MATCH (d:Entity {name: $db_name, group_id: $group_id})
            MERGE (u)-[r:HAS_DATABASE]->(d)
            """,
            {
                "user_name": user_name,
                "db_name": db_name,
                "group_id": self.group_id,
            },
        )

    async def _ensure_single_entity(self, name: str, summary: str) -> None:
        embedding = self._embedding.embed([name])[0] if name else []
        node_data = {
            "uuid": str(uuid.uuid4()),
            "name": name,
            "group_id": self.group_id,
            "created_at": datetime.now().isoformat(),
            "summary": summary,
            "name_embedding": embedding,
            "labels": ["Entity"],
        }
        await self._execute(
            """
            MERGE (n:Entity {name: $node.name, group_id: $node.group_id})
            ON CREATE SET
                n.uuid = $node.uuid,
                n.created_at = $node.created_at,
                n.summary = $node.summary,
                n.name_embedding = vecf32($node.name_embedding),
                n.labels = $node.labels
            """,
            {"node": node_data},
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_memories(self, query: str, limit: int = 5) -> str:
        """Search user summary, similar queries, and database facts concurrently."""
        if not self._memory_enabled or self._graphiti is None:
            return ""

        tasks = [
            self._search_user_summary(),
            self._search_similar_queries(query, limit),
            self._search_database_facts(query, limit),
        ]
        user_summary, similar_queries, db_facts = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        if isinstance(user_summary, Exception):
            logger.error("User summary search failed: %s", user_summary, exc_info=True)
            user_summary = ""
        if isinstance(similar_queries, Exception):
            logger.error("Similar query search failed: %s", similar_queries, exc_info=True)
            similar_queries = []
        if isinstance(db_facts, Exception):
            logger.error("Database facts search failed: %s", db_facts, exc_info=True)
            db_facts = ""

        parts: List[str] = []
        if user_summary:
            parts.append(f"用户偏好与画像:\n{user_summary}")
        if db_facts:
            parts.append(f"数据库 {self.graph_id} 历史事实:\n{db_facts}")
        if similar_queries:
            parts.append(self._format_similar_queries(similar_queries))

        return "\n\n".join(parts)

    async def save_query_memory(
        self,
        question: str,
        sql: str,
        success: bool,
        error: Optional[str] = None,
    ) -> bool:
        """Save a query execution record via Graphiti + custom Query node."""
        if not self._memory_enabled or self._graphiti is None:
            return False

        try:
            # Check if this exact query already exists as Query node
            db_name = f"Database {self.graph_id}"
            records, _, _ = await self._execute(
                """
                MATCH (d:Entity {name: $db_name, group_id: $group_id})
                      -[:HAS_QUERY|SUCCESS|FAILED]->(q:Query)
                WHERE q.question = $question AND q.sql = $sql
                RETURN q.uuid AS existing_uuid
                LIMIT 1
                """,
                {
                    "db_name": db_name,
                    "group_id": self.group_id,
                    "question": question,
                    "sql": sql,
                },
            )
            if records:
                logger.debug("Duplicate query memory skipped.")
                return True

            # 1) Feed the interaction into Graphiti with dedup uuid
            episode_body = (
                f"User asked: {question}\n"
                f"Generated SQL: {sql}\n"
                f"Status: {'Success' if success else 'Failed'}\n"
            )
            if error:
                episode_body += f"Error: {error}\n"

            await self._graphiti.add_episode(
                name=f"Query_{self.group_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                episode_body=episode_body,
                source=EpisodeType.message,
                reference_time=datetime.now(),
                source_description=f"NL2SQL interaction for database {self.graph_id}",
                group_id=self.group_id,
            )

            # 2) Also keep a custom Query node for fast vector-based retrieval
            embedding = self._embedding.embed([question])[0] if question else []
            query_uuid = str(uuid.uuid4())
            rel_type = "SUCCESS" if success else "FAILED"

            await self._execute(
                f"""
                MATCH (d:Entity {{name: $db_name, group_id: $group_id}})
                CREATE (q:Query {{
                    uuid: $uuid,
                    question: $question,
                    sql: $sql,
                    success: $success,
                    error: $error,
                    timestamp: timestamp(),
                    created_at: $created_at,
                    embeddings: vecf32($embedding),
                    group_id: $group_id
                }})
                CREATE (d)-[:{rel_type}]->(q)
                """,
                {
                    "db_name": db_name,
                    "group_id": self.group_id,
                    "uuid": query_uuid,
                    "question": question,
                    "sql": sql,
                    "success": success,
                    "error": error or "",
                    "created_at": datetime.now().isoformat(),
                    "embedding": embedding,
                },
            )
            return True
        except Exception as e:
            logger.error("Failed to save query memory: %s", e, exc_info=True)
            return False

    async def update_user_summary(
        self,
        question: str,
        sql: str,
        success: bool,
        error: Optional[str] = None,
        answer: Optional[str] = None,
    ) -> bool:
        """Feed user interaction into Graphiti as an episode for automatic summary extraction."""
        if not self._memory_enabled or self._graphiti is None:
            return False

        try:
            episode_body = f"User interaction:\nQuestion: {question}\nSQL: {sql}\n"
            if error:
                episode_body += f"Error: {error}\n"
            if answer:
                episode_body += f"Answer: {answer}\n"
            episode_body += f"Status: {'Success' if success else 'Failed'}\n"

            await self._graphiti.add_episode(
                name=f"user_summary_{self.group_id}",
                episode_body=episode_body,
                source=EpisodeType.message,
                reference_time=datetime.now(),
                source_description="User preference update",
                group_id=self.group_id,
            )
            return True
        except Exception as e:
            logger.error("Failed to update user summary: %s", e, exc_info=True)
            return False

    async def add_database_fact(self, fact: str) -> bool:
        """Add a database fact as a Graphiti episode for temporal knowledge extraction."""
        if not self._memory_enabled or self._graphiti is None:
            return False

        try:
            episode_name = (
                f"fact_{self.graph_id}_"
                f"{hashlib.sha256(fact.encode()).hexdigest()[:16]}"
            )

            await self._graphiti.add_episode(
                name=episode_name,
                episode_body=fact,
                source=EpisodeType.json,
                reference_time=datetime.now(),
                source_description=f"Database fact for {self.graph_id}",
                group_id=self.group_id,
            )
            return True
        except Exception as e:
            logger.error("Failed to add database fact: %s", e, exc_info=True)
            return False

    async def clean_memory(self, size: int = 10000) -> int:
        """Retain the most recent `size` QueryMemory nodes; delete older ones and their graphiti episodes."""
        if not self._memory_enabled or self._graphiti is None:
            return 0

        deleted = 0
        try:
            # 1) Clean custom Query nodes
            records, _, _ = await self._execute(
                """
                MATCH (q:Query {group_id: $group_id})
                WITH q ORDER BY coalesce(q.timestamp, 0) DESC
                SKIP $keep
                DETACH DELETE q
                """,
                {"keep": int(size), "group_id": self.group_id},
            )
            deleted += len(records) if records else 0

            # 2) Clean old graphiti episodes and associated edges
            cutoff = datetime.now() - timedelta(days=30)
            # Delete relationships first (FalkorDB compatibility)
            await self._execute(
                """
                MATCH (e:Episodic {group_id: $group_id})
                WHERE e.valid_at < $cutoff
                MATCH (e)-[r]-()
                DELETE r
                """,
                {"group_id": self.group_id, "cutoff": cutoff.isoformat()},
            )
            # Delete episodes
            await self._execute(
                """
                MATCH (e:Episodic {group_id: $group_id})
                WHERE e.valid_at < $cutoff
                DELETE e
                """,
                {"group_id": self.group_id, "cutoff": cutoff.isoformat()},
            )
            logger.info(
                "Memory cleanup executed for %s (group=%s)",
                self.memory_db_name,
                self.group_id,
            )
        except Exception as e:
            logger.error("Memory cleanup failed: %s", e, exc_info=True)
        return deleted

    # ------------------------------------------------------------------
    # Search sub-routines
    # ------------------------------------------------------------------

    async def _search_user_summary(self) -> str:
        records, _, _ = await self._execute(
            """
            MATCH (u:Entity {name: $name, group_id: $group_id})
            RETURN u.summary AS summary
            """,
            {"name": self.user_id, "group_id": self.group_id},
        )
        if records:
            return str(records[0].get("summary", "") or "")
        return ""

    async def _search_similar_queries(self, query: str, limit: int) -> List[Dict[str, Any]]:
        if not query:
            return []
        embedding = self._embedding.embed([query])[0]
        records, _, _ = await self._execute(
            """
            CALL db.idx.vector.queryNodes('Query', 'embeddings', $k, vecf32($embedding))
            YIELD node, score
            MATCH (d:Entity {name: $db_name, group_id: $group_id})
                  -[:HAS_QUERY|SUCCESS|FAILED]->(node)
            RETURN node {
                .question,
                .sql,
                .success,
                .error
            } AS query_data, score
            ORDER BY score ASC
            LIMIT $limit
            """,
            {
                "k": limit * 2,
                "embedding": embedding,
                "db_name": f"Database {self.graph_id}",
                "group_id": self.group_id,
                "limit": limit,
            },
        )
        return [row.get("query_data", {}) for row in records] if records else []

    async def _search_database_facts(self, query: str, limit: int = 5) -> str:
        """Use Graphiti advanced search centred on the database Entity."""
        if not self._memory_enabled or self._graphiti is None:
            return ""

        try:
            db_name = f"Database {self.graph_id}"

            # Resolve database entity UUID
            records, _, _ = await self._execute(
                """
                MATCH (e:Entity {name: $name, group_id: $group_id})
                RETURN e.uuid AS uuid
                """,
                {"name": db_name, "group_id": self.group_id},
            )
            center_uuid = ""
            if records:
                center_uuid = records[0].get("uuid", "") or ""

            if not center_uuid:
                # Fallback: return static facts property
                records, _, _ = await self._execute(
                    """
                    MATCH (d:Entity {name: $name, group_id: $group_id})
                    RETURN d.facts AS facts
                    """,
                    {"name": db_name, "group_id": self.group_id},
                )
                if records:
                    return str(records[0].get("facts", "") or "")
                return ""

            # Advanced graphiti search with hybrid retrieval
            search_config = COMBINED_HYBRID_SEARCH_CROSS_ENCODER.model_copy(
                update={"limit": limit}
            )
            results: SearchResults = await self._graphiti.search_(
                query=query,
                config=search_config,
                group_ids=[self.group_id],
                center_node_uuid=center_uuid,
            )

            facts_text: List[str] = []
            episodes_text: List[str] = []

            for edge in results.edges:
                # Skip expired edges
                expired_at = getattr(edge, "expired_at", None)
                if expired_at:
                    continue

                # Only keep results touching the database node
                src = getattr(edge, "source_node_uuid", "")
                tgt = getattr(edge, "target_node_uuid", "")
                if src != center_uuid and tgt != center_uuid:
                    continue

                # Episodes (source provenance)
                episodes = getattr(edge, "episodes", []) or []
                if len(episodes_text) < 3 and episodes:
                    for ep_uuid in episodes:
                        ep_records, _, _ = await self._execute(
                            """
                            MATCH (e:Episodic {uuid: $uuid, group_id: $group_id})
                            RETURN e.content AS content
                            """,
                            {"uuid": ep_uuid, "group_id": self.group_id},
                        )
                        if ep_records:
                            content = ep_records[0].get("content", "")
                            if content:
                                episodes_text.append(str(content))

                # Fact with temporal validity
                fact = getattr(edge, "fact", "")
                if fact:
                    time_info: List[str] = []
                    valid_at = getattr(edge, "valid_at", None)
                    invalid_at = getattr(edge, "invalid_at", None)
                    if valid_at:
                        time_info.append(f"Valid from: {valid_at}")
                    if invalid_at:
                        time_info.append(f"Valid until: {invalid_at}")
                    entry = str(fact)
                    if time_info:
                        entry += f" ({', '.join(time_info)})"
                    facts_text.append(entry)

            parts: List[str] = []
            if episodes_text:
                parts.append("Previous sessions:\n" + "\n".join(episodes_text))
            if facts_text:
                parts.append("Facts:\n" + "\n".join(facts_text))
            return "\n\n".join(parts)

        except Exception as e:
            logger.error("Database facts search failed: %s", e, exc_info=True)
            # Fallback to static facts
            try:
                records, _, _ = await self._execute(
                    """
                    MATCH (d:Entity {name: $name, group_id: $group_id})
                    RETURN d.facts AS facts
                    """,
                    {"name": f"Database {self.graph_id}", "group_id": self.group_id},
                )
                if records:
                    return str(records[0].get("facts", "") or "")
            except Exception:
                pass
            return ""

    @staticmethod
    def _format_similar_queries(queries: List[Dict[str, Any]]) -> str:
        successful = [q for q in queries if q.get("success")]
        failed = [q for q in queries if not q.get("success")]
        lines: List[str] = ["相似查询历史:"]
        if successful:
            lines.append("\n成功查询 (可借鉴的模式):")
            for i, q in enumerate(successful, 1):
                lines.append(f"{i}. 问题: {q.get('question', '')}")
                lines.append(f"   SQL: {q.get('sql', '')}")
        if failed:
            lines.append("\n失败查询 (应避免的模式):")
            for i, q in enumerate(failed, 1):
                lines.append(f"{i}. 问题: {q.get('question', '')}")
                lines.append(f"   SQL: {q.get('sql', '')}")
                err = q.get("error")
                if err:
                    lines.append(f"   错误: {err}")
                lines.append("   请避免此写法。")
        return "\n".join(lines)
