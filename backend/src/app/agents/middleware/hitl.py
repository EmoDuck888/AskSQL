"""
Human-in-the-Loop 中间件：针对 run_sql 中的销毁类 SQL（DELETE/DROP/TRUNCATE）
触发人工审核，其余调用零打扰放行。
"""
import logging

from langchain_core.messages import AIMessage
from langchain.agents.middleware.human_in_the_loop import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
)

logger = logging.getLogger(__name__)

# 需要人工审核的销毁类操作：不可逆，一旦执行数据/对象无法通过 UPDATE 补救。
# 注意：与 query_engine._DESTRUCTIVE_OPS（全部写操作）口径不同，请勿混用。
_REVIEW_REQUIRED_OPS = frozenset({"DELETE", "DROP", "TRUNCATE"})


def _destructive_op(sql: str) -> str | None:
    """返回 SQL 命中的销毁类操作名（DELETE/DROP/TRUNCATE），未命中返回 None。"""
    upper = sql.strip().upper()
    for op in _REVIEW_REQUIRED_OPS:
        if upper.startswith(op):
            return op
    return None


def _describe_sql_review(tool_call, state, runtime) -> str:
    """HITL 审批卡片描述：提示销毁操作风险并展示完整 SQL。"""
    sql = ""
    if isinstance(tool_call, dict):
        args = tool_call.get("args") or {}
        if isinstance(args, dict):
            sql = args.get("sql", "")
    op = _destructive_op(sql) or "?"
    return (
        f"检测到 **{op}** 销毁操作，执行将永久删除数据库中的数据/对象，请人工审核：\n\n"
        f"```sql\n{sql}\n```"
    )


class DestructiveSQLReviewMiddleware(HumanInTheLoopMiddleware):
    """针对 run_sql 中的销毁类 SQL（DELETE/DROP/TRUNCATE）触发人工审核。

    官方 HumanInTheLoopMiddleware 只能按工具名拦截（配置即拦截该工具的全部调用，
    包括 SELECT 等只读查询），这里重写 after_model 的前置判断：
    仅当最后一条 AI 消息里存在销毁类 run_sql 调用时才交给官方中断/审批流程，
    否则直接放行，日常使用零打扰。
    """

    def __init__(self) -> None:
        super().__init__(
            interrupt_on={
                "run_sql": InterruptOnConfig(
                    # 只允许批准/拒绝，不允许编辑——写操作不允许绕过审核篡改后执行
                    allowed_decisions=["approve", "reject"],
                    description=_describe_sql_review,
                )
            }
        )

    @staticmethod
    def _has_destructive_run_sql(state) -> bool:
        messages = (
            state.get("messages")
            if isinstance(state, dict)
            else getattr(state, "messages", None)
        )
        if not messages:
            return False
        last_ai_msg = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)), None
        )
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return False
        for tool_call in last_ai_msg.tool_calls:
            if not isinstance(tool_call, dict) or tool_call.get("name") != "run_sql":
                continue
            args = tool_call.get("args") or {}
            sql = args.get("sql", "") if isinstance(args, dict) else ""
            op = _destructive_op(sql)
            logger.info(
                "after_model guard: run_sql op=%s sql=%.80s", op or "-", sql
            )
            if op:
                return True
        return False

    def after_model(self, state, runtime):
        # 无销毁类 SQL → 不进入官方中断流程，所有工具调用自动放行
        if not self._has_destructive_run_sql(state):
            return None
        logger.info("Destructive SQL detected, triggering human review")
        return super().after_model(state, runtime)
