import datetime

from django.test import SimpleTestCase
from docx import Document

from kp.services.document import (
    IRS,
    NIKONOV,
    TemplateBusinessError,
    build_context,
    build_filename,
    render,
    totals,
)

ITEMS = [
    {"name": "Анкер торцевой", "quantity": 10, "price": 650.0, "weight": 1.6, "space": 0.0, "volume": 0.0},
    {"name": "Щит Ал линейный 0,70х3,00", "quantity": 4, "price": 100.0, "weight": 1.0, "space": 2.1, "volume": 0.01},
]


def context(**overrides):
    kwargs = {
        "shortname": 'ООО "Ромашка"',
        "address": "г. Москва, ул. Тестовая, 1",
        "sequence_number": 7,
        "date_created": datetime.date(2026, 11, 14),
        "items": ITEMS,
        "rent_day": 4321.0,
        "fio_manager": "Иванов Иван Иванович",
        "phone_manager": "+7 999 123-45-67",
    }
    kwargs.update(overrides)
    return build_context(**kwargs)


def document_text(raw: bytes) -> str:
    from io import BytesIO

    document = Document(BytesIO(raw))
    parts = [p.text for p in document.paragraphs]
    parts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    for section in document.sections:
        for part in (section.header, section.footer):
            parts += [p.text for p in part.paragraphs]
            parts += [cell.text for table in part.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


class FilenameTest(SimpleTestCase):
    def test_replaces_spaces_and_drops_quotes(self):
        self.assertEqual(build_filename('ООО "Ромашка"', 7), "ООО_Ромашка_КП-7.docx")

    def test_keeps_latin_and_digits(self):
        self.assertEqual(build_filename("Alpha 12", 3), "Alpha_12_КП-3.docx")

    def test_drops_slashes(self):
        """Слэш в названии клиента сделал бы из имени файла путь."""

        self.assertEqual(build_filename("ООО А/Б", 1), "ООО_АБ_КП-1.docx")


class TotalsTest(SimpleTestCase):
    def test_sums_with_quantity(self):
        self.assertEqual(totals(ITEMS)["weight"], "20")

    def test_zero_becomes_empty_string(self):
        """Пустая строка гасит блок в шаблоне: «вес – 0кг.» в документе не нужен."""

        self.assertEqual(totals([{"name": "x", "quantity": 1, "price": 0}])["volume"], "")


class ContextTest(SimpleTestCase):
    def test_security_payment_is_a_sum_not_a_percent(self):
        # 650*10 + 100*4 = 6900, 10% = 690
        self.assertEqual(context()["ob"], "690,00")

    def test_month_is_thirty_days(self):
        self.assertEqual(context(rent_day=1000)["rent_month"], "30 000,00")

    def test_date_in_words(self):
        self.assertEqual(context()["date_full"], "14 ноября 2026")


class RenderTest(SimpleTestCase):
    def test_renders_both_templates_without_leftover_tags(self):
        for landlord in (IRS, NIKONOV):
            with self.subTest(landlord=landlord):
                text = document_text(render(context(), landlord))
                self.assertNotIn("{{", text)
                self.assertNotIn("{%", text)

    def test_fills_body_and_footer(self):
        text = document_text(render(context(), IRS))

        self.assertIn("ООО \"Ромашка\"", text)
        self.assertIn("Анкер торцевой", text)
        self.assertIn("Обеспечительный платеж – 690,00 р.", text)
        self.assertIn("Иванов Иван Иванович", text)

    def test_requires_known_landlord(self):
        with self.assertRaises(TemplateBusinessError):
            render(context(), "")
