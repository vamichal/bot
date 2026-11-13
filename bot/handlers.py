import logging

from asgiref.sync import sync_to_async
from django.db import close_old_connections

from maxapi import Dispatcher, F
from maxapi.types import BotStarted, Command, MessageCreated

from bot import kp_dialog
from bot.models import Item

logging.basicConfig(level=logging.INFO)

dp = Dispatcher()
dp.include_routers(kp_dialog.router)


@sync_to_async
def get_available_items():
    # Django ORM синхронный, поэтому оборачиваем в sync_to_async
    close_old_connections()
    return list(Item.objects.filter(is_available=True))


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
        "/items — список товаров с ценами"
    )


@dp.message_created(Command("items"))
async def cmd_items(event: MessageCreated):
    items = await get_available_items()
    if not items:
        await event.message.answer("Пока товаров нет. Загляните позже!")
        return
    lines = [f"• {item.name} — {item.price_per_day} ₽/сутки" for item in items]
    await event.message.answer("📋 Доступные товары:\n\n" + "\n".join(lines))


# None — это «активного диалога нет»: без него заглушка перехватывала бы
# ответы на шагах сборки КП, потому что обработчики диспетчера проверяются
# раньше, чем обработчики подключённого роутера.
@dp.message_created(F.message.body.text, None)
async def echo(event: MessageCreated):
    await event.message.answer("Не понял команду. Отправь /kp — соберём коммерческое предложение.")
