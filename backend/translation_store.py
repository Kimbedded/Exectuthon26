import json

from database import db_connection


def init_translation_store():
    with db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
        """)


def _entry(row):
    return {
        **json.loads(row["result_json"]),
        "id": row["id"],
        "created_at": row["created_at"]
    }


def save_translation(result: dict):
    with db_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO translations (result_json) VALUES (?)",
            (json.dumps(result, ensure_ascii=False),)
        )

        row = connection.execute(
            "SELECT * FROM translations WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

        return _entry(row)


def list_translations(limit: int = 50, offset: int = 0):
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM translations
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()

        return [_entry(row) for row in rows]