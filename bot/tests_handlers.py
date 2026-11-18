from types import SimpleNamespace

from django.test import SimpleTestCase

from maxapi.enums.chat_type import ChatType
from maxapi.filters import filter_attrs

from bot import day_report, kp_dialog
from bot.handlers import dp, echo


def message(text: str, chat_type: ChatType) -> SimpleNamespace:
    return SimpleNamespace(
        message=SimpleNamespace(
            body=SimpleNamespace(text=text),
            recipient=SimpleNamespace(chat_type=chat_type),
        )
    )


def handler_of(func) -> object:
    for router in (*dp.routers, dp):
        for handler in router.event_handlers:
            if handler.func_event is func:
                return handler
    raise AssertionError(f"обработчик {func.__name__} не зарегистрирован")


class RouterOrderTest(SimpleTestCase):
    def test_day_report_goes_before_the_kp_dialog(self):
        """Иначе /day посреди сборки КП съел бы поиск по названию."""

        order = [dp.routers.index(day_report.router), dp.routers.index(kp_dialog.router)]

        self.assertEqual(order, sorted(order))


class EchoFilterTest(SimpleTestCase):
    def filters_pass(self, event) -> bool:
        return filter_attrs(event, *handler_of(echo).filters)

    def test_answers_in_private_dialog(self):
        self.assertTrue(self.filters_pass(message("привет", ChatType.DIALOG)))

    def test_stays_silent_in_a_group(self):
        """В группе бот видит всю переписку — заглушка отвечала бы на каждое сообщение."""

        self.assertFalse(self.filters_pass(message("обсуждаем объект", ChatType.CHAT)))

    def test_stays_silent_in_a_channel(self):
        self.assertFalse(self.filters_pass(message("пост", ChatType.CHANNEL)))

    def test_ignores_messages_without_text(self):
        self.assertFalse(self.filters_pass(message("", ChatType.DIALOG)))
