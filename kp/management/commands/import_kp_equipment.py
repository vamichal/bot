from django.core.management.base import BaseCommand, CommandError

from kp.services.tmc_import import TmcImportError, import_kp_equipment


class Command(BaseCommand):
    help = "Обновляет справочник оборудования для КП из выгрузки Access (csv с FTP)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            dest="path",
            default=None,
            help="Путь к локальному csv вместо загрузки с FTP (для проверки формата и ручного прогона)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показать, что изменится, ничего не записывая в базу",
        )

    def handle(self, *args, **options):
        try:
            stats = import_kp_equipment(path=options["path"], dry_run=options["dry_run"])
        except TmcImportError as error:
            raise CommandError(str(error)) from error

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Режим dry-run: база не изменялась"))

        self.stdout.write(self.style.SUCCESS(stats.summary()))

        for error in stats.errors:
            self.stdout.write(self.style.WARNING(f"Пропущено — {error}"))
