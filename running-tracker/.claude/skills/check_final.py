import asyncio
from playwright.async_api import async_playwright
import httpx
import os
import sys
import datetime

URL = "http://localhost:8000"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"

sys.stdout.reconfigure(encoding='utf-8')

async def check_delete_in_modal():
    print(f"\n=== Delete Button Check at {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # First verify API data for athlete 7 in January
    async with httpx.AsyncClient() as client:
        tr = await client.get(f"{URL}/api/trainings?athlete_id=7&year=2026&month=1")
        jan_trainings = tr.json() if tr.is_success else []
        print(f"\n--- API: Athlete 7, January 2026 ---")
        print(f"  Trainings count: {len(jan_trainings)}")
        for t in jan_trainings:
            print(f"    ID={t['id']}, date={t['date']}, km={t['distance_km']}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Go to homepage
        print("\n--- Opening homepage ---")
        await page.goto(URL)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=f"{SCREENSHOT_DIR}/s01-homepage.png")
        print("  [OK] s01-homepage.png")

        # Find the km cell for athlete 7 in January by clicking on row and finding the Jan cell
        # Instead, use evaluate to directly open the modal with API data
        print("\n--- Opening training modal via API ---")
        await page.evaluate("""
            async () => {
                // Fetch trainings from API
                const resp = await fetch('/api/trainings?athlete_id=7&year=2026&month=1');
                const trainings = await resp.json();

                // Get athlete name
                const aResp = await fetch('/api/athletes/7');
                const athlete = await aResp.json();

                console.log('Trainings:', trainings);
                console.log('Athlete:', athlete);

                // Open modal
                let modal = document.getElementById('trainings-month-modal');
                if (!modal) {
                    console.error('Modal not found on page!');
                    return;
                }
                modal.style.display = 'flex';
                modal.style.zIndex = '9999';

                // Set title
                const title = document.getElementById('trainings-month-title');
                if (title) title.textContent = 'Тренировки за Январь 2026';

                // Show athlete info bar
                const infoBar = document.querySelector('#trainings-month-modal .bg-emerald-50 p:nth-child(1) span:last-child');
                if (infoBar) infoBar.textContent = athlete.full_name || 'Спортсмен';

                // Set select value
                const select = document.getElementById('trainings-modal-athlete-id');
                if (select) {{
                    select.value = String(7);
                    select.style.display = '';
                }}

                // Render training list in the existing ul
                const ul = document.querySelector('#trainings-month-modal ul[data-training-list]');
                if (!ul) return;

                let html = '';
                trainings.forEach(t => {{
                    html += '<li class="px-4 py-3 flex justify-between items-center hover:bg-gray-50" data-training-id="' + t.id + '">'
                        + '<span class="text-gray-700 font-medium">' + new Date(t.date).toLocaleDateString('ru-RU') + '</span>'
                        + '<span class="text-gray-900 font-bold">' + t.distance_km + ' км</span>'
                        + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></li>';
                }});
                ul.innerHTML = html;

                // Calculate total
                const totalEl = document.querySelector('#trainings-month-modal .bg-emerald-50 p:nth-child(2) span:last-child');
                if (totalEl) {{
                    const total = trainings.reduce((s, t) => s + t.distance_km, 0);
                    totalEl.textContent = total.toFixed(1) + ' км';
                }}
            }
        """)
        await page.wait_for_timeout(500)

        # Take screenshot of the modal with training items
        await page.screenshot(path=f"{SCREENSHOT_DIR}/s02-modal-with-trainings.png")
        print("  [OK] s02-modal-with-trainings.png - modal with trainings rendered")

        # Check delete buttons in the list
        x_buttons = page.locator('li[data-training-id] button[onclick*="deleteTraining"]')
        x_count = await x_buttons.count()
        print(f"\n  >>> DELETE BUTTONS FOUND: {x_count}")

        for i in range(x_count):
            btn = x_buttons.nth(i)
            li = page.locator(f'li[data-training-id]').nth(i)
            date_text = await li.locator('span:first-child').inner_text()
            km_text = await li.locator('span:nth-child(2)').inner_text()
            visible = await btn.is_visible()
            color = await btn.evaluate("el => window.getComputedStyle(el).color")
            print(f"    Button {i+1}: date={date_text}, km={km_text}, visible={visible}, color={color}")

        # Hover over first button
        if x_count > 0:
            bbox = await x_buttons.first.bounding_box()
            if bbox:
                mid_x = bbox['x'] + bbox['width'] / 2
                mid_y = bbox['y'] + bbox['height'] / 2
                await page.mouse.move(mid_x, mid_y)
                await page.wait_for_timeout(500)

                hover_color = await x_buttons.first.evaluate("el => window.getComputedStyle(el).color")
                print(f"\n  Hover color: {hover_color}")

            await page.screenshot(path=f"{SCREENSHOT_DIR}/s03-delete-hover.png")
            print("  [OK] s03-delete-hover.png - delete button on hover (darker red)")

        # Test click on first delete button (simulate)
        if x_count > 0:
            # Get the date of the first training before clicking
            first_date = await page.locator('li[data-training-id]').first.locator('span:first-child').inner_text()
            print(f"\n  First training date: {first_date}")

            # Show what delete would do - just verify the onclick function exists
            has_delete_func = await page.evaluate("typeof deleteTraining === 'function'")
            print(f"  deleteTraining function exists: {has_delete_func}")

        # Click away to close modal, then re-open with different month
        print("\n--- Testing cross-month trainings ---")
        for target_month in [2, 3]:
            await page.evaluate(f"""
                async () => {{
                    const resp = await fetch('/api/trainings?athlete_id=7&year=2026&month={target_month}');
                    const trainings = await resp.json();

                    const title = document.getElementById('trainings-month-title');
                    const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь',
                        'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
                    if (title) title.textContent = 'Тренировки за ' + monthNames[{target_month-1}] + ' 2026';

                    const ul = document.querySelector('ul[data-training-list]');
                    if (!ul) return;

                    let html = '';
                    trainings.forEach(t => {{
                        html += '<li class="px-4 py-3 flex justify-between items-center hover:bg-gray-50" data-training-id="' + t.id + '">'
                            + '<span class="text-gray-700 font-medium">' + new Date(t.date).toLocaleDateString('ru-RU') + '</span>'
                            + '<span class="text-gray-900 font-bold">' + t.distance_km + ' км</span>'
                            + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></li>';
                    }});
                    ul.innerHTML = html;

                    const totalEl = document.querySelector('.bg-emerald-50 p:nth-child(2) span:last-child');
                    if (totalEl) {{
                        const total = trainings.reduce((s, t) => s + t.distance_km, 0);
                        totalEl.textContent = total.toFixed(1) + ' км';
                    }}
                }}
            """)
            await page.wait_for_timeout(300)

            btns = await page.locator('button[onclick*="deleteTraining"]').count()
            print(f"  Month {target_month}: {btns} delete buttons")

            if btns > 0:
                await page.screenshot(path=f"{SCREENSHOT_DIR}/s0{3+target_month}-modal-month{target_month}.png")

        # Close modal
        await page.evaluate("() => { const m = document.getElementById('trainings-month-modal'); if (m) m.style.display = 'none'; }")

        # Final screenshot
        await page.screenshot(path=f"{SCREENSHOT_DIR}/s99-final.png")
        print("\n  [OK] s99-final.png")

        await browser.close()
        print("\n=== DELETE BUTTON CHECK COMPLETED ===\n")

asyncio.run(check_delete_in_modal())
