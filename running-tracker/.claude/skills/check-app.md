---
name: check-app
description: Полная проверка приложения: перезапуск сервера, запуск браузера через Playwright, выполнение сценариев и скриншоты
trigger: manual
---

# Проверка приложения FoxTrace

## Что делать

При вызове этого навыка выполни以下步骤 комплексную проверку. Если пользователь указал конкретные действия — делай их. Если нет — проверь базовый функционал по умолчанию.

## Базовые проверки (по умолчанию)

1. Открытие главной страницы
2. Проверка что таблица спортсменов отображается корректно
3. Проверка кликабельных заголовков месяцев
4. Проверка редактирования поля ФИО
5. Проверка модалки добавления спортсмена
6. Скриншоты каждого этапа
7. Исправлять если проверки провалены

## Шаги выполнения

### 0. Перезапуск сервера (если нужен)

Сначала проверь что сервер запущен:
```powershell
curl -s "http://localhost:8000/" | Out-Null; if ($LASTEXITCODE -ne 0 -or (curl -s "http://localhost:8000/" | Select-String "FoxTrace" | Measure-Object).Count -eq 0) { Write-Host "Сервер не отвечает, перезапускаю..." }
```

Если сервер не работает — останови и запусти:
```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }; Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep -Seconds 2
cd E:/git/o-running-info/running-tracker; uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Дождись готовности сервера (3 секунды).

### 1. Установка Playwright (если не установлен)

Проверь установку:
```powershell
python -c "import playwright" 2>&1; if ($LASTEXITCODE -ne 0) { pip install playwright; python -m playwright install chromium }
```

Если браузеры не установлены:
```powershell
python -m playwright install --with-deps chromium
```

### 2. Создание и запуск тестового скрипта Playwright

Создай временный Python-файл с проверками и запусти его:

```python
import asyncio
from playwright.async_api import async_playwright
import os
import datetime

URL = "http://localhost:8000"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"

async def check_app():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        
        # === Проверка 1: Главная страница ===
        print("\n=== Проверка 1: Главная страница ===")
        await page.goto(URL)
        await page.wait_for_timeout(1000)  # Ждем загрузку HTMX
        
        title_exists = await page.locator("h1:has-text('FoxTrace')").is_visible()
        await page.screenshot(path=f"{SCREENSHOT_DIR}/01-homepage.png")
        print(f"Title 'FoxTrace' visible: {title_exists}")
        
        # Проверка что есть таблица
        table_exists = await page.locator("table").is_visible()
        print(f"Table exists: {table_exists}")
        
        # === Проверка 2: Таблица спортсменов ===
        print("\n=== Проверка 2: Таблица спортсменов ===")
        rows = await page.locator("tr[id^='athlete-row-']").all()
        print(f"Спортсменов в таблице: {len(rows)}")
        
        if len(rows) > 0:
            first_name = await page.locator("tr[id^='athlete-row-'] td:nth-child(2)").first().inner_text()
            print(f"Первый спортсмен: {first_name}")
        
        await page.screenshot(path=f"{SCREENSHOT_DIR}/02-table.png")
        
        # === Проверка 3: Кликабельные заголовки месяцев ===
        print("\n=== Проверка 3: Заголовки месяцев ===")
        month_headers = await page.locator("thead th[title='Нажмите для просмотра тренировок']").all()
        print(f"Кликабельных заголовков месяцев: {len(month_headers)}")
        
        if len(month_headers) > 0:
            text = await month_headers[0].inner_text()
            print(f"Первый месяц: {text}")
        
        await page.screenshot(path=f"{SCREENSHOT_DIR}/03-months.png")
        
        # === Проверка 4: Клик по месяцу (открытие модалки) ===
        print("\n=== Проверка 4: Модалка тренировок ===")
        if len(month_headers) > 0:
            await month_headers[2].click()  # Клик на Март
            await page.wait_for_timeout(500)
            
            modal_visible = await page.locator("#trainings-month-modal").is_visible()
            print(f"Модалка тренировок открыта: {modal_visible}")
            
            if modal_visible:
                modal_title = await page.locator("#trainings-month-title").inner_text()
                print(f"Заголовок модалки: {modal_title}")
                
                # Проверяем что есть селект спортсмена
                athlete_select = await page.locator("#trainings-modal-athlete-id").is_visible()
                print(f"Селект спортсмена в модалке: {athlete_select}")
            
            await page.screenshot(path=f"{SCREENSHOT_DIR}/04-modal.png")
            
            # Закрываем модалку
            await page.locator("#trainings-month-modal button").first().click()
            await page.wait_for_timeout(300)

        # === Проверка 5: Клик по км (открытие модалки с конкретным спортсменом) ===
        print("\n=== Проверка 5: Клик по километражу ===")
        km_cells = await page.locator("span[onclick*='openTrainingsModal']").all()
        print(f"Кликабельных ячеек км: {len(km_cells)}")
        
        if len(km_cells) > 0:
            first_km = await km_cells[0].inner_text()
            await km_cells[0].click()
            await page.wait_for_timeout(500)
            
            modal_title = await page.locator("#trainings-month-title").inner_text()
            print(f"Заголовок модалки: {modal_title}")
            
            # Проверяем что выбран нужный спортсмен
            selected_athlete = await page.locator("#trainings-modal-athlete-id").input_value()
            print(f"Выбранный athlete_id: {selected_athlete}")
            
            await page.screenshot(path=f"{SCREENSHOT_DIR}/05-km-modal.png")
            
            # Закрываем модалку
            await page.locator("#trainings-month-modal button").first().click()
            await page.wait_for_timeout(300)

        # === Проверка 6: Редактирование поля ===
        print("\n=== Проверка 6: Редактирование ячейки ===")
        editable = await page.locator(".click-editable").first()
        await editable.click()
        await page.wait_for_timeout(500)
        
        input_visible = await page.locator("input.cell-edit-input").first().is_visible()
        print(f"Режим редактирования активирован: {input_visible}")
        
        if input_visible:
            await page.screenshot(path=f"{SCREENSHOT_DIR}/06-edit.png")
            
            # Нажимаем Escape чтобы отменить
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)

        # === Проверка 7: Модалка добавления спортсмена ===
        print("\n=== Проверка 7: Добавление спортсмена ===")
        add_btn = await page.locator("button:has-text('Добавить спортсмена')").first()
        await add_btn.click()
        await page.wait_for_timeout(500)
        
        modal_open = await page.locator("#add-athlete-modal").is_visible()
        print(f"Модалка добавления открыта: {modal_open}")
        
        if modal_open:
            name_input = await page.locator("#add-athlete-modal input[name='full_name']").is_visible()
            print(f"Поле ФИО в модалке: {name_input}")
            
            await page.screenshot(path=f"{SCREENSHOT_DIR}/07-add-modal.png")
            
            # Закрываем
            await page.locator("#add-athlete-modal button").first().click()
            await page.wait_for_timeout(300)

        # === Проверка 8: Переключение года ===
        print("\n=== Проверка 8: Переключение года ===")
        year_links = await page.locator("a[href^='/']:has-text('20')").all()
        print(f"Ссылок на год: {len(year_links)}")
        
        if len(year_links) > 1:
            second_year = await year_links[1].inner_text()
            href = await year_links[1].get_attribute("href")
            print(f"Второй год: {second_year}, ссылка: {href}")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/08-year-switch.png")

        await browser.close()
        
        print("\n=== ИТОГ: Все проверки завершены ===")

asyncio.run(check_app())
```

### 3. Запуск скрипта

```powershell
cd E:/git/o-running-info/running-tracker; python test_check.py
```

Скрипт создаст скриншоты в `test-screenshots/`:
- `01-homepage.png` — главная страница
- `02-table.png` — таблица спортсменов
- `03-months.png` — кликабельные месяцы
- `04-modal.png` — модалка тренировок (из заголовка)
- `05-km-modal.png` — модалка из ячейки км
- `06-edit.png` — режим редактирования ячейки
- `07-add-modal.png` — модалка добавления спортсмена
- `08-year-switch.png` — переключение года

### 4. Просмотр результатов

Покажи пользователю скриншоты и вывод консоли:
```powershell
Get-ChildItem test-screenshots/*.png | Select-Object Name, @{N='Size';E={'{0:N2}' -f ($_.Length/1KB)} KB}
```

## Пользовательские сценарии

Если пользователь указал конкретные действия — адаптируй скрипт:

### "Проверь добавление спортсмена"
Добавь в тест:
```python
# В модалку ввода ФИО
await page.locator("#add-athlete-modal input[name='full_name']").fill("Тест Спортсмен")
await page.locator("#add-athlete-modal button[type='submit']").click()
await page.wait_for_timeout(1000)
# Проверь что появилась строка с новым спортсменом
new_athlete = await page.locator("td:has-text('Тест Спортсмен')").first().is_visible()
```

### "Проверь редактирование ФИО"
```python
editable = await page.locator(".click-editable td:nth-child(2)").first()
await editable.click()
await page.wait_for_timeout(500)
input_el = await page.locator("input.cell-edit-input").first()
await input_el.fill("Новое Имя ⚡")
await page.keyboard.press("Escape")  # Или Enter для сохранения
```

### "Проверь добавление тренировки"
```python
# Клик по модалке тренировки
await page.locator("button:has-text('Тренировка')").click()
await page.wait_for_timeout(500)
# Заполняй форму и проверяй результат
```

### "Проверь РУСАДА переключение"
```python
rusada_btn = await page.locator("button[onclick*='toggleRusada']").first()
status_before = await rusada_btn.inner_text()
await rusada_btn.click()
await page.wait_for_timeout(1000)
status_after = await rusada_btn.inner_text()
```

## Что проверять по умолчанию

- [x] Главная страница загружается и отображает "FoxTrace"
- [x] Таблица с спортсменами рендерится
- [x] Заголовки месяцев кликабельны (hover, cursor-pointer)
- [x] Ячейки с км кликабельны
- [x] Модалка тренировок открывается и содержит селект + список + форму
- [x] Селект спортсмена популирован из таблицы
- [x] Клик по км открывает модалку с авто-селектом конкретного спортсмена
- [x] Редактирование ячейки (клик → input → Escape/Enter)
- [x] Модалка добавления спортсмена
- [x] Переключение года работает

## Если что-то не так

1. Покажи скриншот с ошибкой
2. Опиши что пошло не так
3. Проверь логи сервера на наличие ошибок
4. Запусти `pytest` для регрессии: `cd E:/git/o-running-info/running-tracker && python -m pytest tests/ -x -v`

## Команды быстрого доступа

```powershell
# Остановить сервер
Get-Process uvicorn -ErrorAction SilentlyContinue | Stop-Process -Force

# Перезапустить сервер
cd E:/git/o-running-info/running-tracker; uvicorn app.main:app --host 0.0.0.0 --port 8000

# Запустить тесты
cd E:/git/o-running-info/running-tracker && python -m pytest tests/ -x -v

# Посмотреть логи сервера в реальном времени
Get-Content test-screenshots/*.png  # (скриншоты), или watch server output
```
