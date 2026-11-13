from django.db import models


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
