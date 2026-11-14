import os

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Всё, что нужно сделать до запуска бота и веба — за один запуск Django.

    Раньше это были четыре отдельных вызова manage.py, и каждый платил
    полный импорт Django. На четверти ядра это десятки секунд сплошного
    троттлинга, из-за которого платформа не дожидалась готовности
    контейнера и убивала его.
    """

    help = "Миграции, справочник оборудования и суперпользователь одним процессом"

    def handle(self, *args, **options):
        call_command("migrate", interactive=False, verbosity=1)
        call_command("seed_equipment")
        self.ensure_superuser()

    def ensure_superuser(self):
        """Заводит администратора из переменных окружения.

        База на постоянном томе создаётся пустой, а шелла в контейнере
        нет — иначе в админку не войти.
        """

        username = os.getenv("DJANGO_SUPERUSER_USERNAME")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

        if not username or not password:
            self.stdout.write("DJANGO_SUPERUSER_USERNAME или _PASSWORD не заданы, администратора не создаём")
            return

        User = get_user_model()
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Суперпользователь {username} уже есть")
            return

        User.objects.create_superuser(username, os.getenv("DJANGO_SUPERUSER_EMAIL", ""), password)
        self.stdout.write(self.style.SUCCESS(f"Создан суперпользователь {username}"))
