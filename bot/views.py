from django.db import connection
from django.http import HttpResponse, JsonResponse


def health(request):
    """Проверка живости для прокси Amvera и для глаз: видно, что контейнер
    отвечает и что база на постоянном томе читается."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        db_ok = True
    except Exception as exc:  # noqa: BLE001 — любую ошибку показываем как есть
        db_ok = False
        db_error = str(exc)

    payload = {"status": "ok" if db_ok else "degraded", "database": db_ok}
    if not db_ok:
        payload["database_error"] = db_error
    return JsonResponse(payload, status=200 if db_ok else 503)


def index(request):
    return HttpResponse(
        "Бот аренды работает. Админка: <a href='/admin/'>/admin/</a>",
        content_type="text/html; charset=utf-8",
    )
