"""方言规则 —— 纯函数测试（零第三方依赖，秒级完成）。

函数已从 agents/middleware/prompt.py 抽到 app/utils/dialect.py，
所以这个文件**不会**连带 import langchain / sqlalchemy / FalkorDB。
"""
import pytest

from app.utils.dialect import get_dialect_rules


def test_sqlite_必须提醒用_strftime_代替_extract():
    rules = get_dialect_rules("sqlite")
    assert "strftime" in rules, "SQLite 分支必须给出 strftime 替代写法"
    assert "EXTRACT" in rules, "必须明确告知模型 SQLite 不支持 EXTRACT"
    assert "不使用 schema 限定符" in rules


def test_postgres_给出_date_trunc_与分页写法():
    rules = get_dialect_rules("postgres")
    assert "DATE_TRUNC" in rules
    assert "LIMIT count OFFSET offset" in rules


def test_mysql_用反引号引用标识符():
    rules = get_dialect_rules("mysql")
    assert "反引号" in rules
    assert "LIMIT offset, count" in rules


def test_未知数据库走兜底并回显类型名():
    rules = get_dialect_rules("oracle")
    assert "ORACLE" in rules, "兜底分支应把 db_type 大写回显，便于模型知道当前库"
    assert "标准 SQL 方言" in rules


@pytest.mark.parametrize("db_type", ["SQLite", "SQlite", "sQLITE"])
def test_库名大小写不敏感(db_type):
    assert get_dialect_rules(db_type) == get_dialect_rules("sqlite")


def test_三种已知方言输出互不相同():
    outs = {get_dialect_rules(t) for t in ("sqlite", "postgres", "mysql")}
    assert len(outs) == 3, "三种方言若输出相同，等于没做方言适配"


def test_任何输入都不返回空串():
    for db_type in ["sqlite", "postgres", "mysql", "oracle", "clickhouse", "duckdb", ""]:
        assert get_dialect_rules(db_type).strip(), f"{db_type!r} 返回了空规则"
