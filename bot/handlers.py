import logging

from maxapi import Dispatcher, F
from maxapi.types import BotStarted, Command, MessageCreated

from bot import kp_dialog

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()
dp.include_routers(kp_dialog.router)


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
        "/kp — собрать КП и получить готовый .docx"
    )


# None — это «активного диалога нет»: без него заглушка перехватывала бы
# ответы на шагах сборки КП, потому что обработчики диспетчера проверяются
# раньше, чем обработчики подключённого роутера.
@dp.message_created(F.message.body.text, None)
async def echo(event: MessageCreated):
    await event.message.answer("Не понял команду. Отправь /kp — соберём коммерческое предложение.")
