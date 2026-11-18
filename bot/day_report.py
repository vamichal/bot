"""Команда /day: сколько КП собрано за сегодня.

Работает в любом чате, где есть бот — в группе её достаточно отправить
как /day, упоминание (@бот /day) тоже понимается. КП собираются в личке
с ботом, поэтому сводка считается по всем КП за день, а не по чату,
откуда пришла команда.
"""

import logging

from asgiref.sync import sync_to_async
from django.db import close_old_connections

from maxapi import Router
from maxapi.types import Command, MessageCreated

from kp.services.formatting import format_date_with_letters, format_money
from kp.services.stats import DailyReport, daily_report

logger = logging.getLogger(__name__)

router = Router()


@sync_to_async
def load_report() -> DailyReport:
    close_old_connections()
    return daily_report()


def report_message(report: DailyReport) -> str:
    """Текст сводки для чата."""

    day = format_date_with_letters(report.day)

    if not report.count:
        return f"📊 {day}\n\nКП сегодня ещё не собирали."

    lines = [f"• КП-{row.sequence_number} — {row.shortname} ({row.author})" for row in report.shown]
    if report.hidden:
        lines.append(f"…и ещё {report.hidden}")

    return (
        f"📊 {day}\n"
        f"Собрано КП: {report.count}\n\n"
        + "\n".join(lines)
        + f"\n\nСумма наборов: {format_money(report.total)} ₽"
    )


@router.message_created(Command("day"))
async def cmd_day(event: MessageCreated):
    """Сводка за сегодня.

    Ошибку базы гасим ответом в чат: /day спрашивают в группе, и молчание
    бота там выглядит как «команды нет».
    """

    try:
        report = await load_report()
    except Exception:
        logger.exception("Не удалось собрать сводку за день")
        await event.message.answer("Не удалось посчитать КП за сегодня. Попробуйте ещё раз чуть позже.")
        return

    await event.message.answer(report_message(report))
