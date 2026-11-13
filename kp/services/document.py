"""Сборка .docx с коммерческим предложением.

Бланк выбирается по арендодателю: у ООО «ИРС» и у ИП Никонова разные
реквизиты в колонтитуле, поэтому это два отдельных файла с одинаковым
набором подстановок.
"""

import re
from io import BytesIO

from django.conf import settings
from docxtpl import DocxTemplate

from kp.services.formatting import format_date_with_letters, format_measure, format_money

IRS = "irs"
NIKONOV = "nik"

LANDLORD_CHOICES = (
    (IRS, 'ООО "ИРС"'),
    (NIKONOV, "ИП Никонов С.В."),
)

TEMPLATE_BY_LANDLORD = {
    IRS: "irs_kp.docx",
    NIKONOV: "nik_kp.docx",
}

# В имени файла оставляем только то, что безопасно отдавать в мессенджер и
# класть на диск: кавычки из названий вроде ООО "Ромашка" отбрасываем.
FILENAME_ALLOWED = re.compile(r"[^A-Za-z0-9_А-Яа-яёЁ\-.]")

# Аренда за месяц считается по 30 дням независимо от календаря.
DAYS_IN_MONTH = 30

# Новое КП почти всегда с 10%.
DEFAULT_SECURITY_PAYMENT_PERCENT = 10


class TemplateBusinessError(Exception):
    """Документ нельзя собрать: не хватает данных или не выбран бланк."""


def build_filename(shortname: str, sequence_number) -> str:
    """«ООО Ромашка» + 7 -> «ООО_Ромашка_КП-7.docx»."""

    return FILENAME_ALLOWED.sub("", f"{shortname} КП-{sequence_number}.docx".replace(" ", "_"))


def totals(items) -> dict:
    """Габариты набора: сумма по позициям с учётом количества.

    Нулевой параметр возвращаем пустой строкой — в шаблоне она гасит свой
    блок целиком, и в документе не появляется «вес – 0кг.».
    """

    sums = {"weight": 0.0, "area": 0.0, "volume": 0.0}
    for item in items:
        quantity = item["quantity"]
        sums["weight"] += (item.get("weight") or 0) * quantity
        sums["area"] += (item.get("space") or 0) * quantity
        sums["volume"] += (item.get("volume") or 0) * quantity

    return {name: format_measure(value) if value else "" for name, value in sums.items()}


def build_context(
    *,
    shortname: str,
    address: str,
    sequence_number,
    date_created,
    items: list[dict],
    rent_day: float,
    fio_manager: str | None = None,
    phone_manager: str | None = None,
    security_payment_percent: float = DEFAULT_SECURITY_PAYMENT_PERCENT,
) -> dict:
    """Контекст подстановки для бланка КП.

    items — позиции со снимком параметров оборудования на момент сборки:
    документ не должен меняться вслед за ночной выгрузкой.

    Менеджер в колонтитуле один на всех и берётся из настроек; параметрами
    его можно переопределить — пригодится в тестах.
    """

    sum_kp = sum((item.get("price") or 0) * item["quantity"] for item in items)

    return {
        "sequence_number": sequence_number,
        "date_full": format_date_with_letters(date_created),
        "shortname": shortname,
        "address": address,
        "rent_day": format_money(rent_day),
        "rent_month": format_money(rent_day * DAYS_IN_MONTH),
        # В шаблоне «Обеспечительный платеж – {{ob}} р.»: сюда идёт сумма,
        # а не процент, из которого она посчитана.
        "ob": format_money(sum_kp * security_payment_percent / 100),
        "items": items,
        **totals(items),
        "fio_manager": settings.KP_MANAGER_FIO if fio_manager is None else fio_manager,
        "phone_manager": settings.KP_MANAGER_PHONE if phone_manager is None else phone_manager,
    }


def render(context: dict, landlord: str) -> bytes:
    """Готовый .docx в память — файл весит меньше мегабайта."""

    filename = TEMPLATE_BY_LANDLORD.get(landlord)
    if not filename:
        raise TemplateBusinessError("Для выгрузки КП укажите арендодателя: у каждого арендодателя свой бланк.")

    path = settings.KP_TEMPLATES_DIR / filename
    if not path.exists():
        raise TemplateBusinessError(f"Бланк {filename} не найден в {settings.KP_TEMPLATES_DIR}")

    template = DocxTemplate(path)
    template.render(context)

    buffer = BytesIO()
    template.save(buffer)

    return buffer.getvalue()
