"""Сводка по собранным КП — то, что бот отвечает на /day.

Считаем по date_created: это дата по Europe/Moscow (см. комментарий у поля),
поэтому «сегодня» в сводке совпадает с «сегодня» у того, кто спрашивает.
"""

from dataclasses import dataclass
from datetime import date

from django.db.models import F, Sum
from django.utils import timezone

from kp.models import KP

# В удачный день КП собирают десятками, а сообщение в MAX не резиновое:
# список режем, но счётчик и сумма считаются по всем КП за день.
LIST_LIMIT = 30


@dataclass(frozen=True)
class KPSummary:
    """Одна строка сводки."""

    sequence_number: int
    shortname: str
    author: str
    total: float


@dataclass(frozen=True)
class DailyReport:
    """Итоги дня: hidden — сколько КП не поместилось в shown."""

    day: date
    count: int
    total: float
    shown: list[KPSummary]
    hidden: int


def author_of(kp: KP) -> str:
    """Кем подписать КП в сводке.

    Имя пишется в КП при сборке, но у старых записей его нет — там
    остаётся числовой id, по нему человека хотя бы можно найти.
    """

    if kp.author_name:
        return kp.author_name
    if kp.author_user_id:
        return f"id {kp.author_user_id}"
    return "автор неизвестен"


def daily_report(day: date | None = None) -> DailyReport:
    """Сколько КП собрано за день и на какую сумму."""

    day = day or timezone.localdate()

    found = (
        KP.objects.filter(date_created=day)
        .annotate(items_total=Sum(F("items__price") * F("items__quantity")))
        .order_by("sequence_number")
    )

    rows = [
        KPSummary(
            sequence_number=kp.sequence_number,
            shortname=kp.shortname,
            author=author_of(kp),
            # None — у КП без позиций: через бота такое не собрать, но
            # запись могли завести иначе, и сводка из-за неё падать не должна.
            total=kp.items_total or 0,
        )
        for kp in found
    ]

    return DailyReport(
        day=day,
        count=len(rows),
        total=sum(row.total for row in rows),
        shown=rows[:LIST_LIMIT],
        hidden=max(len(rows) - LIST_LIMIT, 0),
    )
