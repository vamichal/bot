import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand

from maxapi import Bot

from bot.handlers import dp


class Command(BaseCommand):
    help = "Запуск бота MAX (long polling)"

    def handle(self, *args, **options):
        bot = Bot(settings.BOT_TOKEN)
        asyncio.run(dp.start_polling(bot))
