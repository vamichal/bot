#!/bin/sh
# Точка входа контейнера: подготовка -> бот (фоном) -> веб (foreground).
#
# Всё, что можно, делается за один запуск Django: на четверти ядра каждый
# лишний manage.py — это несколько десятков секунд сплошного троттлинга,
# а пока контейнер ползёт, платформа успевает признать его мёртвым.
set -e

cd "$(dirname "$0")"

python manage.py prepare_app

# Long polling живёт в отдельном процессе: gunicorn может иметь несколько
# воркеров, а опрашивать MAX должен ровно один процесс.
# Если бот падает — поднимаем заново, не роняя веб.
(
  while true; do
    python manage.py runbot || echo "runbot упал, перезапуск через 5с"
    sleep 5
  done
) &

# Один воркер: процесс бота уже занимает интерпретатор, а параллелизм
# веба достаточно обеспечить потоками. --preload загружает Django в
# мастере до fork, так что воркер наследует его страницы.
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
