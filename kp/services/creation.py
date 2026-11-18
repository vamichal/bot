"""Сохранение собранного в боте КП и выгрузка его в .docx."""

from django.db import IntegrityError, transaction
from django.db.models import Max

from kp.models import KP, KPEquipment, KPItem
from kp.services.document import build_context, build_filename, render

# Номер выдаётся как max+1, и при гонке двух сохранений второе упрётся в
# unique. Процесс бота один, так что это страховка, а не рабочий путь.
NUMBER_ATTEMPTS = 5


def next_sequence_number() -> int:
    return (KP.objects.aggregate(last=Max("sequence_number"))["last"] or 0) + 1


def create_kp(*, shortname, address, landlord, items, author_user_id=None, author_name="", rent_day=None):
    """Сохраняет КП и его позиции.

    items — [{"equipment_id": int, "quantity": int}]. Параметры оборудования
    копируются в позицию: документ не должен меняться вслед за ночной выгрузкой.
    """

    equipment_by_id = KPEquipment.objects.in_bulk([item["equipment_id"] for item in items])

    for attempt in range(NUMBER_ATTEMPTS):
        try:
            with transaction.atomic():
                kp = KP(
                    sequence_number=next_sequence_number(),
                    shortname=shortname,
                    address=address,
                    landlord=landlord,
                    author_user_id=author_user_id,
                    author_name=author_name,
                )
                if rent_day is not None:
                    kp.rent_day = rent_day
                kp.save()

                KPItem.objects.bulk_create(
                    [
                        KPItem(
                            kp=kp,
                            equipment=equipment_by_id[item["equipment_id"]],
                            name=equipment_by_id[item["equipment_id"]].name,
                            price=equipment_by_id[item["equipment_id"]].price,
                            weight=equipment_by_id[item["equipment_id"]].weight,
                            space=equipment_by_id[item["equipment_id"]].space,
                            volume=equipment_by_id[item["equipment_id"]].volume,
                            quantity=item["quantity"],
                        )
                        for item in items
                    ]
                )

                return kp
        except IntegrityError:
            if attempt == NUMBER_ATTEMPTS - 1:
                raise

    raise AssertionError("недостижимо")


def build_document(kp: KP) -> tuple[bytes, str]:
    """Готовый .docx и имя файла для отправки в чат."""

    items = [
        {
            "name": item.name,
            "quantity": item.quantity,
            "price": item.price,
            "weight": item.weight,
            "space": item.space,
            "volume": item.volume,
        }
        for item in kp.items.all()
    ]

    context = build_context(
        shortname=kp.shortname,
        address=kp.address,
        sequence_number=kp.sequence_number,
        date_created=kp.date_created,
        items=items,
        rent_day=kp.rent_day,
        security_payment_percent=kp.security_payment_percent,
    )

    return render(context, kp.landlord), build_filename(kp.shortname, kp.sequence_number)
