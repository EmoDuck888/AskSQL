"""
记忆持久化中间件：拦截 run_sql 工具调用，将查询记忆异步写入 FalkorDB。
"""
import asyncio
import logging

from langchain_core.messages import HumanMessage
from langchain.agents.middleware import wrap_tool_call

from app.memory import GraphMemoryTool

logger = logging.getLogger(__name__)


@wrap_tool_call
async def save_sql_memory(request, handler):
    """Intercept run_sql tool calls to persist query memory to FalkorDB."""
    result = await handler(request)

    ctx = request.runtime.context
    use_memory = getattr(ctx, "use_memory", False)
    graph_id = getattr(ctx, "graph_id", None)
    user_id = getattr(ctx, "user_id", "default")

    if not use_memory or not graph_id:
        return result

    tool_name = request.tool_call.get("name") if hasattr(request, "tool_call") else None
    if tool_name != "run_sql":
        return result

    try:
        messages = request.state.get("messages", [])
        last_human_msg = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        question = (
            str(last_human_msg.content)
            if last_human_msg and hasattr(last_human_msg, "content")
            else ""
        )

        sql = ""
        if hasattr(request, "tool_call") and isinstance(request.tool_call, dict):
            sql = request.tool_call.get("args", {}).get("sql", "")

        success = True
        error_msg = None
        if hasattr(result, "status") and result.status == "error":
            success = False
            error_msg = (
                str(result.content)
                if hasattr(result, "content")
                else "Tool execution failed"
            )

        memory_tool = await GraphMemoryTool.create(user_id, graph_id)
        asyncio.create_task(
            memory_tool.save_query_memory(
                question=question, sql=sql, success=success, error=error_msg
            )
        )
        asyncio.create_task(
            memory_tool.update_user_summary(
                question=question,
                sql=sql,
                success=success,
                error=error_msg,
                answer="",
            )
        )
        asyncio.create_task(memory_tool.clean_memory())
    except Exception as e:
        logger.warning("Background memory save failed: %s", e)

    return result
