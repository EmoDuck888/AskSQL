"""
智能对话Agent系统：工具装配 + 中间件挂载 + agent 构建。

中间件实现见 app.agents.middleware（经 build_middleware 统一组装），
后端配置见 app.agents.backends。
"""
import logging
from dataclasses import dataclass

from deepagents import create_deep_agent as create_agent, create_deep_agent

from app.core.llms import deepseek_model
# 方式1：通过 MCP 协议访问所有远程工具（需要启动 MCP server）
from app.tools.mcp import tools as mcp_tools
from app.tools.mcp import get_db_tools as mcp_get_db_tools
# 方式2：直接调用本地数据库工具（无需启动 MCP SQL server）
from app.db.tools import tools as db_tools
from app.agents.schema_tools import find_relevant_schema_tool, get_graph_list_tool
from app.agents.backends import composite_backend
from app.agents.middleware import build_middleware
from app.agents.middleware.prompt import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# 切换开关：True=使用 MCP 数据库访问工具，False=仅使用本地数据库工具
USE_MCP = False

# 默认不使用 MCP；如需使用mcp数据库工具，将上方 USE_MCP 改为 True
db_tools = mcp_get_db_tools() if USE_MCP else db_tools

# 检索工具：FalkorDB 向量搜索 + 图遍历
retrieval_tools = [find_relevant_schema_tool, get_graph_list_tool]

tools = db_tools + mcp_tools + retrieval_tools


@dataclass
class Context:
    connection_id: int | None = None
    user_rules: str | None = None
    graph_id: str | None = None
    user_id: str = "default"
    use_memory: bool = False


agent = create_deep_agent(
    model=deepseek_model,
    tools=tools,
    middleware=build_middleware(composite_backend),
    context_schema=Context,
    # skills=["/skills/"],
    backend=composite_backend,
    system_prompt=SYSTEM_PROMPT,
)
