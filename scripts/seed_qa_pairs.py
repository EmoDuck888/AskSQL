# -*- coding: utf-8 -*-
"""向问答库(qa_pairs)批量写入针对 nl2sql(Chinook) 数据库的问答对。

流程:
1. 先在 Postgres 业务库上真实执行每条 SQL, 验证正确性;
2. 全部通过后写入 manage.db (SQLite) 的 qa_pairs 表, connection_id=6。
"""
import sqlite3
import datetime

import psycopg2

PG = dict(host="localhost", port=5432, dbname="nl2sql",
          user="postgres", password="zsy12311128")
CONNECTION_ID = 6  # db_connections 中名为 'chinook' 的连接

# (问题, SQL, 查询类型, 难度1-5)
QA_PAIRS = [
    (
        "数据库里一共有多少位艺人（艺术家）？",
        "SELECT COUNT(*) AS artist_count FROM artist;",
        "SELECT", 1,
    ),
    (
        "查询所有客户的姓名、所在国家和邮箱地址",
        "SELECT first_name, last_name, country, email FROM customer;",
        "SELECT", 2,
    ),
    (
        "查询价格最高的单曲是哪一首，价格是多少？",
        "SELECT name, unit_price FROM track ORDER BY unit_price DESC LIMIT 1;",
        "SELECT", 2,
    ),
    (
        "统计每种音乐流派包含的曲目数量，按曲目数量从多到少排序",
        "SELECT g.name AS genre, COUNT(t.track_id) AS track_count "
        "FROM genre g JOIN track t ON t.genre_id = g.genre_id "
        "GROUP BY g.name ORDER BY track_count DESC;",
        "SELECT", 3,
    ),
    (
        "查询消费总金额最高的前5名客户的姓名和总消费金额",
        "SELECT c.first_name, c.last_name, SUM(i.total) AS total_spent "
        "FROM customer c JOIN invoice i ON i.customer_id = c.customer_id "
        "GROUP BY c.customer_id, c.first_name, c.last_name "
        "ORDER BY total_spent DESC LIMIT 5;",
        "SELECT", 3,
    ),
    (
        "查询专辑数量最多的前10位艺术家及其专辑数量",
        "SELECT a.name AS artist, COUNT(al.album_id) AS album_count "
        "FROM artist a JOIN album al ON al.artist_id = a.artist_id "
        "GROUP BY a.artist_id, a.name "
        "ORDER BY album_count DESC LIMIT 10;",
        "SELECT", 4,
    ),
    (
        "统计2023年每个季度（Q1-Q4）的销售总额",
        "SELECT EXTRACT(QUARTER FROM invoice_date) AS quarter, SUM(total) AS total_sales "
        "FROM invoice "
        "WHERE EXTRACT(YEAR FROM invoice_date) = 2023 "
        "GROUP BY EXTRACT(QUARTER FROM invoice_date) "
        "ORDER BY quarter;",
        "SELECT", 4,
    ),
    (
        "查询哪些曲目没有被任何播放列表收录",
        "SELECT t.track_id, t.name FROM track t "
        "WHERE NOT EXISTS (SELECT 1 FROM playlist_track pt WHERE pt.track_id = t.track_id);",
        "SELECT", 5,
    ),
]


def verify(pg_conn):
    """在业务库上执行每条 SQL, 返回 {问题: 行数}; 有失败则抛异常。"""
    results = {}
    cur = pg_conn.cursor()
    for question, sql, _qtype, _diff in QA_PAIRS:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            results[question] = len(rows)
        except Exception as e:
            cur.close()
            raise RuntimeError(f"SQL 验证失败 [{question}]: {e}\nSQL: {sql}")
    cur.close()
    return results


def insert(sqlite_path):
    """将问答对写入 manage.db 的 qa_pairs 表。"""
    conn = sqlite3.connect(sqlite_path)
    cur = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    inserted = 0
    for question, sql, qtype, diff in QA_PAIRS:
        cur.execute(
            "INSERT INTO qa_pairs "
            "(connection_id, question, sql, query_type, difficulty_level, "
            " verified, inject_nl2sql, success_rate, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 1, 1, 1.0, ?, ?)",
            (CONNECTION_ID, question, sql, qtype, diff, now, now),
        )
        inserted += 1
    conn.commit()
    cur.close()
    conn.close()
    return inserted


if __name__ == "__main__":
    # 1) 验证 SQL
    pg_conn = psycopg2.connect(**PG)
    row_counts = verify(pg_conn)
    pg_conn.close()
    print("SQL 验证通过:")
    for q, n in row_counts.items():
        print(f"  [{n:>4} 行] {q}")

    # 2) 写入问答库
    count = insert("backend/src/app/data/manage.db")
    print(f"\n已写入 {count} 条问答对到 qa_pairs (connection_id={CONNECTION_ID})")
