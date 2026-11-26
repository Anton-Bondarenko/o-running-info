---
name: deploy-to-production
description: Деплой running-tracker на Raspberry Pi через Docker Compose (plink + docker compose)
trigger: manual
---

# Деплой running-tracker в продакшен на RasPi

## Что делать

При вызове этого навыка выполни следующие шаги:

### Предварительное условие

Убедись, что все файлы приложения готовы к деплою (код, шаблоны, static, fonts, requirements.txt, .env).

> **ВАЖНО:** Все скрипты должны использовать переменные из `.env`. Никогда не хардкодь логин/пароль!

---

## Вариант 1: Полная первичная загрузка (если файлы ещё не на сервере)

### 1. Создать структуру каталогов на сервере

Прочитай `.env`, извлеки `DEPLOY_USER`, `DEPLOY_PASSWORD`, `DEPLOY_HOST`, `SSH_PORT`. Используй их через plink:

```powershell
# Загрузи переменные из .env
$env:DEPLOY_USER = "..."  # прочитай из .env
$env:DEPLOY_PASSWORD = "..."  # прочитай из .env

plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "mkdir -p /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker"
```

### 2. Загрузить .env и docker-compose.yml

Используй `.claude/scripts/docker-build.ps1` или загрузи файлы вручную через plink с переменными из .env:

```powershell
# docker-compose.yml для загрузки
$composeYml = @"
services:
  running-tracker:
    build: .
    container_name: running-tracker
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ${PROD_DATA_DIR}/running-tracker-data:/app/data
      - ./.env:/app/.env:ro
    env_file:
      - .env
    environment:
      - SERVER_HOST=0.0.0.0
      - SERVER_PORT=8000
      - WORKERS=1
"@

plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cat > /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker/docker-compose.yml" << 'HEREDOC'
$composeYml
HEREDOC
```

### 3. Загрузить остальные файлы по частям

Каждый файл — через `plink` с heredoc или base64 для бинарных файлов (шрифты, JS).

---

## Вариант 2: Инкрементальный деплой (наиболее частый сценарий)

### 1. Убедиться что файлы на сервере

Скопировать изменённые файлы локально на сервер:

```powershell
# Загрузи переменные из .env
$env:DEPLOY_USER = "..."  # прочитай из .env
$env:DEPLOY_PASSWORD = "..."  # прочитай из .env

# Загружаем все Python-файлы
Get-ChildItem -Recurse -Filter "*.py" | ForEach-Object {
    $rel = $_.FullName.Replace((Get-Location).Path, '') -replace '\\', '/'
    $dest = "/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker$rel"
    $content = Get-Content $_.FullName -Raw
    plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cat > $dest" | Write-Output $content
}

# Шрифты (бинарные, через base64)
Get-ChildItem app/static/fonts/*.ttf | ForEach-Object {
    $rel = $_.FullName.Replace((Get-Location).Path, '') -replace '\\', '/'
    $dest = "/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker$rel"
    $b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($_.FullName))
    plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "echo $b64 | base64 -d > $dest"
}

# Шаблонные файлы
Get-ChildItem app/templates/**/*.html app/static/**/*.js app/static/**/*.css | ForEach-Object {
    $rel = $_.FullName.Replace((Get-Location).Path, '') -replace '\\', '/'
    $dest = "/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker$rel"
    $content = Get-Content $_.FullName -Raw
    plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cat > $dest" | Write-Output $content
}

# requirements.txt отдельно
cp requirements.txt /tmp/rt-requirements.txt
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cat > /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker/requirements.txt" << 'EOF'
$(Get-Content requirements.txt -Raw)
EOF
```

### 2. Пересобрать и перезапустить контейнер

```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cd /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker && docker compose up -d --build 2>&1"
```

### 3. Дождаться запуска и проверить логи

```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "docker logs --tail 20 running-tracker"
```

Ожидаемый вывод:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Проверить доступность HTTP

```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "curl -s http://localhost:8000 | head -c 300"
```

Должен вернуться HTML с заголовком и содержимым приложения.

### 5. Проверить что БД работает

```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "curl -s http://localhost:8000/api/athletes"
```

Должен вернуться JSON (пустой массив или список спортсменов).

---

## Полезные команды

### Логи контейнера
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "docker logs -f running-tracker"
```

### Остановить контейнер
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cd /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker && docker compose down"
```

### Удалить контейнер и образ (полный сброс)
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cd /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker && docker compose down -rmi"
```

### Перезапустить контейнер (без пере сборки)
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "cd /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker && docker compose restart"
```

### Проверить что файлы на сервере
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "ls -la /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker/"
```

### Проверить размер данных на диске
```bash
plink -P %SSH_PORT% -pw '%DEPLOY_PASSWORD%' %DEPLOY_USER%@raspinas "du -sh /srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data/o-running-info/running-tracker/"
```

---

## Переменные окружения (для справки)

| Variable | Значение на сервере |
|----------|-------------------|
| `PROD_DATA_DIR` | `/srv/dev-disk-by-uuid-86f96d82-ed9f-446e-851c-e27448c041eb/data` |
| `REMOTE_DB_DIR` | `${PROD_DATA_DIR}/running-tracker-data` |
| `SERVER_HOST` | `0.0.0.0` |
| `SERVER_PORT` | `8000` |
| `WORKERS` | `1` |

## Доступ после деплоя

http://raspinas:8000 или http://192.168.2.149:8000
