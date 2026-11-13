from types import SimpleNamespace

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase, override_settings

from bot.kp_dialog import (
    PAGE_SIZE,
    attachment_name,
    author_title,
    basket,
    finish_row,
    load_groups,
    load_page,
    managers_message,
    notify_managers,
    page_keyboard,
    search,
)
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


class AckTest(SimpleTestCase):
    """MAX отклоняет пустой ответ на нажатие кнопки с 400 proto.payload."""

    def test_no_bare_ack_calls(self):
        import re
        from pathlib import Path

        source = Path(__file__).resolve().parent.joinpath("kp_dialog.py").read_text(encoding="utf-8")
        bare = re.findall(r"\.ack\(\s*\)", source)

        self.assertEqual(bare, [], "ack() без notification MAX отклоняет — передайте текст уведомления")

    def test_every_landlord_has_a_title_for_the_notification(self):
        from kp.services.document import LANDLORD_CHOICES, TEMPLATE_BY_LANDLORD

        self.assertEqual(set(dict(LANDLORD_CHOICES)), set(TEMPLATE_BY_LANDLORD))


class AttachmentNameTest(SimpleTestCase):
    """maxapi дописывает расширение по содержимому, не проверяя, есть ли оно."""

    def test_strips_extension(self):
        self.assertEqual(attachment_name("ООО_Ромашка_КП-1.docx"), "ООО_Ромашка_КП-1")

    def test_keeps_dots_inside_the_name(self):
        self.assertEqual(attachment_name("ООО_А.Б._КП-7.docx"), "ООО_А.Б._КП-7")

    def test_name_without_extension_survives(self):
        self.assertEqual(attachment_name("КП-3"), "КП-3")


USER = SimpleNamespace(user_id=90055844, first_name="Иван", last_name="Иванов", username="ivanov", full_name="Иван Иванов")

DATA = {
    "shortname": 'ООО "Ромашка"',
    "address": "г. Новосибирск, ул. Строителей, 15",
    "landlord": "irs",
}

ITEMS = [
    {"name": "Щит Ал универсал 0,63х3,00", "price": 28486.0, "quantity": 3},
    {"name": "Вертикаль 500", "price": 1490.0, "quantity": 56},
]


class AuthorTitleTest(SimpleTestCase):
    def test_prefers_username(self):
        self.assertEqual(author_title(USER), "Иван Иванов (@ivanov)")

    def test_falls_back_to_id(self):
        """Ник есть не у всех, но найти человека менеджеру всё равно нужно."""

        anonymous = SimpleNamespace(user_id=42, username=None, full_name="Пётр")
        self.assertEqual(author_title(anonymous), "Пётр (id 42)")

    def test_survives_missing_user(self):
        self.assertEqual(author_title(None), "неизвестно кто")


class ManagersMessageTest(SimpleTestCase):
    def test_contains_everything_a_manager_needs(self):
        text = managers_message(7, DATA, ITEMS, USER)

        self.assertIn("КП-7", text)
        self.assertIn('ООО "Ромашка"', text)
        self.assertIn("ул. Строителей, 15", text)
        self.assertIn('ООО "ИРС"', text)
        self.assertIn("Вертикаль 500 — 56 шт.", text)
        self.assertIn("168 898,00 ₽", text)
        self.assertIn("@ivanov", text)


class FakeBot:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, **kwargs):
        if self.fail:
            raise RuntimeError("чат недоступен")
        self.sent.append(kwargs)


class NotifyManagersTest(SimpleTestCase):
    @override_settings(KP_MANAGERS_CHAT_ID=None)
    def test_silent_when_chat_is_not_configured(self):
        bot = FakeBot()
        async_to_sync(notify_managers)(bot, 1, DATA, ITEMS, USER, b"PK", "КП-1.docx")

        self.assertEqual(bot.sent, [])

    @override_settings(KP_MANAGERS_CHAT_ID=-73410621418148)
    def test_sends_text_and_file(self):
        bot = FakeBot()
        async_to_sync(notify_managers)(bot, 1, DATA, ITEMS, USER, b"PK", "КП-1.docx")

        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.sent[0]["chat_id"], -73410621418148)
        self.assertEqual(bot.sent[0]["attachments"][0].filename, "КП-1")

    @override_settings(KP_MANAGERS_CHAT_ID=-73410621418148)
    def test_failure_does_not_propagate(self):
        """Пользователь свой файл уже получил — ронять диалог из-за чата нельзя."""

        async_to_sync(notify_managers)(FakeBot(fail=True), 1, DATA, ITEMS, USER, b"PK", "КП-1.docx")
