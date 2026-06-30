"""로컬 SQLite 데이터베이스 — Supabase 스키마와 1:1 호환.

Supabase 마이그레이션 경로:
    sqlite3 -csv -header local.db "SELECT * FROM unit_master" > unit_master.csv
    psql -c "COPY core.unit_master FROM 'unit_master.csv' CSV HEADER"
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


# Supabase core 스키마와 동일한 컬럼 정의
UNIT_MASTER_COLUMNS = [
    "complex_id", "dong", "ho", "canonical_ho_id",
    "floor", "floor_kind", "area_exclusive", "area_type",
    "direction", "public_price", "source", "evidence_confidence",
    "legal_public", "created_at", "updated_at",
]

LINE_FACT_COLUMNS = [
    "complex_id", "dong", "line", "direction",
    "area_type", "confidence", "observations", "revoked",
    "created_at", "updated_at",
]

HO_STATE_COLUMNS = [
    "complex_id", "canonical_ho_id", "status",
    "observed_at", "source", "metadata",
]

EVIDENCE_LOG_COLUMNS = [
    "complex_id", "canonical_ho_id", "field",
    "value_expected", "value_actual", "source", "severity",
    "created_at",
]


class LocalDB:
    """Supabase 호환 SQLite 로컬 데이터베이스."""

    def __init__(self, db_path: str | Path = "local.db"):
        self.path = Path(db_path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")

    def create_schema(self):
        """Supabase migrations/001_init_schema.sql 기반 테이블 생성."""
        self.conn.executescript("""
            DROP TABLE IF EXISTS unit_master;
            CREATE TABLE unit_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complex_id TEXT NOT NULL DEFAULT '',
                dong TEXT DEFAULT '',
                ho TEXT NOT NULL,
                canonical_ho_id TEXT,
                floor INTEGER,
                floor_kind TEXT DEFAULT 'exact',
                area_exclusive INTEGER,
                area_type TEXT DEFAULT '',
                direction TEXT DEFAULT '',
                public_price INTEGER,
                source TEXT DEFAULT '',
                evidence_confidence REAL DEFAULT 1.0,
                legal_public INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX idx_unit_match ON unit_master(complex_id, area_exclusive);
            CREATE INDEX idx_unit_canonical ON unit_master(canonical_ho_id);

            DROP TABLE IF EXISTS line_fact;
            CREATE TABLE line_fact (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complex_id TEXT NOT NULL,
                dong TEXT NOT NULL,
                line TEXT NOT NULL,
                direction TEXT DEFAULT '',
                area_type TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                observations INTEGER DEFAULT 1,
                revoked INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE UNIQUE INDEX idx_line_fact ON line_fact(complex_id, dong, line);

            DROP TABLE IF EXISTS ho_state;
            CREATE TABLE ho_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complex_id TEXT NOT NULL,
                canonical_ho_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('occupied','vacant','for_sale','for_rent','sold')),
                observed_at TEXT DEFAULT (datetime('now')),
                source TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            );

            DROP TABLE IF EXISTS evidence_log;
            CREATE TABLE evidence_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complex_id TEXT DEFAULT '',
                canonical_ho_id TEXT DEFAULT '',
                field TEXT DEFAULT '',
                value_expected TEXT DEFAULT '',
                value_actual TEXT DEFAULT '',
                source TEXT DEFAULT '',
                severity TEXT DEFAULT 'info',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    def insert_unit_master(self, rows: list[dict[str, Any]]):
        """unit_master에 행 삽입."""
        if not rows:
            return 0
        columns = [
            "complex_id", "dong", "ho", "canonical_ho_id",
            "floor", "floor_kind", "area_exclusive", "area_type",
            "direction", "public_price", "source",
        ]
        placeholders = ", ".join(["?"] * len(columns))
        sql = f"INSERT OR IGNORE INTO unit_master ({', '.join(columns)}) VALUES ({placeholders})"
        data = [tuple(r.get(c, "") for c in columns) for r in rows]
        self.conn.executemany(sql, data)
        self.conn.commit()
        return self.conn.total_changes

    def count(self, table: str = "unit_master") -> int:
        return self.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def export_csv(self, table: str, output_path: str | Path):
        """테이블을 Supabase \COPY용 CSV로 export."""
        import csv
        rows = self.conn.execute(f"SELECT * FROM {table}").fetchall()
        cols = [d[0] for d in self.conn.execute(f"PRAGMA table_info({table})")]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)
        return len(rows)

    def close(self):
        self.conn.close()
