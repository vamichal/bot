from django.db import models


class Item(models.Model):
    name = models.CharField("Наименование", max_length=200)
    price_per_day = models.DecimalField("Цена за сутки", max_digits=10, decimal_places=2)
    is_available = models.BooleanField("Доступен", default=True)

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_DONE = "done"
    STATUS_CHOICES = [
        (STATUS_NEW, "Новая"),
        (STATUS_DONE, "Обработана"),
    ]

    client_name = models.CharField("Имя клиента", max_length=200)
    phone = models.CharField("Телефон", max_length=20)
    item = models.ForeignKey(Item, on_delete=models.PROTECT, verbose_name="Товар")
    days = models.PositiveIntegerField("Срок аренды, дней")
    total_price = models.DecimalField("Итоговая цена", max_digits=12, decimal_places=2)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    def __str__(self):
        return f"{self.client_name} — {self.item.name} ({self.created_at:%d.%m.%Y})"
