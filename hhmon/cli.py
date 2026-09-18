"""Командная строка: ``python -m hhmon run`` и друзья."""

from __future__ import annotations

import argparse
import logging
import sys

from . import config as config_mod
from .cover_letter import CoverLetterWriter, LLMConfig
from .exporters import to_csv, to_excel
from .filters import apply as apply_filters, dedupe
from .hh_client import HHClient, Vacancy
from .notify import TelegramNotifier
from .storage import Storage

log = logging.getLogger("hhmon")


def collect(cfg: config_mod.AppConfig) -> list[Vacancy]:
    client = HHClient(delay=cfg.search.delay_seconds)
    found: list[Vacancy] = []
    for query in cfg.search.queries:
        try:
            found.extend(
                client.search(
                    query,
                    schedule=cfg.search.schedule,
                    area=cfg.search.area,
                    experience=cfg.search.experience or None,
                    employment=cfg.search.employment or None,
                    search_period_days=cfg.search.search_period_days,
                    pages=cfg.search.pages,
                    per_page=cfg.search.per_page,
                )
            )
        except Exception as exc:  # один упавший запрос не должен останавливать остальные
            log.error("запрос «%s» пропущен: %s", query, exc)
    return apply_filters(dedupe(found), cfg.filter)


def cmd_run(cfg: config_mod.AppConfig, args: argparse.Namespace) -> int:
    vacancies = collect(cfg)
    log.info("после фильтров: %d вакансий", len(vacancies))

    with Storage(cfg.db_path) as db:
        new = db.upsert(vacancies)
        log.info("новых: %d", len(new))

        if cfg.llm_enabled and cfg.llm_api_key and new:
            writer = CoverLetterWriter.from_profile_file(
                LLMConfig(api_key=cfg.llm_api_key, base_url=cfg.llm_base_url, model=cfg.llm_model),
                cfg.profile_path,
            )
            for v in new[: cfg.max_letters_per_run]:
                try:
                    db.save_cover_letter(v.id, writer.write(v))
                    log.info("письмо готово: %s — %s", v.company, v.name)
                except Exception as exc:
                    log.error("письмо для %s не получилось: %s", v.id, exc)

    path = to_excel(vacancies, cfg.excel_path, new_ids={v.id for v in new})
    log.info("Excel: %s", path)
    if cfg.csv_path:
        log.info("CSV: %s", to_csv(vacancies, cfg.csv_path))

    if cfg.telegram_enabled and cfg.telegram_token and cfg.telegram_chat_id:
        to_send = new if not args.notify_all else vacancies
        if to_send:
            sent = TelegramNotifier(cfg.telegram_token, cfg.telegram_chat_id).send_digest(to_send)
            log.info("Telegram: отправлено сообщений: %d", sent)
        else:
            log.info("Telegram: новых вакансий нет, ничего не отправляю")
    return 0


def cmd_stats(cfg: config_mod.AppConfig, args: argparse.Namespace) -> int:
    with Storage(cfg.db_path) as db:
        st = db.stats()
    print(f"Всего в базе: {st['total']}")
    for status, n in sorted(st["by_status"].items()):
        print(f"  {status:8} {n}")
    print("По запросам:")
    for query, n in sorted(st["by_query"].items(), key=lambda kv: -kv[1]):
        print(f"  {n:4}  {query}")
    return 0


def cmd_letters(cfg: config_mod.AppConfig, args: argparse.Namespace) -> int:
    """Показать сохранённые письма — чтобы скопировать в форму отклика."""
    with Storage(cfg.db_path) as db:
        rows = [r for r in db.all_rows(status="new") if r["cover_letter"]]
    if not rows:
        print("Писем пока нет: включите [llm] в config.toml и запустите run.")
        return 0
    for r in rows[: args.limit]:
        print("=" * 80)
        print(f"{r['name']} — {r['company']}  ({r['url']})")
        print("-" * 80)
        print(r["cover_letter"])
    return 0


def cmd_mark(cfg: config_mod.AppConfig, args: argparse.Namespace) -> int:
    with Storage(cfg.db_path) as db:
        for vid in args.ids:
            db.set_status(vid, args.status)
    print(f"Обновлено: {len(args.ids)} → {args.status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hhmon", description="Монитор вакансий hh.ru")
    parser.add_argument("-c", "--config", default="config.toml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="собрать вакансии, обновить базу, выгрузить Excel, отправить дайджест")
    p_run.add_argument("--notify-all", action="store_true", help="слать в Telegram всё, а не только новое")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("stats", help="статистика по базе").set_defaults(func=cmd_stats)

    p_letters = sub.add_parser("letters", help="показать сгенерированные сопроводительные письма")
    p_letters.add_argument("--limit", type=int, default=20)
    p_letters.set_defaults(func=cmd_letters)

    p_mark = sub.add_parser("mark", help="отметить вакансии: applied / skipped")
    p_mark.add_argument("status", choices=["new", "applied", "skipped"])
    p_mark.add_argument("ids", type=int, nargs="+")
    p_mark.set_defaults(func=cmd_mark)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = config_mod.load(args.config)
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
