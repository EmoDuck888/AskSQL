from langchain_mcp_adapters.client import MultiServerMCPClient
# from app.utils.path_resolver import wrap_tool
def get_db_tools():
    client = MultiServerMCPClient(
        {
            "mcp-db": {
                "transport": "http",  # HTTP-based remote server
                # Ensure you start your weather server on port 8000
                "url": "http://localhost:8000/mcp",
            },
        }
    )
    _tools = client.get_tools()
    return _tools

def get_mcp_tools():
    import asyncio
    client = MultiServerMCPClient(
            {
                "mcp-server-chart": {
                    "transport": "stdio",
                    "command": "npx",
                    "args": ["-y", "@antv/mcp-server-chart"]
                },
            },

        )
    _tools = asyncio.run(client.get_tools())
    return _tools
    # return [wrap_tool(t) for t in _tools]
tools = get_mcp_tools()
