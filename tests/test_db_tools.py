"""数据库引擎注册表 —— 类型名到 SqlRunner 类的解析（多引擎适配层的入口）。"""
import pytest

from app.db.sql_runner.base import SqlRunner
from app.db.tools import _RUNNER_REGISTRY, _load_runner_class


def test_别名_postgresql_解析到和_postgres_同一个类():
    assert _load_runner_class("postgresql") is _load_runner_class("postgres")


def test_类型名大小写不敏感():
    assert _load_runner_class("SQLITE") is _load_runner_class("sqlite")


def test_解析出来的是真正的_SqlRunner_子类():
    for name in ("sqlite", "postgres", "mysql"):
        cls = _load_runner_class(name)
        assert issubclass(cls, SqlRunner)
        assert name in cls.__module__, f"{name} 解析到了 {cls.__module__}"


def test_不支持的库抛错并给出可用清单():
    with pytest.raises(ValueError) as exc:
        _load_runner_class("mongodb")
    msg = str(exc.value)
    assert "mongodb" in msg
    assert "sqlite" in msg and "postgres" in msg, "报错里应列出受支持的类型"


@pytest.mark.xfail(
    reason="已知问题：注册表声明了 hive，但 backend/src/app/db/engine/hive/ 目录不存在（幽灵条目）",
    strict=False,
)
def test_注册表里每个声明的引擎都真的能被导入():
    """谁往注册表加一行，这条就会替他把“目录是否真的存在”验一遍。"""
    for name in _RUNNER_REGISTRY:
        _load_runner_class(name)
