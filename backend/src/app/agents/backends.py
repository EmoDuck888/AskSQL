"""
deepagents 后端配置：shell + 虚拟文件系统（skills/workspace）的
组合后端定义。root 相对本文件定位：仓库搬到任何磁盘/目录/机器都自动跟随。

注意：记忆系统（GraphMemoryTool）存储在 FalkorDB，不经由本文件系统的
/memories/ 路由；该路由已随 AGENTS.md 一并移除。
"""
from pathlib import Path

from deepagents.backends import FilesystemBackend, LocalShellBackend, CompositeBackend

# 定位到 backend/src/app（agents 的上一级）
_APP_DIR = Path(__file__).resolve().parent.parent  # backend/src/app

skills_root = str(_APP_DIR / "skills")
workspace_root = str(_APP_DIR / "workspace")

shell_backend = LocalShellBackend(
    root_dir=workspace_root,
    inherit_env=True,
    virtual_mode=True,
    env={"PATH": r"D:\nodejs;C:\Users\hp\AppData\Roaming\npm;C:\Windows\System32;C:\Windows;D:\code\AskSQL\.venv\Scripts;D:\Program Files\python313\Scripts"}
)

skills_backend = FilesystemBackend(root_dir=skills_root, virtual_mode=True)
workspace_backend = FilesystemBackend(root_dir=workspace_root, virtual_mode=True)

composite_backend = CompositeBackend(
    default=shell_backend,
    routes={
        "/skills/": skills_backend,
        "/": workspace_backend,
    },
)
