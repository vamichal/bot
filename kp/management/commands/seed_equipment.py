from django.core.management import call_command
from django.core.management.base import BaseCommand

from kp.models import KPEquipment

FIXTURE = "equipment"


class Command(BaseCommand):
    help = "Засевает справочник оборудования из фикстуры, если он пуст"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Загрузить фикстуру поверх существующих записей",
        )

    def handle(self, *args, **options):
        # FTP с ночной выгрузкой живёт во внутренней сети и из облака
        # недоступен, поэтому на сервере справочник засевается фикстурой.
        # Источник истины — по-прежнему выгрузка: как только импорт
        # отработает, он перезапишет эти записи.
        if KPEquipment.objects.exists() and not options["force"]:
            self.stdout.write(f"Справочник не пуст ({KPEquipment.objects.count()} позиций), фикстура не нужна")
            return

        call_command("loaddata", FIXTURE, verbosity=0)
        self.stdout.write(self.style.SUCCESS(f"Справочник засеян из фикстуры: {KPEquipment.objects.count()} позиций"))
