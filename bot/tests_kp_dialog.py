from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase

from bot.kp_dialog import PAGE_SIZE, basket, finish_row, load_groups, load_page, page_keyboard, search
from kp.models import KPEquipment


def payloads(attachment) -> list[str]:
    return [button.payload for row in attachment.payload.buttons for button in row]


class BasketTest(SimpleTestCase):
    def test_empty(self):
        self.assertEqual(basket([]), "Пока ничего не выбрано.")

    def test_lists_items_and_total(self):
        text = basket(
            [
                {"name": "Анкер торцевой", "price": 650.0, "quantity": 10},
                {"name": "Балка", "price": 8966.0, "quantity": 2},
            ]
        )

        self.assertIn("• Анкер торцевой — 10 шт.", text)
        self.assertIn("Сумма набора: 24 432,00 ₽", text)


class FinishRowTest(SimpleTestCase):
    def test_hides_done_until_something_is_picked(self):
        """Кнопка «Готово» без позиций приводила бы к пустому КП."""

        self.assertEqual([b.payload for b in finish_row(has_items=False)], ["cancel"])

    def test_shows_done_when_there_are_items(self):
        self.assertEqual([b.payload for b in finish_row(has_items=True)], ["done", "cancel"])


class PageKeyboardTest(SimpleTestCase):
    items = [{"id": 1, "name": "Анкер", "price": 1.0}]

    def test_first_page_has_no_back(self):
        found = payloads(page_keyboard(self.items, group_index=2, page=0, total=30, has_items=False))

        self.assertNotIn("g:2:-1", found)
        self.assertIn("g:2:1", found)

    def test_middle_page_has_both_directions(self):
        found = payloads(page_keyboard(self.items, group_index=2, page=1, total=30, has_items=False))

        self.assertIn("g:2:0", found)
        self.assertIn("g:2:2", found)

    def test_last_page_has_no_forward(self):
        found = payloads(page_keyboard(self.items, group_index=2, page=1, total=16, has_items=False))

        self.assertIn("g:2:0", found)
        self.assertNotIn("g:2:2", found)


class CatalogueQueriesTest(TestCase):
    def setUp(self):
        for number in range(12):
            KPEquipment.objects.create(name=f"Анкер {number:02d}", group="Крепеж", price=10.0)
        KPEquipment.objects.create(name="Балка выравнивающая", group="Балки", price=20.0)
        KPEquipment.objects.create(name="Снято с выгрузки", group="Балки", price=1.0, is_active=False)

    def test_groups_are_alphabetical_and_active_only(self):
        self.assertEqual(async_to_sync(load_groups)(), ["Балки", "Крепеж"])

    def test_page_is_limited_and_reports_total(self):
        items, total = async_to_sync(load_page)("Крепеж", 0)

        self.assertEqual(len(items), PAGE_SIZE)
        self.assertEqual(total, 12)

    def test_second_page_has_the_rest(self):
        items, _ = async_to_sync(load_page)("Крепеж", 1)

        self.assertEqual(len(items), 4)

    def test_search_ignores_case_and_inactive(self):
        self.assertEqual([item["name"] for item in async_to_sync(search)("балка")], ["Балка выравнивающая"])

    def test_search_finds_by_fragment(self):
        self.assertEqual(len(async_to_sync(search)("анкер")), PAGE_SIZE)

    def test_search_is_case_insensitive_for_cyrillic(self):
        """LIKE в SQLite игнорирует регистр только у латиницы."""

        self.assertEqual(len(async_to_sync(search)("БАЛКА")), 1)

    def test_search_treats_yo_as_ye(self):
        KPEquipment.objects.create(name="Клён садовый", group="Прочее", price=1.0)

        self.assertEqual(len(async_to_sync(search)("клен")), 1)
