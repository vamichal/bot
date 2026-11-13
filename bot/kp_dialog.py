"""Диалог сборки коммерческого предложения.

Позиций в справочнике несколько сотен, списком в чат они не влезают,
поэтому выбор идёт либо по группам с постраничной выдачей, либо поиском
по названию — на шаге выбора любой текст считается поисковым запросом.
"""

import logging
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import close_old_connections

from maxapi import F, Router
from maxapi.context import MemoryContext, State, StatesGroup
from maxapi.enums.intent import Intent
from maxapi.enums.upload_type import UploadType
from maxapi.types import Command, MessageCallback, MessageCreated
from maxapi.types.attachments import ButtonsPayload, CallbackButton, InputMediaBuffer

from kp.models import KPEquipment
from kp.services.creation import build_document, create_kp
from kp.services.document import IRS, LANDLORD_CHOICES, NIKONOV, TemplateBusinessError, alphabetical
from kp.services.formatting import format_money

logger = logging.getLogger(__name__)

router = Router()

PAGE_SIZE = 8
# Длинные названия в кнопке всё равно обрезаются клиентом — режем сами,
# чтобы видеть предсказуемый результат.
BUTTON_TEXT_LIMIT = 40
# Защита от опечатки вроде лишнего нуля, а заодно от переполнения колонки.
MAX_QUANTITY = 100_000


class KPForm(StatesGroup):
    shortname = State()
    address = State()
    landlord = State()
    picking = State()
    quantity = State()


# --- доступ к базе -----------------------------------------------------
# Django ORM синхронный, поэтому каждый запрос уходит в поток.


@sync_to_async
def load_groups() -> list[str]:
    close_old_connections()
    groups = KPEquipment.objects.filter(is_active=True).exclude(group="").values_list("group", flat=True)
    return sorted(set(groups), key=alphabetical)


def _as_dicts(queryset) -> list[dict]:
    return [{"id": item.id, "name": item.name, "price": item.price} for item in queryset]


@sync_to_async
def load_page(group: str, page: int) -> tuple[list[dict], int]:
    close_old_connections()
    found = KPEquipment.objects.filter(is_active=True, group=group)
    start = page * PAGE_SIZE
    return _as_dicts(found[start : start + PAGE_SIZE]), found.count()


@sync_to_async
def search(query: str) -> list[dict]:
    """Поиск по части названия.

    Фильтруем в Python, а не через icontains: LIKE в SQLite игнорирует
    регистр только у латиницы, поэтому «балка» не нашла бы «Балка». Позиций
    несколько сотен, так что перебор дешевле, чем возня с коллациями, и
    заодно не зависит от того, на какой базе мы окажемся.
    """

    close_old_connections()
    needle = alphabetical(query)
    found = [item for item in KPEquipment.objects.filter(is_active=True) if needle in alphabetical(item.name)]
    return _as_dicts(found[:PAGE_SIZE])


@sync_to_async
def load_equipment(equipment_id: int) -> dict | None:
    close_old_connections()
    found = KPEquipment.objects.filter(id=equipment_id).first()
    return {"id": found.id, "name": found.name, "price": found.price} if found else None


@sync_to_async
def save_and_render(data: dict, user_id: int | None) -> tuple[bytes, str, int]:
    close_old_connections()
    kp = create_kp(
        shortname=data["shortname"],
        address=data["address"],
        landlord=data["landlord"],
        items=data["items"],
        author_user_id=user_id,
    )
    raw, filename = build_document(kp)
    return raw, filename, kp.sequence_number


# --- клавиатуры --------------------------------------------------------


def keyboard(rows: list[list[CallbackButton]]):
    return ButtonsPayload(buttons=rows).pack()


def button(text: str, payload: str, intent: Intent = Intent.DEFAULT) -> CallbackButton:
    return CallbackButton(text=text[:BUTTON_TEXT_LIMIT], payload=payload, intent=intent)


def landlord_keyboard():
    return keyboard([[button(title, f"ll:{code}")] for code, title in LANDLORD_CHOICES])


def groups_keyboard(groups: list[str], *, has_items: bool):
    rows = [[button(name, f"g:{index}:0")] for index, name in enumerate(groups)]
    rows.append(finish_row(has_items=has_items))
    return keyboard(rows)


def page_keyboard(items: list[dict], group_index: int, page: int, total: int, *, has_items: bool):
    rows = [[button(item["name"], f"e:{item['id']}")] for item in items]

    navigation = []
    if page > 0:
        navigation.append(button("← Назад", f"g:{group_index}:{page - 1}"))
    if (page + 1) * PAGE_SIZE < total:
        navigation.append(button("Вперёд →", f"g:{group_index}:{page + 1}"))
    if navigation:
        rows.append(navigation)

    rows.append([button("К группам", "groups")])
    rows.append(finish_row(has_items=has_items))
    return keyboard(rows)


def found_keyboard(items: list[dict], *, has_items: bool):
    rows = [[button(item["name"], f"e:{item['id']}")] for item in items]
    rows.append([button("К группам", "groups")])
    rows.append(finish_row(has_items=has_items))
    return keyboard(rows)


def finish_row(*, has_items: bool) -> list[CallbackButton]:
    row = [button("Отменить", "cancel", Intent.NEGATIVE)]
    if has_items:
        row.insert(0, button("Готово, собрать КП", "done", Intent.POSITIVE))
    return row


# --- тексты ------------------------------------------------------------


def attachment_name(filename: str) -> str:
    """Имя для вложения — без расширения.

    maxapi при загрузке приписывает к имени расширение, угаданное по
    содержимому файла, не проверяя, есть ли оно уже. С готовым именем
    в чат приходило «КП-1.docx.docx».
    """

    return Path(filename).stem


def author_title(user) -> str:
    """Как подписать автора КП в уведомлении менеджерам.

    Ник есть не у всех, поэтому в запасе остаётся числовой id: по нему
    человека можно найти, даже если он не завёл username.
    """

    if user is None:
        return "неизвестно кто"

    name = user.full_name
    return f"{name} (@{user.username})" if user.username else f"{name} (id {user.user_id})"


def managers_message(number: int, data: dict, items: list[dict], user) -> str:
    """Текст уведомления в чат менеджеров."""

    total = sum(item["price"] * item["quantity"] for item in items)
    positions = "\n".join(f"• {item['name']} — {item['quantity']} шт." for item in items)

    return (
        f"🆕 Собрано КП-{number}\n\n"
        f"Получатель: {data['shortname']}\n"
        f"Адрес объекта: {data['address']}\n"
        f"Арендодатель: {dict(LANDLORD_CHOICES)[data['landlord']]}\n\n"
        f"{positions}\n\n"
        f"Сумма набора: {format_money(total)} ₽\n\n"
        f"Собрал в боте: {author_title(user)}"
    )


async def notify_managers(bot, number: int, data: dict, items: list[dict], user, raw: bytes, filename: str) -> None:
    """Дублирует КП в чат менеджеров.

    Молча пропускаем, если чат не настроен, и не роняем диалог, если
    отправка не удалась: пользователь свой файл уже получил, и терять
    его из-за недоступного чата нельзя.
    """

    if not settings.KP_MANAGERS_CHAT_ID:
        return

    try:
        await bot.send_message(
            chat_id=settings.KP_MANAGERS_CHAT_ID,
            text=managers_message(number, data, items, user),
            attachments=[InputMediaBuffer(raw, filename=attachment_name(filename), type=UploadType.FILE)],
        )
    except Exception:
        logger.exception("Не удалось отправить КП-%s в чат менеджеров", number)


def basket(items: list[dict]) -> str:
    """Что уже набрано — показываем после каждого добавления."""

    if not items:
        return "Пока ничего не выбрано."

    lines = [f"• {item['name']} — {item['quantity']} шт." for item in items]
    total = sum(item["price"] * item["quantity"] for item in items)
    return "Набрано:\n" + "\n".join(lines) + f"\n\nСумма набора: {format_money(total)} ₽"


async def show_groups(send, context: MemoryContext, prefix: str = "") -> None:
    data = await context.get_data()
    groups = await load_groups()
    await context.update_data(groups=groups)
    await context.set_state(KPForm.picking)

    text = f"{prefix}Выберите группу оборудования или напишите часть названия для поиска."
    await send(text=text, attachments=[groups_keyboard(groups, has_items=bool(data.get("items")))])


# --- шаги диалога ------------------------------------------------------


@router.message_created(Command("kp"))
async def start(event: MessageCreated, context: MemoryContext):
    await context.clear()
    await context.set_state(KPForm.shortname)
    await event.message.answer(
        "Собираем коммерческое предложение.\n\nШаг 1 из 4. Кому адресовано КП? Напишите название получателя."
    )


@router.message_created(KPForm.shortname)
async def set_shortname(event: MessageCreated, context: MemoryContext):
    value = (event.message.body.text or "").strip()
    if not value:
        await event.message.answer("Название получателя не может быть пустым. Напишите его текстом.")
        return

    await context.update_data(shortname=value, items=[])
    await context.set_state(KPForm.address)
    await event.message.answer("Шаг 2 из 4. Адрес объекта?")


@router.message_created(KPForm.address)
async def set_address(event: MessageCreated, context: MemoryContext):
    value = (event.message.body.text or "").strip()
    if not value:
        await event.message.answer("Адрес не может быть пустым. Напишите его текстом.")
        return

    await context.update_data(address=value)
    await context.set_state(KPForm.landlord)
    await event.message.answer(
        "Шаг 3 из 4. От какого юрлица выставляем? У каждого свой бланк.",
        attachments=[landlord_keyboard()],
    )


@router.message_callback(F.callback.payload.startswith("ll:"), KPForm.landlord)
async def set_landlord(event: MessageCallback, context: MemoryContext):
    code = event.callback.payload.removeprefix("ll:")
    if code not in {IRS, NIKONOV}:
        await event.ack(notification="Неизвестный арендодатель")
        return

    await context.update_data(landlord=code)
    # Уведомление обязательно: MAX отклоняет пустой ответ на нажатие
    # (`message` or `notification` required), и кнопка зависает.
    await event.ack(notification=dict(LANDLORD_CHOICES)[code])
    await show_groups(event.send, context, prefix="Шаг 4 из 4. ")


@router.message_callback(F.callback.payload == "groups", KPForm.picking)
async def back_to_groups(event: MessageCallback, context: MemoryContext):
    data = await context.get_data()
    groups = await load_groups()
    await context.update_data(groups=groups)
    await event.answer(
        new_text="Выберите группу оборудования или напишите часть названия для поиска.",
        attachments=[groups_keyboard(groups, has_items=bool(data.get("items")))],
    )


@router.message_callback(F.callback.payload.startswith("g:"), KPForm.picking)
async def show_page(event: MessageCallback, context: MemoryContext):
    _, raw_index, raw_page = event.callback.payload.split(":")
    index, page = int(raw_index), int(raw_page)

    data = await context.get_data()
    groups = data.get("groups") or await load_groups()
    if index >= len(groups):
        await event.ack(notification="Группа устарела, откройте список заново")
        return

    group = groups[index]
    items, total = await load_page(group, page)
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    await event.answer(
        new_text=f"{group} — позиции {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + len(items)} из {total}"
        f"\nСтраница {page + 1} из {pages}",
        attachments=[page_keyboard(items, index, page, total, has_items=bool(data.get("items")))],
    )


@router.message_callback(F.callback.payload.startswith("e:"), KPForm.picking)
async def pick_equipment(event: MessageCallback, context: MemoryContext):
    equipment_id = int(event.callback.payload.removeprefix("e:"))
    equipment = await load_equipment(equipment_id)
    if equipment is None:
        await event.ack(notification="Позиция не найдена")
        return

    await context.update_data(pending=equipment)
    await context.set_state(KPForm.quantity)
    await event.ack(notification=equipment["name"])
    await event.send(f"{equipment['name']}\nЦена: {format_money(equipment['price'])} ₽\n\nСколько штук?")


@router.message_created(KPForm.quantity)
async def set_quantity(event: MessageCreated, context: MemoryContext):
    value = (event.message.body.text or "").strip()
    if not value.isdigit() or not 0 < int(value) <= MAX_QUANTITY:
        await event.message.answer(f"Нужно целое число от 1 до {MAX_QUANTITY}. Сколько штук?")
        return

    data = await context.get_data()
    equipment = data.get("pending")
    if not equipment:
        await show_groups(event.message.answer, context, prefix="Позиция потерялась, выберите заново. ")
        return

    items = list(data.get("items") or [])
    # Повторный выбор той же позиции заменяет количество, а не задваивает строку.
    items = [item for item in items if item["equipment_id"] != equipment["id"]]
    items.append(
        {
            "equipment_id": equipment["id"],
            "name": equipment["name"],
            "price": equipment["price"],
            "quantity": int(value),
        }
    )
    await context.update_data(items=items, pending=None)

    await show_groups(event.message.answer, context, prefix=f"{basket(items)}\n\n")


@router.message_created(KPForm.picking)
async def search_by_text(event: MessageCreated, context: MemoryContext):
    query = (event.message.body.text or "").strip()
    if len(query) < 2:
        await event.message.answer("Для поиска напишите хотя бы два символа.")
        return

    data = await context.get_data()
    found = await search(query)
    if not found:
        await event.message.answer(f"По запросу «{query}» ничего не нашлось. Попробуйте другое слово.")
        return

    await event.message.answer(
        f"Нашлось по запросу «{query}» (показаны первые {len(found)}):",
        attachments=[found_keyboard(found, has_items=bool(data.get("items")))],
    )


@router.message_callback(F.callback.payload == "cancel")
async def cancel(event: MessageCallback, context: MemoryContext):
    await context.clear()
    await event.answer(new_text="Сборка КП отменена. Начать заново — /kp", attachments=[])


@router.message_callback(F.callback.payload == "done", KPForm.picking)
async def finish(event: MessageCallback, context: MemoryContext):
    data = await context.get_data()
    items = data.get("items") or []
    if not items:
        await event.ack(notification="Сначала добавьте хотя бы одну позицию")
        return

    await event.answer(new_text="Собираю документ…", attachments=[])

    try:
        raw, filename, number = await save_and_render(data, event.callback.user.user_id)
    except TemplateBusinessError as error:
        await event.send(f"Не удалось собрать КП: {error}")
        return
    except Exception:
        logger.exception("Не удалось собрать КП")
        await event.send("Не удалось собрать КП. Попробуйте ещё раз — /kp")
        return

    await context.clear()
    await event.send(
        f"КП-{number} готово.\n\n{basket(items)}",
        attachments=[InputMediaBuffer(raw, filename=attachment_name(filename), type=UploadType.FILE)],
    )

    # После ответа пользователю: его файл не должен зависеть от того,
    # доступен ли чат менеджеров.
    await notify_managers(event.bot, number, data, items, event.callback.user, raw, filename)
