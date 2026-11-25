# Этап 3: Упаковка в Docker и подготовка к деплою

## Цель этапа
Настроить сборку Docker-образа, совместимого с Raspberry Pi 4 (ARM64), обеспечить сохранность базы данных SQLite при перезапуске контейнера и проверить сборку.

## Требования к Docker (`Dockerfile` и `docker-compose.yml`)
1. **`Dockerfile`**:
   - Используй легкий базовый образ: `python:3.11-slim`.
   - Установи рабочую директорию `/app`.
   - Сначала скопируй `requirements.txt` и выполни `pip install --no-cache-dir -r requirements.txt` (для кэширования слоев).
   - Скопируй папку `app/`.
   - Укажи команду запуска: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.

2. **`docker-compose.yml`**:
   - Сервис `web`:
     - `build: .`
     - `container_name: running-tracker`
     - `restart: unless-stopped` (чтобы приложение само поднималось после перезагрузки Raspberry Pi).
     - `ports: - "8000:8000"`
     - `volumes: - ./data:/app/data` (критически важно для сохранения файла `tracker.db` на хосте).

3. **Файл `.dockerignore`**:
   - Исключи `__pycache__`, `*.pyc`, `.pytest_cache`, `tests/`, `data/`, `.git`.

## Задачи для выполнения
1. Создай `Dockerfile`, `docker-compose.yml` и `.dockerignore`.
2. Создай `README.md` с краткой инструкцией: как запустить локально, как запустить тесты и как развернуть на Raspberry Pi 4.
3. Проверь сборку и запуск контейнера (если Docker доступен в окружении агента):
   - Выполни `docker compose build`.
   - Запусти контейнер в фоне `docker compose up -d`.
   - Проверь через `curl -I http://localhost:8000`, что сервер отвечает `200 OK`.
   - Останови контейнер `docker compose down`.
