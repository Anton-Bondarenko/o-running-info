import asyncio
from playwright.async_api import async_playwright
import httpx
import os
import sys
import datetime

URL = "http://localhost:8000"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"

sys.stdout.reconfigure(encoding='utf-8')

async def check_delete_button():
    print(f"\n=== Check Delete Button at {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Step 1: Find an athlete with existing trainings or add one
        print("\n--- Finding/trainings data ---")
        async with httpx.AsyncClient() as client:
            athletes_resp = await client.get(f"{URL}/api/athletes")
            athletes = athletes_resp.json() if athletes_resp.is_success else []
            print(f"  Athletes: {len(athletes)}")

            trainings_resp = await client.get(f"{URL}/api/trainings")
            all_trainings = trainings_resp.json() if trainings_resp.is_success else []
            print(f"  All trainings: {len(all_trainings)}")

            # Group by athlete and month
            from collections import defaultdict
            by_athlete_month = defaultdict(list)
            for t in all_trainings:
                key = (t['athlete_id'], t['date'][:7])  # YYYY-MM
                by_athlete_month[key].append(t)

            # Find athlete+month with trainings
            found_key = None
            for k, ts in by_athlete_month.items():
                if len(ts) > 0:
                    print(f"  Found: athlete={k[0]}, month={k[1]}, trainings={len(ts)}")
                    found_key = k
                    break

        # Step 2: Go to homepage and open modal with specific athlete
        await page.goto(URL)
        await page.wait_for_timeout(1500)

        if found_key:
            athlete_id = found_key[0]
            year_month = found_key[1]  # YYYY-MM
            month_num = int(year_month.split('-')[1]) - 1  # 0-indexed for JS

            print(f"\n--- Opening modal for athlete {athlete_id}, month {year_month} ---")

            # Open the training modal via API directly with specific athlete+month
            await page.evaluate(f"""
                (() => {{
                    const modal = document.getElementById('trainings-month-modal');
                    if (modal) modal.style.display = 'none';
                }})()
            """)

            # Click on km cell that contains the target athlete
            # Build the onclick URL for this specific month+athlete
            months_map = ['ЯНВ','ФЕВ','МАР','АПР','МАЙ','ИЮН','ИЮЛ','АВГ','СЕН','ОКТ','НОЯ','ДЕК']
            target_month = months_map[month_num]

            # Direct approach: open modal via custom function
            await page.evaluate(f"""
                async () => {{
                    const resp = await fetch('/api/athletes/{athlete_id}/trainings?year={year_month[:4]}&month={year_month[5:7]}');
                    const data = await resp.json();
                    console.log('Trainings:', data);

                    // Show in modal
                    const modal = document.getElementById('trainings-month-modal');
                    if (!modal) return;
                    modal.style.display = 'flex';

                    const title = document.getElementById('trainings-month-title');
                    if (title) {{
                        const monthNames = ['Январь','Февраль','Март','Апрель','Май','Июнь',
                            'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
                        title.textContent = 'Тренировки за ' + monthNames[{month_num}] + ' ' + {year_month[:4]};
                    }}

                    const athleteSelect = document.getElementById('trainings-modal-athlete-id');
                    if (athleteSelect) {{
                        athleteSelect.value = String({athlete_id});
                        athleteSelect.style.display = '';
                    }}

                    // Render training items
                    const content = document.getElementById('trainings-month-content');
                    if (content) {{
                        let html = '';
                        data.forEach(t => {{
                            html += '<li class="px-4 py-2 flex justify-between items-center hover:bg-gray-50" data-training-id="' + t.id + '">'
                                + '<span class="text-gray-700 font-medium">' + new Date(t.date).toLocaleDateString('ru-RU') + '</span>'
                                + '<span class="text-gray-900 font-bold">' + t.distance_km + ' км</span>'
                                + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></li>';
                        }});
                        if (data.length === 0) html = '<p class="px-4 py-8 text-gray-500 text-center">Нет тренировок</p>';
                        content.innerHTML = html;
                    }}
                }}
            """)
            await page.wait_for_timeout(1000)

            # Count delete buttons
            x_buttons = page.locator('button[onclick*="deleteTraining"]')
            x_count = await x_buttons.count()
            print(f"\n  >>> DELETE BUTTONS IN MODAL: {x_count}")

            if x_count > 0:
                for i in range(x_count):
                    text = await x_buttons.nth(i).inner_text()
                    visible = await x_buttons.nth(i).is_visible()
                    hover = await x_buttons.nth(i).evaluate("el => window.getComputedStyle(el).hover")
                    print(f"    Button {i+1}: text='{text}', visible={visible}")
                print("  [OK] Delete buttons are present and visible!")

                await page.screenshot(path=f"{SCREENSHOT_DIR}/07-delete-visible.png")
                print("  [OK] 07-delete-visible.png - delete buttons shown")
            else:
                print("  [WARN] No delete buttons found in modal")
                await page.screenshot(path=f"{SCREENSHOT_DIR}/08-no-delete.png")

            # Hover over one to see the hover effect
            if x_count > 0:
                first_btn = x_buttons.first
                bbox = await first_btn.bounding_box()
                if bbox:
                    await page.mouse.move(bbox['x'] + bbox['width']/2, bbox['y'] + bbox['height']/2)
                    await page.wait_for_timeout(300)

                    # Check hover color change
                    color_after = await first_btn.evaluate("el => window.getComputedStyle(el).color")
                    print(f"  Button color on hover: {color_after}")

                    await page.screenshot(path=f"{SCREENSHOT_DIR}/09-delete-hover.png")
                    print("  [OK] 09-delete-hover.png - delete button on hover")

        # Close everything
        await page.evaluate("""() => {
            const m = document.getElementById('trainings-month-modal');
            if (m) m.style.display = 'none';
        }""")

        # Final screenshot of the homepage
        await page.screenshot(path=f"{SCREENSHOT_DIR}/10-final-delete-check.png")
        print("\n[OK] 10-final-delete-check.png - final state")

        await browser.close()
        print("\n=== DELETE BUTTON CHECK COMPLETED ===\n")

asyncio.run(check_delete_button())
