import json
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from kp.models import KPEquipment

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "equipment.json"


class FixtureFileTest(SimpleTestCase):
    def test_is_valid_utf8_json(self):
        """dumpdata -o на Windows пишет в cp1251, и на Linux такая фикстура не читается."""

        records = json.loads(FIXTURE.read_bytes().decode("utf-8"))

        self.assertGreater(len(records), 0)
        self.assertEqual(records[0]["model"], "kp.kpequipment")

    def test_every_record_has_a_name(self):
        records = json.loads(FIXTURE.read_bytes().decode("utf-8"))

        self.assertTrue(all(record["fields"]["name"].strip() for record in records))


class SeedCommandTest(TestCase):
    def test_fills_empty_catalogue(self):
        call_command("seed_equipment", verbosity=0)

        self.assertGreater(KPEquipment.objects.count(), 0)

    def test_does_not_touch_a_filled_catalogue(self):
        """Ночная выгрузка — источник истины, перетирать её фикстурой нельзя."""

        KPEquipment.objects.create(name="Единственная позиция", price=1.0)
        call_command("seed_equipment", verbosity=0)

        self.assertEqual(KPEquipment.objects.count(), 1)

    def test_force_reloads_over_existing(self):
        KPEquipment.objects.create(name="Единственная позиция", price=1.0)
        call_command("seed_equipment", "--force", verbosity=0)

        self.assertGreater(KPEquipment.objects.count(), 1)

    def test_seeded_catalogue_has_groups(self):
        call_command("seed_equipment", verbosity=0)

        groups = set(KPEquipment.objects.exclude(group="").values_list("group", flat=True))
        self.assertIn("Крепеж", groups)
