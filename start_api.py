#!/usr/bin/env python3
"""
DataAgent NL2SQL — FastAPI 服务启动脚本。

用法:
    python start_api.py          # 默认启动在 8065 端口
    python start_api.py --port 8080

环境变量:
    DATA_AGENT_PORT   - 服务端口（默认 8065，复刻 DataAgent Java 后端端口）
    DATA_AGENT_HOST   - 绑定地址（默认 0.0.0.0）
    LLM_API_KEY       - LLM API 密钥
"""

import os
import sys
from pathlib import Path

# 从项目根目录 .env 加载环境变量（唯一配置源）
root_env = Path(__file__).parent / ".env"
if root_env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(root_env, override=True)
    except ImportError:
        pass

# 确保 backend/src 在路径中
src_path = Path(__file__).parent / "backend" / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import uvicorn


def main():
    host = os.getenv("DATA_AGENT_HOST", "0.0.0.0")
    port = int(os.getenv("DATA_AGENT_PORT", "8065"))

    # 解析命令行参数
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]

    print("=" * 60)
    print("  DataAgent NL2SQL - Enterprise NL2SQL Service")
    print("=" * 60)
    print(f"  API Address:   http://{host}:{port}")
    print(f"  API Docs:      http://{host}:{port}/docs")
    print(f"  Health Check:  http://{host}:{port}/health")
    print("=" * 60)
    print()

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        access_log=True,
    )


if __name__ == "__main__":
    main()
