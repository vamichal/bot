"""Форматирование значений для документов КП.

Перенесено из основного проекта: вид чисел и даты в коммерческом документе
должен совпадать с тем, что выдаёт CRM.
"""

import datetime
from decimal import Decimal

MONTHS = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def format_money(value) -> str:
    """Деньги в документе: «1 234,56» — разряды пробелом, копейки запятой, всегда два знака."""

    if value in ("", None):
        return ""

    amount = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, cents = f"{amount:.2f}".partition(".")
    negative = whole.startswith("-")
    digits = whole.lstrip("-")

    groups = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]

    return f"{'-' if negative else ''}{' '.join(groups) or '0'},{cents}"


def format_measure(value, decimals: int = 3) -> str:
    """Вес, площадь, объём: «8 670» и «1 234,567».

    Отличие от format_money: дробная часть переменной длины — у объёма значимы
    тысячные, а хвостовые нули в документе не нужны.
    """

    if value in ("", None):
        return ""

    amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals))
    whole, _, fraction = f"{amount:f}".partition(".")
    negative = whole.startswith("-")
    digits = whole.lstrip("-")
    fraction = fraction.rstrip("0")

    groups = []
    while digits:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]

    formatted = f"{'-' if negative else ''}{' '.join(groups) or '0'}"

    return f"{formatted},{fraction}" if fraction else formatted


def format_date_with_letters(date_obj: datetime.date) -> str:
    return f"{date_obj.day} {MONTHS[date_obj.month]} {date_obj.year}"
