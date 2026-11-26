# Деплой running-tracker в продакшен

## Стек
**Docker Compose** на Raspberry Pi 4 (raspinas). Данные хранятся на отдельном диске по UUID.

## Файлы деплоя

- `.env` — путь к данным + параметры сервера (**обязательно содержит DEPLOY_USER и DEPLOY_PASSWORD**)
- `Dockerfile` — образ Python 3.11-slim
- `docker-compose.yml` — сервис + persistent volumes
- `.claude/skills/deploy-to-production.md` — навык для AI-агента по деплою

## Инфраструктура

| Компонент | Значение |
|-----------|----------|
| Хост | raspinas (192.168.2.149) |
| Пользователь SSH | claude |
| Данные | `/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data` |
| Приложение | `.../data/o-running-info/running-tracker/` |
| База данных | `.../data/running-tracker-data/tracker.db` |

## Быстрый старт

### Первичный деплой (на свежий сервер)

См. `.claude/skills/deploy-to-production.md` — полный гайд по загрузке файлов и запуску.

### Инкрементальный деплой (после изменений в коде)

> **Важно:** все скрипты используют переменные из `.env`. Никогда не хардкодь логин/пароль!

```powershell
# 1. Убедись, что .env содержит DEPLOY_USER и DEPLOY_PASSWORD
# 2. Запусти деплой через docker-build.ps1 (он загрузит файлы и пересоберет образ)
.\.claude\scripts\docker-build.ps1 -Rebuild
```

Или вручную через plink (замени переменные на значения из .env):

```bash
# Пересобрать контейнер
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cd %REMOTE_APP_DIR% && docker compose up -d --build 2>&1"

# Проверить логи
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "docker logs --tail 20 running-tracker"

# Проверить доступность
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "curl -s http://localhost:8000 | head -c 300"
```

### AI-агент

Вызови навык `/deploy-to-production` — он проведет через весь процесс деплоя.

## Переменные окружения (.env)

| Variable | Описание | Default |
|----------|----------|---------|
| `DEPLOY_HOST` | Хост сервера | `raspinas` |
| `DEPLOY_USER` | Логин SSH | **обязательно** (извлекай из .env, не хардкодь) |
| `DEPLOY_PASSWORD` | Пароль SSH | **обязательно** (извлекай из .env, не хардкодь) |
| `SSH_PORT` | Порт SSH | `22` |
| `PROD_DATA_DIR` | Путь к данным на RasPi | `/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data` |
| `REMOTE_DB_DIR` | Папка с БД | `${PROD_DATA_DIR}/running-tracker-data` |
| `REMOTE_DATABASE_URL` | URL SQLite | авто из DB_DIR |
| `SERVER_HOST` | Слушать адрес | `0.0.0.0` |
| `SERVER_PORT` | Порт | `8000` |
| `WORKERS` | Кол-во воркеров | `1` |

## Данные

База данных SQLite хранится в volume mount на диске с UUID `86f96d82-ed9f-446e-851c-e27448c041eb`. При удалении контейнера данные сохраняются.

## Доступ

http://raspinas:8000 или http://192.168.2.149:8000
