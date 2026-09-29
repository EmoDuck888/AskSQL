"""数据库方言规则：按目标数据库生成注入提示词的方言约束文本。

从 `agents/middleware/prompt.py` 抽出（原私有函数 `_get_dialect_rules`）。
抽出来的目的：这是个**纯函数**（输入字符串 → 输出字符串，无 IO、无第三方依赖），
留在重量级模块里会让测试被迫连带拉起整个应用（langchain / sqlalchemy / FalkorDB /
graphiti）。放在这里，测试可以零依赖地秒跑。

`prompt.py` 仍以原名 `_get_dialect_rules` 再导出，调用方无需改动。
"""
from __future__ import annotations


def get_dialect_rules(db_type: str) -> str:
    """根据数据库类型返回对应的方言规则文本。"""
    db_type_lower = db_type.lower()
    if db_type_lower == "sqlite":
        return (
            "- SQLite **不支持** `EXTRACT()` 函数，必须使用 `strftime()`：\n"
            "  - `EXTRACT(YEAR FROM date_col)` → `strftime('%Y', date_col)`\n"
            "  - `EXTRACT(MONTH FROM date_col)` → `strftime('%m', date_col)`\n"
            "  - `EXTRACT(DAY FROM date_col)` → `strftime('%d', date_col)`\n"
            '- SQLite 标识符不区分大小写，但必须存在。使用双引号 `"column"` 或反引号 `` `column` `` 处理特殊字符。\n'
            "- 不使用 schema 限定符（`database.table.column`）。\n"
            "- 常见错误速查：\n"
            "  - `no such column` → 检查列名拼写和大小写\n"
            "  - `no such table` → 检查表名拼写\n"
            "  - `ambiguous column` → 使用表别名：`table.column`\n"
            '  - `near "from"` / syntax error → 检查是否误用了不支持的函数'
        )
    elif db_type_lower == "postgres":
        return (
            "- PostgreSQL 支持标准 SQL 函数，包括 `EXTRACT()`、`DATE_TRUNC()` 等。\n"
            '- 标识符使用双引号 `"column"` 时区分大小写；无引号时不区分。\n'
            "- 分页使用 `LIMIT count OFFSET offset`。\n"
            "- 字符串连接使用 `||` 或 `CONCAT()`。\n"
            "- 常见错误速查：\n"
            "  - `column does not exist` → 检查列名拼写\n"
            "  - `relation does not exist` → 检查表名拼写\n"
            "  - `ambiguous column` → 使用表别名：`table.column`"
        )
    elif db_type_lower == "mysql":
        return (
            "- MySQL 支持标准 SQL 函数，包括 `EXTRACT()`、`YEAR()`、`MONTH()` 等。\n"
            '- 标识符使用反引号 `` `column` `` 处理特殊字符。\n'
            "- 分页使用 `LIMIT offset, count` 或 `LIMIT count OFFSET offset`。\n"
            "- 常见错误速查：\n"
            "  - `Unknown column` → 检查列名拼写\n"
            "  - `Table doesn't exist` → 检查表名拼写\n"
            "  - `ambiguous column` → 使用表别名：`table.column`"
        )
    else:
        return (
            f"- 当前数据库类型为 {db_type.upper()}，请使用该数据库的标准 SQL 方言。\n"
            "- 注意日期函数、标识符引用方式和分页语法的数据库差异。\n"
            "- 常见错误速查：\n"
            "  - 列/表不存在 → 检查拼写\n"
            "  - 歧义列 → 使用表别名：`table.column`"
        )
