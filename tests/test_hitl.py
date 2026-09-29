"""危险 SQL 审核口径 —— 决定「要不要弹人工审批卡片」的那道判断。

口径（见 hitl.py 注释）：只拦**不可逆**的销毁操作（DELETE / DROP / TRUNCATE）；
UPDATE 等可逆修改放行，避免审批泛滥到没人看。
"""
import pytest

from app.agents.middleware.hitl import _destructive_op


def test_三种销毁操作都命中():
    assert _destructive_op("DROP TABLE tracks") == "DROP"
    assert _destructive_op("DELETE FROM invoices") == "DELETE"
    assert _destructive_op("TRUNCATE TABLE invoices") == "TRUNCATE"


def test_大小写与前导空白不影响判定():
    assert _destructive_op("  delete from t") == "DELETE"
    assert _destructive_op("drop table t") == "DROP"
    assert _destructive_op("\n\tDELETE FROM t") == "DELETE"


def test_只读查询不命中():
    assert _destructive_op("SELECT 1") is None
    assert _destructive_op("SELECT * FROM tracks WHERE TrackId = 1") is None


def test_可逆写操作不命中():
    """UPDATE / INSERT 能把数据改回来，不进审批流程。"""
    assert _destructive_op("UPDATE t SET a = 1") is None
    assert _destructive_op("INSERT INTO t VALUES (1)") is None


def test_空字符串与纯空白不命中():
    assert _destructive_op("") is None
    assert _destructive_op("   \n  ") is None


def test_关键字出现在中间不算命中():
    """当前实现只看开头——这里记录真实行为，防止以后改坏。"""
    assert _destructive_op("SELECT * FROM (DELETE)") is None


# ---- 已知限制：以下两种写法当前会被漏检（startswith 只看开头）----
@pytest.mark.xfail(reason="已知限制：注释前缀会让开头不是关键字", strict=False)
def test_注释前缀的销毁语句应被拦住():
    assert _destructive_op("/* 清理 */ DROP TABLE t") == "DROP"


@pytest.mark.xfail(reason="已知限制：CTE 前置时 DELETE 不在开头（WITH ... DELETE）", strict=False)
def test_cte_前置的销毁语句应被拦住():
    assert _destructive_op("WITH x AS (SELECT 1) DELETE FROM t") == "DELETE"
