"""Чтение config.toml + переменных окружения (.env)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .filters import FilterConfig


@dataclass
class SearchConfig:
    queries: list[str] = field(default_factory=lambda: ["python"])
    schedule: str | None = "remote"
    area: int = 113
    experience: list[str] = field(default_factory=list)
    employment: list[str] = field(default_factory=list)
    search_period_days: int | None = 1
    pages: int = 1
    per_page: int = 50
    delay_seconds: float = 1.5


@dataclass
class AppConfig:
    search: SearchConfig
    filter: FilterConfig
    db_path: str = "data/hhmon.sqlite3"
    excel_path: str = "out/vacancies.xlsx"
    csv_path: str | None = None
    telegram_enabled: bool = False
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    llm_enabled: bool = False
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    profile_path: str = "profile.md"
    max_letters_per_run: int = 10


def _load_dotenv(path: Path) -> None:
    """Минимальный .env-парсер, чтобы не тянуть зависимость."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load(config_path: str | Path = "config.toml", dotenv_path: str | Path = ".env") -> AppConfig:
    config_path = Path(config_path)
    _load_dotenv(Path(dotenv_path))
    raw = tomllib.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}

    s = raw.get("search", {})
    f = raw.get("filter", {})
    e = raw.get("export", {})
    t = raw.get("telegram", {})
    llm = raw.get("llm", {})

    search = SearchConfig(
        queries=s.get("queries", ["python"]),
        schedule=s.get("schedule", "remote") or None,
        area=int(s.get("area", 113)),
        experience=s.get("experience", []),
        employment=s.get("employment", []),
        search_period_days=s.get("search_period_days", 1) or None,
        pages=int(s.get("pages", 1)),
        per_page=int(s.get("per_page", 50)),
        delay_seconds=float(s.get("delay_seconds", 1.5)),
    )
    flt = FilterConfig(
        include_keywords=f.get("include_keywords", []),
        exclude_keywords=f.get("exclude_keywords", []),
        exclude_companies=f.get("exclude_companies", []),
        min_salary=int(f.get("min_salary", 0)),
        allowed_experience=f.get("allowed_experience", []),
        remote_only=bool(f.get("remote_only", True)),
        suspicious_companies=f.get("suspicious_companies", []),
        suspicious_title_patterns=f.get("suspicious_title_patterns", []),
        max_responses=f.get("max_responses"),
    )
    return AppConfig(
        search=search,
        filter=flt,
        db_path=e.get("db_path", "data/hhmon.sqlite3"),
        excel_path=e.get("excel_path", "out/vacancies.xlsx"),
        csv_path=e.get("csv_path"),
        telegram_enabled=bool(t.get("enabled", False)),
        telegram_token=os.environ.get(t.get("bot_token_env", "TG_BOT_TOKEN")),
        telegram_chat_id=os.environ.get(t.get("chat_id_env", "TG_CHAT_ID")),
        llm_enabled=bool(llm.get("enabled", False)),
        llm_api_key=os.environ.get(llm.get("api_key_env", "LLM_API_KEY")),
        llm_base_url=llm.get("base_url", "https://api.openai.com/v1"),
        llm_model=llm.get("model", "gpt-4o-mini"),
        profile_path=llm.get("profile_path", "profile.md"),
        max_letters_per_run=int(llm.get("max_letters_per_run", 10)),
    )
