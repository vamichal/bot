#!/bin/sh
# Точка входа контейнера: миграции -> статика -> бот (фоном) -> веб (foreground).
set -e

cd "$(dirname "$0")"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# Long polling живёт в отдельном процессе: gunicorn может иметь несколько
# воркеров, а опрашивать MAX должен ровно один процесс.
# Если бот падает — поднимаем заново, не роняя веб.
(
  while true; do
    python manage.py runbot || echo "runbot упал, перезапуск через 5с"
    sleep 5
  done
) &

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:5000 \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
