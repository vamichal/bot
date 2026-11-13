"""Импорт оборудования для КП из ночной выгрузки Access.

Access каждую ночь кладёт на FTP файл с позициями: группа, наименование, цена и
параметры (вес, площадь, объём, длина). Поля разделены «|» и не экранируются.
Файл — источник истины: то, что в нём есть, становится доступным для добавления
в КП, остальное помечается неактивным, но из базы не удаляется — на него
ссылаются уже созданные КП.
"""

import logging
from dataclasses import dataclass, field
from ftplib import FTP
from io import BytesIO
from pathlib import Path

from django.conf import settings

from kp.models import KPEquipment

logger = logging.getLogger("db")

NAME_COLUMN = "Nom_Name"
PRICE_COLUMN = "Nom_CenaA"
WEIGHT_COLUMN = "Nom_Massa"
SPACE_COLUMN = "Nom_M2Ed"
VOLUME_COLUMN = "Nom_M3Ed"
LENGTH_COLUMN = "Nom_Len"

# Access называет колонку Nom_Grp; остальные варианты — на случай переименования.
GROUP_COLUMNS = ("Nom_Grp", "Nom_Group", "Nom_Gruppa", "Nom_GroupName")

NUMERIC_COLUMNS = {
    "price": PRICE_COLUMN,
    "weight": WEIGHT_COLUMN,
    "space": SPACE_COLUMN,
    "volume": VOLUME_COLUMN,
    "length": LENGTH_COLUMN,
}

# Выгрузка идёт без экранирования, поэтому разделителем выбран символ, которого
# не бывает в наименованиях и группах: кавычки и «;» внутри значений встречаются.
DELIMITER = "|"

# Access отдаёт файл в кодировке Windows, но гарантий нет — пробуем по очереди.
ENCODINGS = ("utf-8-sig", "cp1251")

CHUNK_SIZE = 500

# Сколько первых ошибочных строк показать в логе, чтобы он не распух.
ERRORS_IN_LOG = 10

UPDATED_FIELDS = ("group", "price", "weight", "space", "volume", "length", "is_active")


class TmcImportError(Exception):
    """Файл не удалось получить или разобрать."""


@dataclass
class ImportStats:
    """Итоги импорта — уходят в лог и в вывод команды."""

    rows: int = 0
    invalid_rows: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    deactivated: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Отмечает битую строку; в лог попадают только первые — чтобы он не распух."""

        self.invalid_rows += 1

        if len(self.errors) < ERRORS_IN_LOG:
            self.errors.append(message)

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "invalid_rows": self.invalid_rows,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "deactivated": self.deactivated,
        }

    def summary(self) -> str:
        return (
            f"строк: {self.rows}, добавлено: {self.created}, обновлено: {self.updated}, "
            f"без изменений: {self.unchanged}, снято с выгрузки: {self.deactivated}, "
            f"битых строк: {self.invalid_rows}"
        )


def download_from_ftp() -> bytes:
    """Скачивает выгрузку с FTP в память — файл занимает десятки килобайт."""

    host = settings.KP_TMC_FTP_HOST
    if not host:
        raise TmcImportError("Не задан KP_TMC_FTP_HOST — проверьте project/.env")

    buffer = BytesIO()
    try:
        # S321: обычный FTP без шифрования — так отдаёт файл сервер Access, выбора протокола нет.
        # Обмен идёт внутри контура VPN; если на сервере поднимут FTPS, достаточно заменить FTP на FTP_TLS.
        with FTP(timeout=settings.KP_TMC_FTP_TIMEOUT) as ftp:  # noqa: S321
            ftp.connect(host, settings.KP_TMC_FTP_PORT)
            ftp.login(settings.KP_TMC_FTP_USER, settings.KP_TMC_FTP_PASSWORD)
            ftp.set_pasv(True)

            if settings.KP_TMC_FTP_DIR:
                ftp.cwd(settings.KP_TMC_FTP_DIR)

            ftp.retrbinary(f"RETR {settings.KP_TMC_FTP_FILENAME}", buffer.write)
    except TmcImportError:
        raise
    except Exception as error:
        raise TmcImportError(f"Не удалось забрать файл с FTP {host}: {error}") from error

    return buffer.getvalue()


def decode(raw: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    raise TmcImportError(f"Не удалось определить кодировку файла, пробовали: {', '.join(ENCODINGS)}")


def parse_number(value: str) -> float:
    """Access пишет дробные через запятую: «0,06»."""

    try:
        return float((value or "").strip().replace(",", ".") or 0)
    except ValueError:
        return 0.0


def parse(text: str, stats: ImportStats) -> dict[str, dict]:
    """Разбирает выгрузку в словарь «наименование → параметры».

    Экранирования в файле нет: поля просто разделены «|». Поэтому режем строку
    обычным split, а не модулем csv — тот принял бы кавычку в начале значения
    за открывающую и съел бы её вместе с частью названия.

    Повтор наименования в файле не ошибка: берём последнюю строку.
    Битая строка не валит импорт — считаем её и идём дальше.
    """

    lines = [line for line in text.splitlines() if line.strip()]

    if not lines:
        raise TmcImportError("Файл выгрузки пуст")

    columns = lines[0].split(DELIMITER)

    if NAME_COLUMN not in columns:
        raise TmcImportError(f"В файле нет колонки {NAME_COLUMN}, а есть: {columns}")

    group_column = next((column for column in GROUP_COLUMNS if column in columns), None)
    items: dict[str, dict] = {}

    for number, line in enumerate(lines[1:], start=2):  # первая строка — заголовок
        stats.rows += 1
        parts = line.split(DELIMITER)

        # Разделитель попал в значение: склеивать наугад нельзя — чинить надо выгрузку.
        if len(parts) != len(columns):
            stats.add_error(f"строка {number}: колонок {len(parts)} вместо {len(columns)}")
            continue

        row = dict(zip(columns, parts, strict=True))

        name = row[NAME_COLUMN].strip()
        if not name:
            stats.add_error(f"строка {number}: пустое наименование")
            continue

        item = {field_name: parse_number(row.get(column, "")) for field_name, column in NUMERIC_COLUMNS.items()}
        item["group"] = row[group_column].strip() if group_column else ""
        items[name] = item

    return items


def apply(items: dict[str, dict], stats: ImportStats, *, dry_run: bool = False) -> None:
    """Обновляет справочник: файл — источник истины."""

    existing = {equipment.name: equipment for equipment in KPEquipment.objects.all()}

    to_create = []
    to_update = []

    for name, values in items.items():
        equipment = existing.get(name)

        if equipment is None:
            to_create.append(KPEquipment(name=name, is_active=True, **values))
            stats.created += 1
            continue

        changed = equipment.is_active is False or any(
            getattr(equipment, field_name) != value for field_name, value in values.items()
        )

        if not changed:
            stats.unchanged += 1
            continue

        for field_name, value in values.items():
            setattr(equipment, field_name, value)
        equipment.is_active = True

        to_update.append(equipment)
        stats.updated += 1

    # Позиции, пропавшие из выгрузки, остаются в базе ради уже созданных КП.
    missing = [equipment for name, equipment in existing.items() if name not in items and equipment.is_active]
    for equipment in missing:
        equipment.is_active = False
    stats.deactivated = len(missing)

    if dry_run:
        return

    KPEquipment.objects.bulk_create(to_create, batch_size=CHUNK_SIZE)
    if to_update:
        KPEquipment.objects.bulk_update(to_update, UPDATED_FIELDS, batch_size=CHUNK_SIZE)
    if missing:
        KPEquipment.objects.bulk_update(missing, ["is_active"], batch_size=CHUNK_SIZE)


def import_kp_equipment(*, path: Path | str | None = None, dry_run: bool = False) -> ImportStats:
    """Точка входа: берёт файл с FTP (или локальный при path) и обновляет справочник."""

    if path:
        raw = Path(path).read_bytes()
        source = str(path)
    else:
        raw = download_from_ftp()
        source = f"ftp://{settings.KP_TMC_FTP_HOST}/{settings.KP_TMC_FTP_FILENAME}"

    stats = ImportStats()
    items = parse(decode(raw), stats)

    if not items:
        raise TmcImportError(f"В файле {source} нет ни одной позиции — справочник не трогаем")

    apply(items, stats, dry_run=dry_run)

    prefix = "Импорт оборудования для КП (dry-run)" if dry_run else "Импорт оборудования для КП"
    logger.info(f"{prefix} из {source}; {stats.summary()}")

    if stats.errors:
        logger.warning(f"Битые строки в {source}: {'; '.join(stats.errors)}")

    return stats
