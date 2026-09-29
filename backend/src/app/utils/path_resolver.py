# """Virtual path → real filesystem path resolver for deepagents backends.
#
# When deepagents operates with CompositeBackend + virtual_mode, all file paths
# returned by backend operations are virtual paths starting with ``/``.
# External tools (especially MCP tools running in separate processes) cannot
# resolve these virtual paths and require real filesystem paths.
#
# This module provides utilities to transparently convert virtual paths to real
# paths at the tool-call boundary.
# """
#
# from __future__ import annotations
#
# from functools import wraps
# from pathlib import Path
# from typing import Any
#
# # Must match agent.py workspace_dir exactly
# WORKSPACE_DIR = Path(
#     r"C:\Users\65132\Desktop\workspace\nl2sql\src\app"
# ).resolve()
#
# # Parameter names that commonly carry file-path values.
# # Only values associated with these keys (or nested dict keys) are converted.
# DEFAULT_PATH_PARAM_NAMES: set[str] = {
#     "file_path",
#     "path",
#     "filename",
#     "file",
#     "filepath",
#     "input_file",
#     "output_file",
#     "source",
#     "destination",
#     "src",
#     "dst",
#     "input",
#     "output",
#     "dir",
#     "directory",
#     "root",
#     "url",  # some tools accept a local file via url-like param
# }
#
#
# def resolve_virtual_path(vpath: str) -> str:
#     """Convert a deepagents virtual path to a real filesystem path.
#
#     Virtual paths start with ``/`` and are relative to ``WORKSPACE_DIR``.
#     Windows absolute paths and relative paths without leading ``/`` are
#     returned unchanged.
#
#     Examples
#     --------
#     >>> resolve_virtual_path("/report/test.pdf")
#     'C:\\...\\workspace\\report\\test.pdf'
#
#     >>> resolve_virtual_path("C:\\foo\\bar.pdf")
#     'C:\\foo\\bar.pdf'
#
#     >>> resolve_virtual_path("report/test.pdf")
#     'C:\\...\\workspace\\report\\test.pdf'
#     """
#     vpath = vpath.strip().replace("\\", "/")
#
#     # Windows absolute path → passthrough
#     if len(vpath) >= 2 and vpath[1] == ":":
#         return vpath
#
#     # Virtual path (starts with /) → resolve under workspace
#     if vpath.startswith("/"):
#         return str(WORKSPACE_DIR / vpath.lstrip("/"))
#
#     # Plain relative path → resolve under workspace
#     return str((WORKSPACE_DIR / vpath).resolve())
#
#
# def resolve_value(value: Any, param_name: str = "") -> Any:
#     """Recursively resolve virtual paths inside a value.
#
#     Only values whose associated parameter name (or nested dict key) is in
#     ``DEFAULT_PATH_PARAM_NAMES`` are converted.  This avoids accidentally
#     mutating non-path strings such as API endpoints (``/api/v1/users``).
#
#     A double-leading slash ``//`` can be used as an escape hatch to prevent
#     conversion: ``//api/v1`` stays as ``//api/v1``.
#     """
#     if isinstance(value, str):
#         # Escape hatch: // means "do not convert"
#         if value.startswith("//"):
#             return value
#
#         # Only convert if the parameter name looks like a path param
#         if param_name.lower() in DEFAULT_PATH_PARAM_NAMES:
#             if value.startswith("/") and not (len(value) >= 2 and value[1] == ":"):
#                 return resolve_virtual_path(value)
#         return value
#
#     if isinstance(value, list):
#         return [resolve_value(v, param_name) for v in value]
#
#     if isinstance(value, dict):
#         return {
#             k: resolve_value(v, param_name=k if k in DEFAULT_PATH_PARAM_NAMES else param_name)
#             for k, v in value.items()
#         }
#
#     return value
#
#
# def _resolve_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
#     """Resolve virtual paths in tool call arguments."""
#     # Handle the case where the first positional arg is a dict (common for
#     # langchain BaseTool._run(tool_input) style).
#     if args and len(args) == 1 and isinstance(args[0], dict):
#         resolved_input = {
#             k: resolve_value(v, param_name=k)
#             for k, v in args[0].items()
#         }
#         return (resolved_input,), kwargs
#
#     # Resolve kwargs
#     if kwargs:
#         resolved_kwargs = {
#             k: resolve_value(v, param_name=k)
#             for k, v in kwargs.items()
#         }
#         return args, resolved_kwargs
#
#     return args, kwargs
#
#
# def wrap_tool(tool: Any) -> Any:
#     """Wrap a langchain BaseTool to auto-resolve virtual paths in arguments.
#
#     The wrapper intercepts ``_run`` and ``_arun`` (or ``invoke`` / ``ainvoke``)
#     calls and converts any virtual paths to real filesystem paths before the
#     original tool logic runs.
#     """
#     # Try to wrap _run / _arun first (works for most BaseTool subclasses)
#     original_run = getattr(tool, "_run", None)
#     original_arun = getattr(tool, "_arun", None)
#
#     if original_run is not None:
#         @wraps(original_run)
#         def wrapped_run(*args: Any, **kwargs: Any) -> Any:
#             new_args, new_kwargs = _resolve_args(args, kwargs)
#             return original_run(*new_args, **new_kwargs)
#
#         tool._run = wrapped_run  # type: ignore[method-assign]
#
#     if original_arun is not None:
#         @wraps(original_arun)
#         async def wrapped_arun(*args: Any, **kwargs: Any) -> Any:
#             new_args, new_kwargs = _resolve_args(args, kwargs)
#             return await original_arun(*new_args, **new_kwargs)
#
#         tool._arun = wrapped_arun  # type: ignore[method-assign]
#
#     # Fallback: also wrap invoke / ainvoke at the BaseTool level
#     original_invoke = getattr(tool, "invoke", None)
#     if original_invoke is not None and original_invoke is not tool.invoke:
#         # Already wrapped above via _run, skip double wrapping
#         pass
#
#     return tool
