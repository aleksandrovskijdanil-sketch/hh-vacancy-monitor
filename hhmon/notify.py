"""Уведомления в Telegram через Bot API (без лишних зависимостей — обычный requests)."""

from __future__ import annotations

import html
import logging

import requests

from .hh_client import Vacancy

log = logging.getLogger(__name__)
TG_LIMIT = 4096


def format_vacancy(v: Vacancy) -> str:
    warn = " ⚠️" if v.flags else ""
    lines = [
        f"<b>{html.escape(v.name)}</b>{warn}",
        f"{html.escape(v.company)} · {html.escape(v.salary_text)}",
        f"{v.experience_ru} · {v.employment_ru} · откликов: {v.responses if v.responses is not None else '—'}",
        f'<a href="{v.url}">hh.ru/vacancy/{v.id}</a>',
    ]
    if v.flags:
        lines.append("<i>" + html.escape("; ".join(v.flags)) + "</i>")
    return "\n".join(lines)


def build_digest(vacancies: list[Vacancy], title: str = "Новые вакансии") -> list[str]:
    """Разбивает дайджест на сообщения, укладывающиеся в лимит Telegram."""
    if not vacancies:
        return []
    header = f"📋 <b>{html.escape(title)}: {len(vacancies)}</b>\n\n"
    messages: list[str] = []
    current = header
    for v in sorted(vacancies, key=lambda v: v.published_at, reverse=True):
        block = format_vacancy(v) + "\n\n"
        if len(current) + len(block) > TG_LIMIT:
            messages.append(current.rstrip())
            current = block
        else:
            current += block
    messages.append(current.rstrip())
    return messages


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str | int):
        self.api = f"https://api.telegram.org/bot{bot_token}"
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        resp = requests.post(
            f"{self.api}/sendMessage",
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        if not resp.ok:
            log.error("Telegram ответил %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()

    def send_digest(self, vacancies: list[Vacancy], title: str = "Новые вакансии") -> int:
        messages = build_digest(vacancies, title)
        for msg in messages:
            self.send(msg)
        return len(messages)
