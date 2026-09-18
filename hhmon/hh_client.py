"""Загрузка и разбор страниц поиска hh.ru.

hh.ru встраивает в HTML полное состояние страницы
(``<template id="HH-Lux-InitialState">``), поэтому API-ключ не нужен:
достаём JSON из страницы и читаем вакансии со всеми полями —
зарплата, опыт, формат работы, дата публикации, число откликов.
"""

from __future__ import annotations

import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

import requests

log = logging.getLogger(__name__)

HH_HOST = "https://hh.ru"
SEARCH_PATH = "/search/vacancy"
STATE_RE = re.compile(
    r'<template[^>]*id="HH-Lux-InitialState"[^>]*>(.*?)</template>', re.S
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

EXPERIENCE_RU = {
    "noExperience": "без опыта",
    "between1And3": "1–3 года",
    "between3And6": "3–6 лет",
    "moreThan6": "более 6 лет",
}
EMPLOYMENT_RU = {
    "FULL": "полная",
    "PART": "частичная",
    "PROJECT": "проектная",
    "PROBATION": "стажировка",
    "VOLUNTEER": "волонтёрство",
}
WORK_FORMAT_RU = {
    "REMOTE": "удалённо",
    "ON_SITE": "офис",
    "HYBRID": "гибрид",
    "FIELD_WORK": "разъездная",
}


class HHError(RuntimeError):
    """Страница hh.ru не отдала ожидаемые данные (капча, блокировка, смена вёрстки)."""


@dataclass
class Vacancy:
    id: int
    name: str
    company: str
    url: str
    salary_from: int | None
    salary_to: int | None
    currency: str | None
    gross: bool | None
    experience: str
    employment: str
    work_formats: list[str]
    area: str
    published_at: datetime
    responses: int | None
    query: str = ""
    company_trusted: bool = False
    accredited_it: bool = False
    no_resume_needed: bool = False
    flags: list[str] = field(default_factory=list)

    @property
    def salary_text(self) -> str:
        if self.salary_from is None and self.salary_to is None:
            return "не указана"
        cur = {"RUR": "₽", "USD": "$", "EUR": "€"}.get(self.currency or "", self.currency or "")
        parts = []
        if self.salary_from is not None:
            parts.append(f"от {self.salary_from:,}".replace(",", " "))
        if self.salary_to is not None:
            parts.append(f"до {self.salary_to:,}".replace(",", " "))
        tail = " до вычета" if self.gross else " на руки"
        return f"{' '.join(parts)} {cur}{tail}"

    @property
    def experience_ru(self) -> str:
        return EXPERIENCE_RU.get(self.experience, self.experience)

    @property
    def employment_ru(self) -> str:
        return EMPLOYMENT_RU.get(self.employment, self.employment)

    @property
    def work_formats_ru(self) -> str:
        return ", ".join(WORK_FORMAT_RU.get(f, f) for f in self.work_formats)

    def to_row(self) -> dict:
        """Плоское представление для таблиц и БД."""
        return {
            "id": self.id,
            "name": self.name,
            "company": self.company,
            "salary": self.salary_text,
            "salary_from": self.salary_from,
            "salary_to": self.salary_to,
            "currency": self.currency,
            "experience": self.experience_ru,
            "employment": self.employment_ru,
            "work_formats": self.work_formats_ru,
            "area": self.area,
            "published_at": self.published_at,
            "responses": self.responses,
            "query": self.query,
            "url": self.url,
            "flags": ", ".join(self.flags),
        }


def parse_state(page_html: str) -> dict:
    """Достаёт JSON состояния страницы из HTML. Бросает HHError, если его нет."""
    m = STATE_RE.search(page_html)
    if not m:
        if "captcha" in page_html.lower() and "showcaptcha" in page_html.lower():
            raise HHError("hh.ru показал капчу — увеличьте задержку между запросами")
        raise HHError("на странице нет HH-Lux-InitialState — изменилась вёрстка hh.ru?")
    return json.loads(html.unescape(m.group(1)))


def _compensation(raw: dict) -> tuple[int | None, int | None, str | None, bool | None]:
    if not raw or "noCompensation" in raw:
        return None, None, None, None
    return raw.get("from"), raw.get("to"), raw.get("currencyCode"), raw.get("gross")


def _work_formats(raw: list | None) -> list[str]:
    result: list[str] = []
    for item in raw or []:
        result.extend(item.get("workFormatsElement", []))
    return result


def _published(raw: dict | None) -> datetime:
    if raw and raw.get("@timestamp"):
        return datetime.fromtimestamp(int(raw["@timestamp"]))
    if raw and raw.get("$"):
        return datetime.fromisoformat(raw["$"]).replace(tzinfo=None)
    return datetime.now()


def parse_vacancies(state: dict, query: str = "") -> tuple[list[Vacancy], int]:
    """Возвращает (вакансии, всего найдено по запросу)."""
    result = state.get("vacancySearchResult") or {}
    total = int(result.get("totalResults") or 0)
    raw_items = result.get("vacancies", [])
    if total == 0 and raw_items:
        # По запросу ничего нет — hh.ru подмешивает «похожие» вакансии из других запросов.
        # Это не результаты поиска, поэтому отбрасываем их целиком.
        log.info("«%s»: точных совпадений нет, %d похожих пропущено", query, len(raw_items))
        return [], 0
    vacancies: list[Vacancy] = []
    for raw in raw_items:
        try:
            company = raw.get("company") or {}
            s_from, s_to, cur, gross = _compensation(raw.get("compensation") or {})
            labels = {lb.get("id") for lb in raw.get("labels") or []}
            vacancies.append(
                Vacancy(
                    id=int(raw["vacancyId"]),
                    name=raw.get("name", "").strip(),
                    company=(company.get("visibleName") or company.get("name") or "").strip(),
                    url=(raw.get("links") or {}).get("desktop")
                    or f"{HH_HOST}/vacancy/{raw['vacancyId']}",
                    salary_from=s_from,
                    salary_to=s_to,
                    currency=cur,
                    gross=gross,
                    experience=raw.get("workExperience", ""),
                    employment=raw.get("employmentForm") or (raw.get("employment") or {}).get("@type", ""),
                    work_formats=_work_formats(raw.get("workFormats")),
                    area=(raw.get("area") or {}).get("name", ""),
                    published_at=_published(raw.get("publicationTime")),
                    responses=raw.get("totalResponsesCount"),
                    query=query,
                    company_trusted=bool(company.get("@trusted")),
                    accredited_it=bool(company.get("accreditedITEmployer")),
                    no_resume_needed="vacancy-label-no-resume" in labels,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:  # одна кривая запись не должна ронять всё
            log.warning("пропускаю вакансию: %s (%s)", exc, raw.get("vacancyId"))
    return vacancies, total


class HHClient:
    """Тонкий клиент поиска hh.ru: одна сессия, вежливая задержка, повтор при сетевой ошибке."""

    def __init__(self, delay: float = 1.5, host: str = HH_HOST, session: requests.Session | None = None):
        self.delay = delay
        self.host = host
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ru-RU,ru;q=0.9",
            }
        )

    def fetch_page(self, params: dict) -> tuple[list[Vacancy], int]:
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.session.get(self.host + SEARCH_PATH, params=params, timeout=30)
                resp.raise_for_status()
                state = parse_state(resp.text)
                return parse_vacancies(state, query=params.get("text", ""))
            except (requests.RequestException, HHError) as exc:
                last_exc = exc
                log.warning("hh.ru: попытка %d не удалась: %s", attempt + 1, exc)
                time.sleep(self.delay * (attempt + 1))
        raise HHError(f"не удалось загрузить {params}: {last_exc}")

    def search(
        self,
        text: str,
        *,
        schedule: str | None = "remote",
        area: int = 113,
        experience: list[str] | None = None,
        employment: list[str] | None = None,
        search_period_days: int | None = None,
        order_by: str = "publication_time",
        pages: int = 1,
        per_page: int = 50,
    ) -> Iterator[Vacancy]:
        """Идёт по страницам выдачи и отдаёт вакансии по одной.

        ``experience``: noExperience, between1And3, between3And6, moreThan6.
        ``employment``: full, part, project, probation.
        ``search_period_days``: 1, 3, 7, 30 — только свежие публикации.
        """
        params: dict = {
            "text": text,
            "area": area,
            "items_on_page": per_page,
            "order_by": order_by,
        }
        if schedule:
            params["schedule"] = schedule
        if experience:
            params["experience"] = experience
        if employment:
            params["employment"] = employment
        if search_period_days:
            params["search_period"] = search_period_days

        seen = 0
        for page in range(pages):
            vacancies, total = self.fetch_page({**params, "page": page})
            # Хвост страницы сверх totalResults — тоже «похожие», а не найденные.
            vacancies = vacancies[: max(total - seen, 0)]
            log.info("«%s»: страница %d, %d вакансий (всего %d)", text, page + 1, len(vacancies), total)
            yield from vacancies
            seen += len(vacancies)
            if seen >= total or not vacancies:
                break
            time.sleep(self.delay)
