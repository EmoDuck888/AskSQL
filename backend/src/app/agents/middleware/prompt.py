"""
动态系统提示词中间件：根据用户选择的连接注入数据库信息、方言规则、
语义模型配置和历史记忆。
"""
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from sqlalchemy import select

from app.api.graph import FalkorDBClient
from app.db.session import AsyncSessionLocal
from app.memory import GraphMemoryTool
from app.models.database import DBConnection
# 纯函数已抽到轻量模块，便于零依赖测试（原名 _get_dialect_rules 保持不变）
from app.utils.dialect import get_dialect_rules as _get_dialect_rules

logger = logging.getLogger(__name__)

# 从文件加载系统提示词，与 memory 参考手册分离以优化上下文窗口
_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[1] / "SYSTEM_PROMPT.md"
SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


async def _get_semantic_model_text(graph_id: str) -> str:
    """Query FalkorDB for semantic model configs and format as readable text."""
    try:
        graph = FalkorDBClient.select_graph(graph_id)
        # 预定义语义属性，避免访问未定义属性报错（详见 falkordb_client.ensure_semantic_attributes）
        from app.api.graph.falkordb_client import ensure_semantic_attributes
        await ensure_semantic_attributes(graph, graph_id)
        result = await graph.query(
            """
            MATCH (t:Table)
            OPTIONAL MATCH (c:Column)-[:BELONGS_TO]->(t)
            WHERE t.business_name IS NOT NULL
               OR t.synonyms IS NOT NULL
               OR t.description IS NOT NULL
               OR c.business_name IS NOT NULL
               OR c.synonyms IS NOT NULL
               OR c.description IS NOT NULL
               OR c.enum_descriptions IS NOT NULL
            RETURN
                t.name AS table_name,
                t.business_name AS table_biz,
                t.synonyms AS table_syn,
                t.description AS table_desc,
                collect(DISTINCT {
                    name: c.name,
                    type: c.type,
                    business_name: c.business_name,
                    synonyms: c.synonyms,
                    description: c.description,
                    enum_descriptions: c.enum_descriptions,
                    key_type: c.key_type
                }) AS columns
            """
        )

        lines: list[str] = []
        for row in result.result_set:
            table_name = row[0] or ""
            table_biz = row[1] or ""
            table_syn = row[2] or ""
            table_desc = row[3] or ""
            columns = row[4] or []

            # Skip tables with no semantic configs at all
            has_semantic = bool(table_biz or table_syn or table_desc)
            semantic_cols = [
                c for c in columns
                if c.get("business_name") or c.get("synonyms") or c.get("description") or c.get("enum_descriptions")
            ]
            if not has_semantic and not semantic_cols:
                continue

            lines.append(f"\n[Table] {table_name}")
            if table_biz:
                lines.append(f"  业务名称: {table_biz}")
            if table_syn:
                lines.append(f"  同义词: {table_syn}")
            if table_desc:
                lines.append(f"  描述: {table_desc}")

            for col in semantic_cols:
                col_name = col.get("name", "")
                col_biz = col.get("business_name", "")
                col_syn = col.get("synonyms", "")
                col_desc = col.get("description", "")
                col_enum = col.get("enum_descriptions", "")
                col_type = col.get("type", "")
                col_key = col.get("key_type", "")

                parts: list[str] = []
                if col_biz:
                    parts.append(f"业务名称={col_biz}")
                if col_syn:
                    parts.append(f"同义词={col_syn}")
                if col_desc:
                    parts.append(f"描述={col_desc}")
                if col_enum:
                    parts.append(f"枚举值={col_enum}")
                if col_type:
                    parts.append(f"类型={col_type}")
                if col_key == "PRI":
                    parts.append("主键")

                if parts:
                    lines.append(f"  [Column] {col_name}: {', '.join(parts)}")

        return "\n".join(lines) if lines else ""
    except Exception:
        logger.warning("Failed to load semantic model configs for graph %s", graph_id, exc_info=True)
        return ""


@dynamic_prompt
async def prompt_with_context(request: ModelRequest) -> str:
    """动态生成系统提示词，根据用户选择的连接注入数据库信息和用户规则。"""
    base_prompt = SYSTEM_PROMPT
    ctx = request.runtime.context

    connection_id = getattr(ctx, "connection_id", None)
    user_rules = getattr(ctx, "user_rules", None)
    graph_id = getattr(ctx, "graph_id", None)
    user_id = getattr(ctx, "user_id", "default")
    use_memory = getattr(ctx, "use_memory", False)

    dynamic_info: list[str] = []

    if connection_id:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(DBConnection).where(DBConnection.id == connection_id)
                )
                conn = result.scalar_one_or_none()
                if conn:
                    dynamic_info.append(
                        f"当前数据库类型: {conn.db_type.upper()}"
                    )
                    if conn.falkordb_graph_id:
                        dynamic_info.append(
                            f"FalkorDB Graph ID: {conn.falkordb_graph_id}"
                        )
                    if conn.database_name:
                        dynamic_info.append(f"数据库名称: {conn.database_name}")
                    dynamic_info.append(f"连接名称: {conn.name}")
                    # 替换方言规则占位符
                    base_prompt = base_prompt.replace(
                        "{DB_TYPE}", conn.db_type.upper()
                    )
                    base_prompt = base_prompt.replace(
                        "{DB_DIALECT_RULES}", _get_dialect_rules(conn.db_type)
                    )
        except Exception:
            pass

    if user_rules:
        dynamic_info.append(
            f"\n用户自定义规则 (user_rules_spec):\n{user_rules}"
        )

    # ---- Semantic Model injection ----
    if graph_id:
        try:
            semantic_text = await _get_semantic_model_text(graph_id)
            if semantic_text:
                base_prompt += (
                    "\n\n<semantic_model>\n"
                    "以下语义模型配置帮助你将用户的自然语言问题映射到正确的数据库表和字段。\n"
                    "优先使用业务名称和同义词来理解用户意图，参考枚举值说明来正确过滤数据。\n"
                    f"{semantic_text}\n"
                    "</semantic_model>"
                )
        except Exception as e:
            logger.warning("Semantic model injection failed: %s", e)

    if dynamic_info:
        replacement = "\n".join(dynamic_info)
        # 尝试替换固定的 SQLite 描述
        if "当前数据库是 SQLITE，文件名是：chinook.db" in base_prompt:
            base_prompt = base_prompt.replace(
                "当前数据库是 SQLITE，文件名是：chinook.db",
                replacement,
            )
        else:
            # 兜底：在关键提醒部分追加
            base_prompt = base_prompt.replace(
                "> 当前操作系统是 Windows 11，请确保所有的命令都是在 Windows 11 下进行。",
                f"> 当前操作系统是 Windows 11，请确保所有的命令都是在 Windows 11 下进行。\n> \n> {replacement.replace(chr(10), chr(10)+'> ')}",
            )

    # ---- Memory injection ----
    if use_memory and graph_id:
        try:
            memory_tool = await GraphMemoryTool.create(user_id, graph_id)
            messages = request.state.get("messages", [])
            last_human_msg = next(
                (m for m in reversed(messages) if isinstance(m, HumanMessage)),
                None,
            )
            if last_human_msg and last_human_msg.content:
                memory_context = await memory_tool.search_memories(
                    str(last_human_msg.content)
                )
                if memory_context:
                    base_prompt += (
                        "\n\n<memory_context>\n"
                        f"{memory_context}\n"
                        "</memory_context>\n"
                        "使用此上下文来：\n"
                        "1. 理解用户偏好和工作风格\n"
                        "2. 复用之前对该数据库的学习\n"
                        "3. 借鉴 SUCCESSFUL QUERIES 的模式\n"
                        "4. 避免 FAILED QUERIES 的错误"
                    )
        except Exception as e:
            logger.warning("Memory injection failed: %s", e)

    return base_prompt
