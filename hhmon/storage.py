"""SQLite-хранилище: помним, какие вакансии уже видели, чтобы слать только новые."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .hh_client import Vacancy

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    company       TEXT NOT NULL,
    url           TEXT NOT NULL,
    salary_from   INTEGER,
    salary_to     INTEGER,
    currency      TEXT,
    experience    TEXT,
    employment    TEXT,
    work_formats  TEXT,
    area          TEXT,
    published_at  TEXT,
    responses     INTEGER,
    query         TEXT,
    flags         TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'new',   -- new / applied / skipped
    cover_letter  TEXT
);
CREATE INDEX IF NOT EXISTS idx_vacancies_first_seen ON vacancies(first_seen);
"""


class Storage:
    def __init__(self, path: str | Path = "hhmon.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def upsert(self, vacancies: list[Vacancy]) -> list[Vacancy]:
        """Сохраняет вакансии и возвращает те, которых раньше не было."""
        now = datetime.now().isoformat(timespec="seconds")
        new: list[Vacancy] = []
        with self.conn:
            for v in vacancies:
                exists = self.conn.execute("SELECT 1 FROM vacancies WHERE id = ?", (v.id,)).fetchone()
                if exists:
                    self.conn.execute(
                        "UPDATE vacancies SET last_seen = ?, responses = ?, flags = ? WHERE id = ?",
                        (now, v.responses, ", ".join(v.flags), v.id),
                    )
                    continue
                self.conn.execute(
                    """INSERT INTO vacancies (id, name, company, url, salary_from, salary_to, currency,
                       experience, employment, work_formats, area, published_at, responses, query, flags,
                       first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        v.id, v.name, v.company, v.url, v.salary_from, v.salary_to, v.currency,
                        v.experience_ru, v.employment_ru, v.work_formats_ru, v.area,
                        v.published_at.isoformat(timespec="seconds"), v.responses, v.query,
                        ", ".join(v.flags), now, now,
                    ),
                )
                new.append(v)
        return new

    def set_status(self, vacancy_id: int, status: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE vacancies SET status = ? WHERE id = ?", (status, vacancy_id))

    def save_cover_letter(self, vacancy_id: int, text: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE vacancies SET cover_letter = ? WHERE id = ?", (text, vacancy_id))

    def all_rows(self, status: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM vacancies"
        args: tuple = ()
        if status:
            sql += " WHERE status = ?"
            args = (status,)
        sql += " ORDER BY published_at DESC"
        return self.conn.execute(sql, args).fetchall()

    def stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        by_status = dict(self.conn.execute("SELECT status, COUNT(*) FROM vacancies GROUP BY status").fetchall())
        by_query = dict(self.conn.execute("SELECT query, COUNT(*) FROM vacancies GROUP BY query").fetchall())
        return {"total": total, "by_status": by_status, "by_query": by_query}
