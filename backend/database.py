import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "idk_button.db"


@contextmanager
def db_connection():
    with closing(sqlite3.connect(DB_PATH)) as connection:
        connection.row_factory = sqlite3.Row
        with connection:
            yield connection


def init_db():
    with db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS expressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT NOT NULL,
                meaning TEXT NOT NULL,
                translation TEXT NOT NULL,
                example TEXT NOT NULL,
                target_language TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                )
            )
        """)
def save_expression(
    expression: str,
    meaning: str,
    translation: str,
    example: str,
    target_language: str
):
    with db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expressions
                (expression, meaning, translation, example, target_language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (expression, meaning, translation, example, target_language)
        )

        row = connection.execute(
            "SELECT * FROM expressions WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

        return dict(row)


def list_expressions(limit: int = 50, offset: int = 0):
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM expressions
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()

        return [dict(row) for row in rows]