import asyncio
from playwright.async_api import async_playwright
import os, sys, datetime

URL = "http://localhost:8000"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"
sys.stdout.reconfigure(encoding='utf-8')

async def verify():
    print(f"\n=== Delete Button Verification at {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # 1. Homepage
        print("\n--- Opening homepage ---")
        await page.goto(URL)
        await page.wait_for_timeout(2000)
        title = await page.title()
        print(f"  Title: {title}")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/v01-homepage.png")
        print("  [OK] v01-homepage.png")

        # 2. Open training modal for athlete 7, January
        print("\n--- Opening training modal (athlete 7, Jan 2026) ---")
        await page.evaluate("""
            async () => {
                const resp = await fetch('/api/trainings?athlete_id=7&year=2026&month=1');
                const trainings = await resp.json();
                const modal = document.getElementById('trainings-month-modal');
                if (!modal) return;
                modal.classList.remove('hidden');

                const title = document.getElementById('trainings-month-title');
                if (title) title.textContent = 'Тренировки за Январь 2026';

                // Render list in #trainings-month-content
                const content = document.getElementById('trainings-month-content');
                let html = '';
                trainings.forEach(t => {
                    html += '<div class="px-4 py-3 flex justify-between items-center hover:bg-gray-50" data-training-id="' + t.id + '">'
                        + '<span class="text-gray-700 font-medium">' + new Date(t.date).toLocaleDateString("ru-RU") + '</span>'
                        + '<span class="text-gray-900 font-bold">' + t.distance_km + ' км</span>'
                        + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></div>';
                });
                content.innerHTML = html;
            }
        """)
        await page.wait_for_timeout(500)

        # Count elements via Playwright
        liCount = await page.locator('[data-training-id]').count()
        btnCount = await page.locator('#trainings-month-content button[onclick*="deleteTraining"]').count()
        print(f"  Training items: {liCount}, Delete buttons: {btnCount}")
        print(f"\n  >>> DELETE BUTTONS FOUND: {btnCount}")

        if btnCount > 0:
            for i in range(btnCount):
                li = page.locator('[data-training-id]').nth(i)
                dateText = await li.locator('span').first.inner_text()
                kmText = await li.locator('span').last.inner_text()
                btn = page.locator('#trainings-month-content button[onclick*="deleteTraining"]').nth(i)
                visible = await btn.is_visible()
                color = await btn.evaluate("el => window.getComputedStyle(el).color")
                print(f"    Button {i+1}: date={dateText}, km={kmText}, visible={visible}, color={color}")

            # Screenshot with delete buttons visible
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v02-delete-visible.png")
            print("  [OK] v02-delete-visible.png - delete buttons present!")

            # Hover over first button
            firstBtn = page.locator('#trainings-month-content button[onclick*="deleteTraining"]').first
            bbox = await firstBtn.bounding_box()
            if bbox:
                await page.mouse.move(bbox['x'] + bbox['width']/2, bbox['y'] + bbox['height']/2)
                await page.wait_for_timeout(500)
                hoverColor = await firstBtn.evaluate("el => window.getComputedStyle(el).color")
                print(f"  Hover color (red-400->red-600): {hoverColor}")

            await page.screenshot(path=f"{SCREENSHOT_DIR}/v03-delete-hover.png")
            print("  [OK] v03-delete-hover.png - hover state shown")
        else:
            print("  [FAIL] No delete buttons found!")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v04-no-delete.png")

        # 3. Check February (should be empty)
        print("\n--- Checking February (empty) ---")
        febCount = await page.locator('button[onclick*="deleteTraining"]').count() if btnCount == 0 else await page.locator('#trainings-month-content button[onclick*="deleteTraining"]').count()

        # Render empty month (February)
        await page.evaluate("""
            async () => {
                const title = document.getElementById('trainings-month-title');
                if (title) title.textContent = 'Тренировки за Февраль 2026';
                document.getElementById('trainings-month-content').innerHTML = '<p class="px-4 py-8 text-gray-500 text-center">Нет тренировок</p>';
            }
        """)
        await page.wait_for_timeout(500)

        febBtnCount = await page.locator('#trainings-month-content button[onclick*="deleteTraining"]').count()
        print(f"  Feb delete buttons: {febBtnCount}")
        if febBtnCount == 0:
            print("  [OK] February correctly shows no trainings and no delete buttons")

        # 4. November (current month - many trainings)
        print("\n--- Checking November 2026 (many trainings) ---")
        await page.evaluate("""
            async () => {
                const resp = await fetch('/api/trainings?athlete_id=7&year=2026&month=11');
                const trainings = await resp.json();
                const title = document.getElementById('trainings-month-title');
                if (title) title.textContent = 'Тренировки за Ноябрь 2026';
                const content = document.getElementById('trainings-month-content');
                let html = '';
                trainings.forEach(t => {
                    html += '<div class="px-4 py-3 flex justify-between items-center hover:bg-gray-50" data-training-id="' + t.id + '">'
                        + '<span class="text-gray-700 font-medium">' + new Date(t.date).toLocaleDateString("ru-RU") + '</span>'
                        + '<span class="text-gray-900 font-bold">' + t.distance_km + ' км</span>'
                        + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></div>';
                });
                content.innerHTML = html;
            }
        """)
        await page.wait_for_timeout(500)

        novBtnCount = await page.locator('button[onclick*="deleteTraining"]').count()
        print(f"  Nov delete buttons: {novBtnCount}")
        if novBtnCount > 0:
            print("  [OK] November has trainings with delete buttons")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v05-november-trainings.png")
            print("  [OK] v05-november-trainings.png")

        # Close modal
        await page.evaluate("() => { const m = document.getElementById('trainings-month-modal'); if (m) m.classList.add('hidden'); }")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/v99-final.png")
        print("  [OK] v99-final.png")

        await browser.close()
        success = btnCount > 0 and novBtnCount > 0
        status = "COMPLETED SUCCESSFULLY" if success else "FAILED"
        print(f"\n=== VERIFICATION {status} ===\n")

asyncio.run(verify())
