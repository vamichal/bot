from io import BytesIO

from django.test import TestCase
from docx import Document

from kp.models import KP, KPEquipment
from kp.services.creation import build_document, create_kp
from kp.services.document import IRS


def equipment(name, **overrides):
    values = {"price": 100.0, "weight": 1.0, "space": 0.0, "volume": 0.0}
    values.update(overrides)
    return KPEquipment.objects.create(name=name, **values)


def document_text(raw: bytes) -> str:
    document = Document(BytesIO(raw))
    parts = [p.text for p in document.paragraphs]
    parts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


class CreateKPTest(TestCase):
    def setUp(self):
        self.anchor = equipment("Анкер торцевой", price=650.0, weight=1.6)
        self.beam = equipment("Балка выравнивающая 3,0 м.", price=8966.0, weight=35.0, volume=0.06)

    def build(self, **overrides):
        kwargs = {
            "shortname": 'ООО "Ромашка"',
            "address": "г. Новосибирск, ул. Строителей, 15",
            "landlord": IRS,
            "items": [
                {"equipment_id": self.anchor.id, "quantity": 10},
                {"equipment_id": self.beam.id, "quantity": 2},
            ],
        }
        kwargs.update(overrides)
        return create_kp(**kwargs)

    def test_numbers_are_sequential_across_all_kp(self):
        self.assertEqual(self.build().sequence_number, 1)
        self.assertEqual(self.build(shortname="Другой клиент").sequence_number, 2)

    def test_copies_equipment_parameters_into_items(self):
        kp = self.build()
        item = kp.items.get(name="Анкер торцевой")

        self.assertEqual(item.price, 650.0)
        self.assertEqual(item.quantity, 10)

    def test_item_keeps_old_price_after_catalogue_changed(self):
        """Снимок позиции: документ не должен меняться вслед за выгрузкой."""

        kp = self.build()
        self.anchor.price = 1.0
        self.anchor.save()

        self.assertEqual(kp.items.get(name="Анкер торцевой").price, 650.0)

    def test_uses_default_rent_day(self):
        self.assertEqual(self.build().rent_day, 500.0)


class BuildDocumentTest(TestCase):
    def setUp(self):
        self.beam = equipment("Балка выравнивающая 3,0 м.", price=8966.0, weight=35.0, volume=0.06)
        self.anchor = equipment("Анкер торцевой", price=650.0, weight=1.6)
        self.kp = create_kp(
            shortname='ООО "Ромашка"',
            address="г. Новосибирск, ул. Строителей, 15",
            landlord=IRS,
            items=[
                {"equipment_id": self.beam.id, "quantity": 2},
                {"equipment_id": self.anchor.id, "quantity": 10},
            ],
        )

    def test_returns_docx_and_filename(self):
        raw, filename = build_document(self.kp)

        self.assertEqual(filename, "ООО_Ромашка_КП-1.docx")
        self.assertTrue(raw.startswith(b"PK"))  # docx это zip

    def test_items_go_in_alphabetical_order(self):
        """Добавлены балка, затем анкер — в документе анкер должен быть первым."""

        text = document_text(build_document(self.kp)[0])

        self.assertLess(text.index("Анкер торцевой"), text.index("Балка выравнивающая"))

    def test_fills_totals(self):
        text = document_text(build_document(self.kp)[0])

        # 8966*2 + 650*10 = 24432, обеспечительный платёж 10% = 2443,20
        self.assertIn("Обеспечительный платеж – 2 443,20 р.", text)
        # вес 35*2 + 1,6*10 = 86
        self.assertIn("вес – 86кг.", text)

    def test_hides_zero_area(self):
        """У этих позиций площадь нулевая — блок про неё в документ не идёт."""

        self.assertNotIn("площадь щитов", document_text(build_document(self.kp)[0]))


class SavedKPTest(TestCase):
    def test_str_is_readable_in_admin(self):
        item = equipment("Анкер торцевой")
        kp = create_kp(
            shortname="Клиент",
            address="Адрес",
            landlord=IRS,
            items=[{"equipment_id": item.id, "quantity": 1}],
        )

        self.assertEqual(str(KP.objects.get(pk=kp.pk)), "КП-1 — Клиент")
