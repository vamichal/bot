import logging

from maxapi import Dispatcher, F
from maxapi.enums.chat_type import ChatType
from maxapi.types import BotStarted, Command, MessageCreated

from bot import day_report, kp_dialog

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()
# day_report впереди: /day должна отвечать и посреди сборки КП, иначе её
# съест обработчик поиска по названию на шаге выбора оборудования.
dp.include_routers(day_report.router, kp_dialog.router)


@dp.bot_started()
async def on_start_button(event: BotStarted):
    """Пользователь нажал кнопку «Начать» в профиле бота."""
    await event.bot.send_message(
        chat_id=event.chat_id,
        text="Привет! Я бот аренды. Отправь /kp — соберём коммерческое предложение.",
    )


@dp.message_created(Command("start"))
async def cmd_start(event: MessageCreated):
    await event.message.answer(
        "Привет! 👋\n\n"
        "Я помогу собрать коммерческое предложение.\n"
        "Команды:\n"
        "/kp — собрать КП и получить готовый .docx\n"
        "/day — сколько КП собрано сегодня"
    )


# None — это «активного диалога нет»: заглушка не должна отвечать на шагах
# сборки КП, даже если роутер почему-то пропустил сообщение.
#
# Только личный диалог: в группе бот получает всю переписку, и без этого
# условия он отвечал бы «Не понял команду» на каждое сообщение коллег.
@dp.message_created(F.message.body.text, F.message.recipient.chat_type == ChatType.DIALOG, None)
async def echo(event: MessageCreated):
    await event.message.answer("Не понял команду. Отправь /kp — соберём коммерческое предложение.")
