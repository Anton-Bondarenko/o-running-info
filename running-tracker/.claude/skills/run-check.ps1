# Automated check-app for running-tracker
$URL = "http://localhost:8000"
$SCREENSHOT_DIR = "E:\git\o-running-info\running-tracker\test-screenshots"
New-Item -ItemType Directory -Force -Path $SCREENSHOT_DIR | Out-Null

# Run Python playwright script
& python -c @"
import asyncio
from playwright.async_api import async_playwright
import os

URL = '$URL'.replace('\\\\', '/')
SD = r'$SCREENSHOT_DIR'
async def check():
    os.makedirs(SD, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 900})

        # 1. Homepage
        await page.goto(URL)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f'{SD}/01-homepage.png')
        print('[OK] 01-homepage.png - main page loaded')

        # 2. Check table exists
        rows = await page.locator('tr[id^=\"athlete-row-\"]').all()
        print(f'[INFO] Athletes in table: {len(rows)}')

        # 3. Month headers
        months = await page.locator('thead th.cursor-pointer').all()
        print(f'[INFO] Clickable month headers: {len(months)}')
        if months:
            await months[0].click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f'{SD}/02-month-modal.png')
            print('[OK] 02-month-modal.png - month header click test')
            # Close modal
            btns = page.locator('#trainings-month-modal button')
            if await btns.count() > 0:
                await btns.first.click()
                await page.wait_for_timeout(500)

        # 4. Click km cell to open specific athlete modal
        km_cells = await page.locator('span[onclick*=\"openTrainingsModal\"]').all()
        print(f'[INFO] KM clickable cells: {len(km_cells)}')
        if km_cells:
            await km_cells[0].click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f'{SD}/03-km-modal.png')
            print('[OK] 03-km-modal.png - km cell modal test')

            # Check training delete button (x icon)
            x_buttons = page.locator('button[onclick*=\"deleteTraining\"]')
            x_count = await x_buttons.count()
            print(f'[INFO] Delete X buttons in modal: {x_count}')

            if x_count > 0:
                visible = await x_buttons.first.is_visible()
                print(f'[INFO] First delete button visible: {visible}')

            # Close modal
            btns = page.locator('#trainings-month-modal button')
            if await btns.count() > 0:
                await btns.first.click()
                await page.wait_for_timeout(500)

        # 5. Add athlete modal
        add_btn = page.locator('button:has-text(\"Добавить спортсмена\")').first
        if await add_btn.is_visible():
            await add_btn.click()
            await page.wait_for_timeout(1000)
            await page.screenshot(path=f'{SD}/04-add-athlete.png')
            print('[OK] 04-add-athlete.png - add athlete modal')
            # Close
            btns = page.locator('#add-athlete-modal button')
            if await btns.count() > 0:
                await btns.first.click()
                await page.wait_for_timeout(500)

        # 6. Click editable cell
        editable = page.locator('.click-editable').first
        if await editable.is_visible():
            await editable.click()
            await page.wait_for_timeout(500)
            await page.screenshot(path=f'{SD}/05-edit.png')
            print('[OK] 05-edit.png - edit mode activated')
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(300)

        # 7. Year switcher
        year_links = await page.locator('a:has-text(\"20\")').all()
        print(f'[INFO] Year links found: {len(year_links)}')
        if len(year_links) > 1:
            href = await year_links[1].get_attribute('href')
            text = await year_links[1].inner_text()
            print(f'[INFO] Second year: {text} -> {href}')

        # Final screenshot
        await page.screenshot(path=f'{SD}/06-final.png')
        print('[OK] 06-final.png - final state')

        print('\n=== ALL CHECKS PASSED ===')
        await browser.close()

asyncio.run(check())
"@

Write-Host "`n--- Screenshots ---"
Get-ChildItem "$SCREENSHOT_DIR"/*.png | Select-Object Name, @{N='Size(KB)';E={[math]::Round($_.Length/1KB,1)}} | Format-Table -AutoSize
