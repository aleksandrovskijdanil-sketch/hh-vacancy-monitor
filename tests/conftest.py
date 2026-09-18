import html
import json

import pytest

from hhmon.hh_client import Vacancy, parse_state, parse_vacancies


def make_state(vacancies: list[dict], total: int | None = None) -> dict:
    return {"vacancySearchResult": {"vacancies": vacancies, "totalResults": total or len(vacancies)}}


RAW_VACANCIES = [
    {
        "vacancyId": 137196945,
        "name": "Инженер ИИ-автоматизаций / AI automation engineer",
        "company": {"name": "Topface Media", "visibleName": "Topface Media", "@trusted": True, "accreditedITEmployer": True},
        "compensation": {"from": 40000, "to": 60000, "currencyCode": "RUR", "gross": False},
        "workExperience": "noExperience",
        "employmentForm": "FULL",
        "workFormats": [{"workFormatsElement": ["REMOTE"]}],
        "area": {"@id": 88, "name": "Казань"},
        "publicationTime": {"@timestamp": 1789743222, "$": "2026-09-18T17:53:42.101+03:00"},
        "totalResponsesCount": 215,
        "links": {"desktop": "https://hh.ru/vacancy/137196945"},
        "labels": [{"id": "vacancy-label-no-resume"}],
    },
    {
        "vacancyId": 136996674,
        "name": "Оператор чата",
        "company": {"name": "ГОРЕЛКИНА АНГЕЛИНА", "@trusted": False},
        "compensation": {"from": 450, "to": 900, "currencyCode": "USD", "gross": False},
        "workExperience": "noExperience",
        "employmentForm": "PART",
        "workFormats": [{"workFormatsElement": ["REMOTE"]}],
        "area": {"@id": 2, "name": "Санкт-Петербург"},
        "publicationTime": {"@timestamp": 1789700000},
        "totalResponsesCount": 900,
        "links": {"desktop": "https://hh.ru/vacancy/136996674"},
    },
    {
        "vacancyId": 137492681,
        "name": "Senior системный аналитик",
        "company": {"name": "evrone.ru", "@trusted": True},
        "compensation": {"noCompensation": {}},
        "workExperience": "between3And6",
        "employmentForm": "FULL",
        "workFormats": [{"workFormatsElement": ["HYBRID"]}],
        "area": {"@id": 1, "name": "Москва"},
        "publicationTime": {"@timestamp": 1789600000},
        "totalResponsesCount": 12,
        "links": {"desktop": "https://hh.ru/vacancy/137492681"},
    },
]


@pytest.fixture
def page_html() -> str:
    """HTML, максимально похожий на настоящую страницу hh.ru: JSON в <template>, экранированный как в оригинале."""
    state_json = html.escape(json.dumps(make_state(RAW_VACANCIES, total=91), ensure_ascii=False), quote=True)
    return (
        "<!DOCTYPE html><html><head><title>Вакансии</title></head><body>"
        '<div data-qa="vacancy-serp__vacancy">…</div>'
        f'<template style="display:none" id="HH-Lux-InitialState">{state_json}</template>'
        "</body></html>"
    )


@pytest.fixture
def vacancies(page_html) -> list[Vacancy]:
    parsed, _ = parse_vacancies(parse_state(page_html), query="test")
    return parsed
