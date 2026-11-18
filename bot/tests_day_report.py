import datetime
from types import SimpleNamespace
from unittest import mock

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

from bot.day_report import cmd_day, load_report, report_message
from kp.models import KPEquipment
from kp.services.creation import create_kp
from kp.services.document import IRS
from kp.services.stats import DailyReport, KPSummary

DAY = datetime.date(2026, 11, 18)


def report(rows, *, hidden=0, count=None, total=None):
    return DailyReport(
        day=DAY,
        count=count if count is not None else len(rows),
        total=total if total is not None else sum(row.total for row in rows),
        shown=rows,
        hidden=hidden,
    )


def summary(number, shortname="Клиент", author="Иван Петров", total=1000.0):
    return KPSummary(sequence_number=number, shortname=shortname, author=author, total=total)


class ReportMessageTest(SimpleTestCase):
    def test_says_nothing_was_built(self):
        text = report_message(report([]))

        self.assertIn("18 ноября 2026", text)
        self.assertIn("КП сегодня ещё не собирали.", text)
        self.assertNotIn("Сумма наборов", text)

    def test_lists_number_recipient_and_author(self):
        text = report_message(report([summary(41, 'ООО "Ромашка"')]))

        self.assertIn("Собрано КП: 1", text)
        self.assertIn('• КП-41 — ООО "Ромашка" (Иван Петров)', text)

    def test_shows_total(self):
        text = report_message(report([summary(41, total=8966.0), summary(42, total=650.0)]))

        self.assertIn("Сумма наборов: 9 616,00 ₽", text)

    def test_mentions_rows_that_did_not_fit(self):
        """Счётчик считает все КП, а список обрезан — иначе сводка выглядит неполной."""

        text = report_message(report([summary(41)], hidden=4, count=5, total=5000.0))

        self.assertIn("Собрано КП: 5", text)
        self.assertIn("…и ещё 4", text)


class FakeEvent:
    """Событие MessageCreated ровно в том объёме, что нужен обработчику."""

    def __init__(self):
        self.answers = []
        self.message = SimpleNamespace(answer=self.answer)

    async def answer(self, text: str):
        self.answers.append(text)


class CmdDayTest(TestCase):
    def test_answers_with_the_report(self):
        anchor = KPEquipment.objects.create(name="Анкер торцевой", price=650.0)
        create_kp(
            shortname='ООО "Ромашка"',
            address="Адрес",
            landlord=IRS,
            items=[{"equipment_id": anchor.id, "quantity": 10}],
            author_user_id=42,
            author_name="Иван Петров",
        )

        event = FakeEvent()
        async_to_sync(cmd_day)(event)

        self.assertEqual(len(event.answers), 1)
        self.assertIn('• КП-1 — ООО "Ромашка" (Иван Петров)', event.answers[0])
        self.assertIn("6 500,00 ₽", event.answers[0])

    def test_answers_when_nothing_was_built(self):
        event = FakeEvent()
        async_to_sync(cmd_day)(event)

        self.assertIn("КП сегодня ещё не собирали.", event.answers[0])

    def test_loads_report_through_the_thread(self):
        """Проверяем сам sync_to_async-мост: ORM здесь синхронный."""

        self.assertEqual(async_to_sync(load_report)().count, 0)

    def test_answers_even_when_the_database_fails(self):
        """В группе молчание бота читается как «такой команды нет»."""

        event = FakeEvent()
        with mock.patch("bot.day_report.load_report", side_effect=RuntimeError("база занята")):
            with self.assertLogs("bot.day_report", level="ERROR") as logs:
                async_to_sync(cmd_day)(event)

        self.assertIn("Не удалось посчитать КП за сегодня", event.answers[0])
        self.assertIn("Не удалось собрать сводку за день", logs.output[0])
