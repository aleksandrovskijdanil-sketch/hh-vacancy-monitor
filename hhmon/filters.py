"""Фильтрация выдачи: стоп-слова, минимальная зарплата, чёрный список компаний.

Отдельно помечаем (не выкидываем) подозрительные объявления — «оператор чата без опыта
за 80 000», однотипные объявления кадровых «центров занятости» и т.п. Решение остаётся за
человеком, но в таблице такие строки сразу видны.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hh_client import Vacancy


@dataclass
class FilterConfig:
    include_keywords: list[str] = field(default_factory=list)   # хотя бы одно должно быть в названии
    exclude_keywords: list[str] = field(default_factory=list)   # ни одного в названии
    exclude_companies: list[str] = field(default_factory=list)  # точное совпадение (без учёта регистра)
    min_salary: int = 0                                          # 0 — не фильтровать по зарплате
    allowed_experience: list[str] = field(default_factory=list) # пусто — любой опыт
    remote_only: bool = True
    suspicious_companies: list[str] = field(default_factory=list)
    suspicious_title_patterns: list[str] = field(default_factory=list)
    max_responses: int | None = None                             # отсекать перегретые вакансии


def _contains_any(text: str, words: list[str]) -> bool:
    low = text.lower()
    return any(w.lower() in low for w in words)


def flag_suspicious(v: Vacancy, cfg: FilterConfig) -> list[str]:
    flags: list[str] = []
    if _contains_any(v.company, cfg.suspicious_companies):
        flags.append("компания из списка подозрительных")
    for pattern in cfg.suspicious_title_patterns:
        if re.search(pattern, v.name, re.I):
            flags.append("шаблонное название")
            break
    if v.currency == "USD" and v.experience == "noExperience":
        flags.append("оплата в $ без опыта")
    if not v.company_trusted and v.salary_from and v.salary_from >= 100_000 and v.experience == "noExperience":
        flags.append("100k+ без опыта у непроверенной компании")
    return flags


def passes(v: Vacancy, cfg: FilterConfig) -> bool:
    if cfg.remote_only and v.work_formats and "REMOTE" not in v.work_formats:
        return False
    if cfg.include_keywords and not _contains_any(v.name, cfg.include_keywords):
        return False
    if _contains_any(v.name, cfg.exclude_keywords):
        return False
    if v.company.lower() in {c.lower() for c in cfg.exclude_companies}:
        return False
    if cfg.allowed_experience and v.experience not in cfg.allowed_experience:
        return False
    if cfg.min_salary:
        best = max(x for x in (v.salary_from, v.salary_to, 0) if x is not None)
        if best and best < cfg.min_salary:
            return False
    if cfg.max_responses is not None and v.responses is not None and v.responses > cfg.max_responses:
        return False
    return True


def apply(vacancies: list[Vacancy], cfg: FilterConfig) -> list[Vacancy]:
    """Отфильтровать список и проставить флаги оставшимся."""
    kept: list[Vacancy] = []
    for v in vacancies:
        if passes(v, cfg):
            v.flags = flag_suspicious(v, cfg)
            kept.append(v)
    return kept


def dedupe(vacancies: list[Vacancy]) -> list[Vacancy]:
    """Одна вакансия может прийти по нескольким запросам — оставляем первую, склеивая запросы."""
    by_id: dict[int, Vacancy] = {}
    for v in vacancies:
        if v.id in by_id:
            if v.query and v.query not in by_id[v.id].query:
                by_id[v.id].query += f", {v.query}"
        else:
            by_id[v.id] = v
    return list(by_id.values())
