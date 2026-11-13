#!/bin/sh
# Точка входа контейнера: миграции -> статика -> бот (фоном) -> веб (foreground).
set -e

cd "$(dirname "$0")"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# На пустой базе наполняем справочник оборудования из фикстуры: FTP с
# ночной выгрузкой находится во внутренней сети и из контейнера недоступен.
python manage.py seed_equipment

# База на постоянном томе создаётся пустой, а шелла в контейнере нет —
# заводим администратора из переменных окружения. Проверяем наличие явно:
# createsuperuser --noinput падает и когда юзер есть, и когда не задан
# DJANGO_SUPERUSER_EMAIL, а различать эти случаи в логах важно.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -v 0 -c '
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
if User.objects.filter(username=username).exists():
    print(f"Суперпользователь {username} уже есть")
else:
    User.objects.create_superuser(
        username,
        os.environ.get("DJANGO_SUPERUSER_EMAIL", ""),
        os.environ["DJANGO_SUPERUSER_PASSWORD"],
    )
    print(f"Создан суперпользователь {username}")
'
fi

# Long polling живёт в отдельном процессе: gunicorn может иметь несколько
# воркеров, а опрашивать MAX должен ровно один процесс.
# Если бот падает — поднимаем заново, не роняя веб.
(
  while true; do
    python manage.py runbot || echo "runbot упал, перезапуск через 5с"
    sleep 5
  done
) &

# Памяти на тарифе мало, а процесс бота уже занимает один интерпретатор.
# Поэтому один воркер вместо двух, параллелизм — потоками (статику админки
# whitenoise отдаёт через воркер, и в один поток страница грузилась бы
# последовательно). --preload загружает Django в мастере до fork, так что
# воркер наследует его страницы, а не выделяет свои.
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:5000 \
  --workers 1 \
  --threads 4 \
  --preload \
  --timeout 120 \
  --max-requests 500 \
  --max-requests-jitter 50 \
  --access-logfile - \
  --error-logfile -
