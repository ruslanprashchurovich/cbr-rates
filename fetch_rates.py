"""Забирает официальные курсы USD и EUR ЦБ РФ и дописывает их в data/rates.csv.

Основной источник — официальный XML-эндпоинт ЦБ (https://www.cbr.ru/scripts/XML_daily.asp).
Если он недоступен (например, гео-блокировка зарубежных IP на раннерах GitHub),
скрипт автоматически берёт те же данные с зеркала https://www.cbr-xml-daily.ru.

Зависимостей нет — только стандартная библиотека Python 3.9+.
"""

import csv
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

CBR_XML_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
MIRROR_JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CURRENCIES = ("USD", "EUR")

CSV_PATH = Path(__file__).resolve().parent / "data" / "rates.csv"
CSV_HEADER = ["fetched_at_utc", "rate_date", "usd_rub", "eur_rub", "source"]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cbr-rates-bot)"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_cbr_xml(raw: bytes):
    """Разбирает ответ XML_daily.asp. Возвращает (дата курса, {код: курс})."""
    # ЦБ отдаёт XML в windows-1251 — определяем кодировку из декларации
    m = re.match(rb'^<\?xml[^>]*encoding="([^"]+)"', raw)
    encoding = m.group(1).decode("ascii") if m else "utf-8"
    text = re.sub(r"^<\?xml[^>]*\?>", "", raw.decode(encoding))

    root = ET.fromstring(text)
    rate_date = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date().isoformat()

    rates = {}
    for valute in root.iter("Valute"):
        code = valute.findtext("CharCode")
        if code in CURRENCIES:
            value = float(valute.findtext("Value").replace(",", "."))
            nominal = int(valute.findtext("Nominal"))
            rates[code] = value / nominal
    return rate_date, rates


def parse_mirror_json(raw: bytes):
    """Разбирает ответ зеркала cbr-xml-daily.ru (тот же формат данных, но JSON)."""
    data = json.loads(raw)
    rate_date = data["Date"][:10]
    rates = {}
    for code in CURRENCIES:
        valute = data["Valute"][code]
        rates[code] = valute["Value"] / valute["Nominal"]
    return rate_date, rates


def read_last_row(path: Path):
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    return rows[-1] if len(rows) > 1 else None


def main() -> None:
    try:
        rate_date, rates = parse_cbr_xml(fetch(CBR_XML_URL))
        source = "cbr.ru"
    except Exception as exc:
        print(f"cbr.ru недоступен ({exc}), беру данные с зеркала...")
        rate_date, rates = parse_mirror_json(fetch(MIRROR_JSON_URL))
        source = "cbr-xml-daily.ru"

    missing = [c for c in CURRENCIES if c not in rates]
    if missing:
        sys.exit(f"В ответе не нашлись валюты: {', '.join(missing)}")

    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rate_date,
        f"{rates['USD']:.4f}",
        f"{rates['EUR']:.4f}",
        source,
    ]

    # Курс ЦБ меняется раз в день: если дата и значения те же, что в последней
    # строке, ничего не дописываем — в CSV остаётся одна строка на каждый курс.
    last = read_last_row(CSV_PATH)
    if last and last[1:4] == row[1:4]:
        print(f"Без изменений: {rate_date} USD={row[2]} EUR={row[3]}")
        return

    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(CSV_HEADER)
        writer.writerow(row)
    print(f"Записано: {rate_date} USD={row[2]} EUR={row[3]} (источник: {source})")


if __name__ == "__main__":
    main()
