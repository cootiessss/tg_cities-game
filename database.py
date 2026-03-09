"""Модуль для работы с SQLite: логирование запросов к LLM."""

import sqlite3
from datetime import datetime

DB_PATH = "bot_requests.db"


def init_db():
    """Создаёт таблицу requests, если она ещё не существует."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            reqtimes TEXT    NOT NULL,
            req      TEXT    NOT NULL,
            resp     TEXT    NOT NULL,
            llm      TEXT    NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_request(req: str, resp: str, llm: str):
    """Записывает один игровой ход в базу данных."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO requests (reqtimes, req, resp, llm) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), req, resp, llm),
    )
    conn.commit()
    conn.close()
