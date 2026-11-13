from django.test import SimpleTestCase

from kp.services.tmc_import import ImportStats, TmcImportError, decode, parse

HEADER = "Nom_Grp|Nom_Name|Nom_CenaA|Nom_Massa|Nom_M2Ed|Nom_M3Ed|Nom_Len"


def parse_rows(*rows: str) -> tuple[dict[str, dict], ImportStats]:
    stats = ImportStats()
    items = parse("\n".join([HEADER, *rows]), stats)

    return items, stats


class ParseTest(SimpleTestCase):
    def test_reads_row(self):
        items, stats = parse_rows("Крепеж|Клин для планки контрфорса|153|0,1|0|0,01|0")

        self.assertEqual(stats.rows, 1)
        self.assertEqual(stats.invalid_rows, 0)
        self.assertEqual(
            items,
            {
                "Клин для планки контрфорса": {
                    "group": "Крепеж",
                    "price": 153.0,
                    "weight": 0.1,
                    "space": 0.0,
                    "volume": 0.01,
                    "length": 0.0,
                }
            },
        )

    def test_keeps_quotes_inside_value(self):
        """Выгрузка не экранирует кавычки — в названии они обычные символы."""

        items, _ = parse_rows('Крепеж|Шкворень "Т обр" |650|0,6|0|0,0007|0')

        self.assertEqual(list(items), ['Шкворень "Т обр"'])

    def test_keeps_quote_at_the_start_of_value(self):
        """Модуль csv принял бы такую кавычку за открывающую и съел бы её."""

        items, _ = parse_rows('Крепеж|"Т обр" шкворень|650|0,6|0|0,0007|0')

        self.assertEqual(list(items), ['"Т обр" шкворень'])

    def test_keeps_semicolon_inside_group(self):
        items, _ = parse_rows("Щиты ал.2 (>=0,7м; < 1м)|Щит Ал линейный 0,70х3,00|100|1|0|0|0")

        self.assertEqual(items["Щит Ал линейный 0,70х3,00"]["group"], "Щиты ал.2 (>=0,7м; < 1м)")

    def test_last_row_wins_for_duplicated_name(self):
        items, stats = parse_rows(
            "Крепеж|Анкер торцевой|650|1,6|0|0|0",
            "Крепеж|Анкер торцевой|700|1,6|0|0|0",
        )

        self.assertEqual(stats.rows, 2)
        self.assertEqual(items["Анкер торцевой"]["price"], 700.0)

    def test_counts_row_with_delimiter_inside_value(self):
        """Разделитель в значении не ломает импорт: строка попадает в битые."""

        items, stats = parse_rows(
            "Крепеж|Анкер|торцевой|650|1,6|0|0|0",
            "Крепеж|Анкер торцевой|650|1,6|0|0|0",
        )

        self.assertEqual(stats.rows, 2)
        self.assertEqual(stats.invalid_rows, 1)
        self.assertEqual(stats.errors, ["строка 2: колонок 8 вместо 7"])
        self.assertEqual(list(items), ["Анкер торцевой"])

    def test_counts_row_without_name(self):
        items, stats = parse_rows("Крепеж| |650|1,6|0|0|0")

        self.assertEqual(stats.invalid_rows, 1)
        self.assertEqual(items, {})

    def test_skips_blank_lines(self):
        items, stats = parse_rows("", "Крепеж|Анкер торцевой|650|1,6|0|0|0", "   ")

        self.assertEqual(stats.rows, 1)
        self.assertEqual(stats.invalid_rows, 0)
        self.assertEqual(list(items), ["Анкер торцевой"])

    def test_reads_file_without_group_column(self):
        stats = ImportStats()
        items = parse("Nom_Name|Nom_CenaA\nАнкер торцевой|650", stats)

        self.assertEqual(items["Анкер торцевой"]["group"], "")
        self.assertEqual(items["Анкер торцевой"]["price"], 650.0)

    def test_rejects_file_without_name_column(self):
        with self.assertRaises(TmcImportError):
            parse("Nom_Grp|Nom_CenaA\nКрепеж|650", ImportStats())

    def test_rejects_empty_file(self):
        with self.assertRaises(TmcImportError):
            parse("", ImportStats())


class DecodeTest(SimpleTestCase):
    def test_reads_windows_encoding(self):
        self.assertEqual(decode("Крепеж".encode("cp1251")), "Крепеж")

    def test_reads_utf8_with_bom(self):
        self.assertEqual(decode("Крепеж".encode("utf-8-sig")), "Крепеж")
