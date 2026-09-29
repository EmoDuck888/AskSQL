"""
Agent 中间件包：统一组装并导出中间件列表。

中间件顺序敏感（如 dynamic_prompt 必须最先执行），
请勿在调用方自行拼装，一律通过 build_middleware() 获取。
"""
from deepagents.middleware import SkillsMiddleware

from app.agents.middleware.hitl import DestructiveSQLReviewMiddleware
from app.agents.middleware.memory import save_sql_memory
from app.agents.middleware.prompt import prompt_with_context


def build_middleware(backend) -> list:
    """按固定顺序构建中间件列表。

    Args:
        backend: deepagents CompositeBackend 实例，供 SkillsMiddleware 使用。

    Returns:
        可直接传给 create_agent(middleware=[...]) 的中间件列表。
    """
    return [
        prompt_with_context,
        DestructiveSQLReviewMiddleware(),
        save_sql_memory,
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/nl2sql/"]
        ),
    ]
