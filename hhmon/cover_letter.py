"""Генерация сопроводительных писем через любой OpenAI-совместимый API.

Работает с OpenAI, DeepSeek, OpenRouter, локальным Ollama/LM Studio — меняется только
``base_url`` и ``model``. Письмо строится из профиля кандидата (profile.md) и карточки
вакансии; результат сохраняется в базу, чтобы не платить дважды за одну вакансию.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from .hh_client import Vacancy

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты помогаешь кандидату писать короткие сопроводительные письма на hh.ru.
Правила:
- 4–6 предложений, без воды и без шаблонных фраз вроде «меня заинтересовала ваша вакансия»;
- первое предложение — про конкретную пользу для этой компании, а не про кандидата;
- упоминай только те навыки и проекты, которые есть в профиле кандидата; ничего не выдумывай;
- если в вакансии есть требование, которого нет в профиле, — не упоминай его вовсе;
- пиши на «вы», по-русски, без эмодзи и без обращения по имени;
- в конце одно предложение о готовности выполнить тестовое задание."""


@dataclass
class LLMConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.5
    max_tokens: int = 500


class CoverLetterWriter:
    def __init__(self, cfg: LLMConfig, profile: str):
        self.cfg = cfg
        self.profile = profile.strip()

    @classmethod
    def from_profile_file(cls, cfg: LLMConfig, path: str | Path) -> "CoverLetterWriter":
        return cls(cfg, Path(path).read_text(encoding="utf-8"))

    def build_messages(self, v: Vacancy) -> list[dict]:
        vacancy_card = (
            f"Вакансия: {v.name}\nКомпания: {v.company}\nЗарплата: {v.salary_text}\n"
            f"Опыт: {v.experience_ru}\nЗанятость: {v.employment_ru}\nФормат: {v.work_formats_ru}"
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"ПРОФИЛЬ КАНДИДАТА:\n{self.profile}\n\nВАКАНСИЯ:\n{vacancy_card}\n\nНапиши сопроводительное письмо.",
            },
        ]

    def write(self, v: Vacancy) -> str:
        resp = requests.post(
            f"{self.cfg.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.cfg.api_key}"},
            json={
                "model": self.cfg.model,
                "messages": self.build_messages(v),
                "temperature": self.cfg.temperature,
                "max_tokens": self.cfg.max_tokens,
            },
            timeout=90,
        )
        if not resp.ok:
            log.error("LLM ответил %s: %s", resp.status_code, resp.text[:300])
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
