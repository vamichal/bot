import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from maxapi import Bot

from bot.handlers import dp


class Command(BaseCommand):
    help = "Запуск бота MAX (long polling)"

    def handle(self, *args, **options):
        if not settings.BOT_TOKEN:
            raise CommandError("BOT_TOKEN не задан в переменных окружения")
        bot = Bot(settings.BOT_TOKEN)
        self.stdout.write("Бот запущен (long polling)")
        asyncio.run(dp.start_polling(bot))
