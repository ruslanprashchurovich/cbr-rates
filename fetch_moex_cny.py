"""Забирает биржевой курс CNY/RUB с Мосбиржи и дописывает его в data/cny_rub.csv.

Источник — открытый ISS API Мосбиржи (https://iss.moex.com), инструмент
CNYRUB_TOM (юань с расчётами «завтра», основной валютный стакан).
Регистрация и ключи не нужны, зависимостей нет — только стандартная библиотека.

В отличие от курса ЦБ (одно значение в день), биржевой курс живёт в течение
торговой сессии, поэтому этот скрипт имеет смысл запускать каждые 5–10 минут.
Ночью и в выходные сделок нет — скрипт видит, что цена не изменилась,
и ничего не дописывает.
"""

import csv
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ISS_URL = (
    "https://iss.moex.com/iss/engines/currency/markets/selt/"
    "boards/CETS/securities/CNYRUB_TOM.json"
    "?iss.meta=off&iss.only=marketdata"
)

CSV_PATH = Path(__file__).resolve().parent / "data" / "cny_rub.csv"
CSV_HEADER = ["fetched_at_utc", "moex_time_msk", "cny_rub"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cbr-rates-bot)"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def read_last_row(path: Path):
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[-1] if len(rows) > 1 else None


def main() -> None:
    data = json.loads(fetch(ISS_URL))
    md = data.get("marketdata", {})
    rows = md.get("data") or []
    if not rows:
        sys.exit("ISS вернул пустой marketdata — проверьте доступность iss.moex.com")

    rec = dict(zip(md.get("columns", []), rows[0]))
    last = rec.get("LAST")
    if last is None:
        print("Сделок по CNYRUB_TOM сейчас нет (торги не идут) — пропускаю.")
        return

    # UPDATETIME — время последнего обновления данных по инструменту (МСК);
    # вне торгов оно замирает, что вместе с ценой даёт защиту от дубликатов.
    moex_time = rec.get("UPDATETIME") or rec.get("TIME") or rec.get("SYSTIME") or ""

    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        moex_time,
        f"{float(last):.4f}",
    ]

    last_row = read_last_row(CSV_PATH)
    if last_row and last_row[1:3] == row[1:3]:
        print(f"Без изменений: CNY/RUB={row[2]} (на {moex_time} МСК)")
        return

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(CSV_HEADER)
        writer.writerow(row)
    print(f"Записано: CNY/RUB={row[2]} (на {moex_time} МСК)")


if __name__ == "__main__":
    main()
