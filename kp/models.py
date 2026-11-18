from django.db import models
from django.utils import timezone

from kp.services.document import DEFAULT_RENT_DAY, DEFAULT_SECURITY_PAYMENT_PERCENT, LANDLORD_CHOICES


class KPEquipment(models.Model):
    """Оборудование, доступное к добавлению в КП.

    Таблица целиком заполняется ночной выгрузкой из Access (tmc_data.csv) —
    руками её не редактируют. Позиция, пропавшая из выгрузки, не удаляется,
    а помечается неактивной: в новые КП её не добавить, а старые документы
    продолжают ссылаться на неё.
    """

    name = models.CharField("Наименование", max_length=255, unique=True)
    group = models.CharField("Номенклатурная группа", max_length=70, blank=True, default="")
    price = models.FloatField("Цена", default=0)
    weight = models.FloatField("Вес (кг)", default=0)
    space = models.FloatField("Площадь (м2)", default=0)
    volume = models.FloatField("Объем (м3)", default=0)
    length = models.FloatField("Длина (м)", default=0)
    is_active = models.BooleanField("Есть в последней выгрузке", default=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Оборудование для КП"
        verbose_name_plural = "Оборудование для КП"
        ordering = ["name"]


class KP(models.Model):
    """Коммерческое предложение, собранное через бота.

    Номер сквозной по всем КП, а не по клиенту: в боте клиента как
    отдельной сущности нет, получатель — просто строка.
    """

    sequence_number = models.PositiveIntegerField("Номер", unique=True)
    shortname = models.CharField("Получатель", max_length=255)
    address = models.TextField("Адрес объекта")
    landlord = models.CharField("Арендодатель", max_length=10, choices=LANDLORD_CHOICES)
    rent_day = models.FloatField("Стоимость аренды в день", default=DEFAULT_RENT_DAY)
    security_payment_percent = models.FloatField(
        "Процент обеспечительного платежа",
        default=DEFAULT_SECURITY_PAYMENT_PERCENT,
    )
    author_user_id = models.BigIntegerField("ID пользователя MAX", null=True, blank=True)
    # Имя автора — снимок на момент сборки: в сводке по дню нужно читаемое
    # «кто собрал», а по числовому id в чате человека не узнать.
    author_name = models.CharField("Кто собрал", max_length=255, blank=True, default="")
    # Намеренно не auto_now_add: у DateField он заполняется datetime.date.today(),
    # то есть датой по часам контейнера (на Amvera — UTC), а не по TIME_ZONE.
    # КП, собранное ночью по Москве, получало бы вчерашнюю дату — и в документе,
    # и в сводке за день.
    date_created = models.DateField("Дата", default=timezone.localdate)

    def __str__(self):
        return f"КП-{self.sequence_number} — {self.shortname}"

    class Meta:
        verbose_name = "Коммерческое предложение"
        verbose_name_plural = "Коммерческие предложения"
        ordering = ["-sequence_number"]


class KPItem(models.Model):
    """Позиция КП со снимком параметров оборудования.

    Наименование, цена и габариты копируются в момент сборки: документ
    должен открываться одинаково, даже если позицию убрали из ночной
    выгрузки или у неё изменилась цена.
    """

    kp = models.ForeignKey(KP, on_delete=models.CASCADE, related_name="items", verbose_name="КП")
    equipment = models.ForeignKey(
        KPEquipment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="Оборудование",
    )
    name = models.CharField("Наименование", max_length=255)
    price = models.FloatField("Цена", default=0)
    weight = models.FloatField("Вес (кг)", default=0)
    space = models.FloatField("Площадь (м2)", default=0)
    volume = models.FloatField("Объем (м3)", default=0)
    quantity = models.PositiveIntegerField("Количество")

    def __str__(self):
        return f"{self.name} — {self.quantity} шт."

    class Meta:
        verbose_name = "Позиция КП"
        verbose_name_plural = "Позиции КП"
