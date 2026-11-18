import datetime

from django.test import TestCase

from kp.models import KP, KPEquipment
from kp.services.creation import create_kp
from kp.services.document import IRS
from kp.services.stats import LIST_LIMIT, daily_report


def equipment(name, price):
    return KPEquipment.objects.create(name=name, price=price, weight=1.0, space=0.0, volume=0.0)


class DailyReportTest(TestCase):
    def setUp(self):
        self.anchor = equipment("Анкер торцевой", 650.0)
        self.beam = equipment("Балка выравнивающая 3,0 м.", 8966.0)

    def build(self, shortname="Клиент", quantity=1, **overrides):
        return create_kp(
            shortname=shortname,
            address="Адрес",
            landlord=IRS,
            items=[{"equipment_id": self.anchor.id, "quantity": quantity}],
            **overrides,
        )

    def test_empty_day(self):
        report = daily_report()

        self.assertEqual(report.count, 0)
        self.assertEqual(report.total, 0)
        self.assertEqual(report.shown, [])

    def test_counts_only_requested_day(self):
        """КП вчерашнего дня в сегодняшнюю сводку попадать не должно."""

        yesterday = self.build(shortname="Вчерашний")
        KP.objects.filter(pk=yesterday.pk).update(
            date_created=yesterday.date_created - datetime.timedelta(days=1)
        )
        self.build(shortname="Сегодняшний")

        report = daily_report()

        self.assertEqual(report.count, 1)
        self.assertEqual([row.shortname for row in report.shown], ["Сегодняшний"])

    def test_sums_items(self):
        self.build(quantity=10)
        create_kp(
            shortname="Второй",
            address="Адрес",
            landlord=IRS,
            items=[{"equipment_id": self.beam.id, "quantity": 2}],
        )

        report = daily_report()

        # 650*10 + 8966*2 = 24432
        self.assertEqual(report.count, 2)
        self.assertEqual(report.total, 24432.0)

    def test_author_name_from_snapshot(self):
        self.build(author_user_id=777, author_name="Иван Петров")

        self.assertEqual(daily_report().shown[0].author, "Иван Петров")

    def test_falls_back_to_user_id_for_old_kp(self):
        """У КП, собранных до появления поля, имени нет — остаётся id."""

        self.build(author_user_id=777)

        self.assertEqual(daily_report().shown[0].author, "id 777")

    def test_falls_back_when_author_is_unknown(self):
        self.build()

        self.assertEqual(daily_report().shown[0].author, "автор неизвестен")

    def test_rows_are_ordered_by_number(self):
        self.build(shortname="Первый")
        self.build(shortname="Второй")

        self.assertEqual([row.sequence_number for row in daily_report().shown], [1, 2])

    def test_long_day_is_cut_but_counted_in_full(self):
        for index in range(LIST_LIMIT + 3):
            self.build(shortname=f"Клиент {index}")

        report = daily_report()

        self.assertEqual(report.count, LIST_LIMIT + 3)
        self.assertEqual(len(report.shown), LIST_LIMIT)
        self.assertEqual(report.hidden, 3)

    def test_explicit_day(self):
        kp = self.build()
        day = kp.date_created - datetime.timedelta(days=5)
        KP.objects.filter(pk=kp.pk).update(date_created=day)

        self.assertEqual(daily_report(day).count, 1)
        self.assertEqual(daily_report().count, 0)
