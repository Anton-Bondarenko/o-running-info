---
name: restart-server
description: Перезапуск FastAPI/Uvicorn сервера в PowerShell с проверкой что порт свободен
trigger: manual
---

# Перезапуск сервера FoxTrace

## Что делать

При вызове этого навыка выполни следующие шаги в PowerShell:

### 1. Остановка всех процессов на порту 8000

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }; Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Seconds 2
```

### 2. Запуск сервера в фоне

```powershell
cd E:/git/o-running-info/running-tracker; uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Или через `run_in_background` если используешь Agent tool:
- `command`: `cd E:/git/o-running-info/running-tracker && uvicorn app.main:app --host 0.0.0.0 --port 8000`
- `run_in_background`: true

### 3. Проверка что сервер запустился

Посмотри на вывод сервера — должно быть:
```
INFO:     Started server process [...]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 4. Проверка что эндпоинт отвечает

```powershell
curl -s "http://localhost:8000/" | Select-String "FoxTrace"
```

Должно вернуть HTML с текстом "FoxTrace".

## Когда использовать

- После изменений в коде которые требуют перезапуска сервера
- По запросу пользователя "перезапусти сервер"
- Если сервер упал или перестал отвечать
- Перед проверкой приложения в браузере
