import datetime

from django.test import SimpleTestCase

from kp.services.formatting import format_date_with_letters, format_measure, format_money


class FormatMoneyTest(SimpleTestCase):
    def test_groups_thousands_and_keeps_two_decimals(self):
        self.assertEqual(format_money(1234.56), "1 234,56")

    def test_pads_decimals(self):
        self.assertEqual(format_money(1000), "1 000,00")

    def test_rounds_to_kopecks(self):
        self.assertEqual(format_money(77455.199), "77 455,20")

    def test_groups_millions(self):
        self.assertEqual(format_money(12345678.9), "12 345 678,90")

    def test_zero(self):
        self.assertEqual(format_money(0), "0,00")

    def test_negative(self):
        self.assertEqual(format_money(-1234.5), "-1 234,50")

    def test_empty_stays_empty(self):
        """Пустая строка гасит свой блок в шаблоне — подменять её нулём нельзя."""

        self.assertEqual(format_money(None), "")
        self.assertEqual(format_money(""), "")


class FormatMeasureTest(SimpleTestCase):
    def test_drops_trailing_zeros(self):
        self.assertEqual(format_measure(8670), "8 670")

    def test_keeps_thousandths(self):
        self.assertEqual(format_measure(1234.567), "1 234,567")

    def test_trims_only_trailing_zeros(self):
        self.assertEqual(format_measure(56.70), "56,7")

    def test_rounds_beyond_thousandths(self):
        self.assertEqual(format_measure(0.0006), "0,001")

    def test_zero(self):
        self.assertEqual(format_measure(0), "0")

    def test_empty_stays_empty(self):
        self.assertEqual(format_measure(None), "")
        self.assertEqual(format_measure(""), "")


class FormatDateTest(SimpleTestCase):
    def test_writes_month_in_words(self):
        self.assertEqual(format_date_with_letters(datetime.date(2026, 11, 14)), "14 ноября 2026")

    def test_keeps_day_without_leading_zero(self):
        self.assertEqual(format_date_with_letters(datetime.date(2026, 1, 5)), "5 января 2026")

    def test_every_month_has_a_name(self):
        for month in range(1, 13):
            self.assertTrue(format_date_with_letters(datetime.date(2026, month, 1)))
