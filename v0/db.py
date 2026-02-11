import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "db" / "migrations" / "001_init.sql"


def connect(db_path: str = "data/alpha.db") -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def insert_raw_post(conn: sqlite3.Connection, row: dict[str, Any]) -> bool:
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_posts
          (post_id, url, username, text, created_at, scraped_at, text_hash, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row.get("post_id"),
            row.get("url"),
            row.get("username"),
            row.get("text"),
            row.get("created_at"),
            row.get("scraped_at"),
            row.get("text_hash"),
            json.dumps(row.get("raw_json", row), ensure_ascii=False),
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def text_hash_exists(conn: sqlite3.Connection, text_hash_value: str) -> bool:
    if not text_hash_value:
        return False
    row = conn.execute(
        "SELECT 1 FROM raw_posts WHERE text_hash=? LIMIT 1",
        (text_hash_value,),
    ).fetchone()
    return row is not None


def update_gatekeeper(conn: sqlite3.Connection, post_id: str, gatekeeper: dict[str, Any]) -> None:
    conn.execute(
        "UPDATE raw_posts SET gatekeeper_json=?, processed_at=datetime('now') WHERE post_id=?",
        (json.dumps(gatekeeper, ensure_ascii=False), post_id),
    )
    conn.commit()


def update_alpha(
    conn: sqlite3.Connection,
    post_id: str,
    alpha: dict[str, Any],
    created_at: str | None,
) -> None:
    alpha_json = json.dumps(alpha, ensure_ascii=False)
    assets_json = json.dumps(alpha.get("assets", []), ensure_ascii=False)
    conn.execute(
        """
        UPDATE raw_posts
        SET alpha_json=?, processed_at=datetime('now')
        WHERE post_id=?
        """,
        (alpha_json, post_id),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO alpha_objects
          (post_id, assets_json, stance, timeframe, extraction_confidence, alpha_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            post_id,
            assets_json,
            alpha.get("stance"),
            alpha.get("timeframe"),
            alpha.get("extraction_confidence"),
            alpha_json,
            created_at,
        ),
    )
    conn.commit()


def fetch_unprocessed(conn: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    return conn.execute(
        """
        SELECT post_id, url, username, text, created_at, scraped_at, gatekeeper_json
        FROM raw_posts
        WHERE gatekeeper_json IS NULL
        ORDER BY created_at DESC
        """
    )
