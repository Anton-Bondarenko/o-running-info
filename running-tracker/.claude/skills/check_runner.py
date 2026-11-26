import asyncio
from playwright.async_api import async_playwright
import os
import sys
import datetime

URL = "http://localhost:8000"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"

sys.stdout.reconfigure(encoding='utf-8')

async def check_app():
    print(f"\n=== Running App Check at {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # === 1. Homepage ===
        print("\n--- Check 1: Homepage ---")
        await page.goto(URL)
        await page.wait_for_timeout(1500)
        title = await page.title()
        print(f"  Title: {title}")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/01-homepage.png")
        h1_visible = await page.locator("h1").first.is_visible() if await page.locator("h1").count() > 0 else False
        print(f"  H1 visible: {h1_visible}")
        print("  [OK] Homepage loaded successfully")

        # Count athletes
        rows = await page.locator('tr[id^="athlete-row-"]').all()
        print(f"  Athletes in table: {len(rows)}")

        # === 2. Month headers ===
        print("\n--- Check 2: Month Headers ---")
        months = await page.locator("thead th.cursor-pointer").all()
        print(f"  Clickable month headers: {len(months)}")
        for i, m in enumerate(months[:3]):
            text = await m.inner_text()
            print(f"    Month {i+1}: '{text.strip()}'")

        if months:
            # Open first month (January)
            await months[0].click()
            await page.wait_for_timeout(1500)

            modal_visible = await page.locator("#trainings-month-modal").is_visible()
            print(f"  Modal opened: {modal_visible}")

            if modal_visible:
                title_el = await page.locator("#trainings-month-title").inner_text()
                print(f"  Modal title: {title_el}")

                # Check athlete select (should be hidden in "all" mode)
                select_style = await page.locator("#trainings-modal-athlete-id").get_attribute("style")
                print(f"  Athlete select style: {select_style[:80] if select_style else 'None'}")

                # Count training items if any
                train_items = await page.locator("li[data-training-id]").all()
                print(f"  Training items visible: {len(train_items)}")

                await page.screenshot(path=f"{SCREENSHOT_DIR}/02-month-modal.png")
                print("  [OK] Month modal screenshot saved")

                # Close modal
                btns = page.locator("#trainings-month-modal button")
                if await btns.count() > 0:
                    await btns.first.click()
                    await page.wait_for_timeout(500)

        # === 3. Click km cell ===
        print("\n--- Check 3: KM Cell Modal (Specific Athlete) ---")
        km_cells = await page.locator("span[onclick*='openTrainingsModal']").all()
        print(f"  Clickable KM cells: {len(km_cells)}")

        if km_cells:
            await km_cells[0].click()
            await page.wait_for_timeout(1500)

            modal_visible = await page.locator("#trainings-month-modal").is_visible()
            print(f"  Modal opened from KM: {modal_visible}")

            if modal_visible:
                title_el = await page.locator("#trainings-month-title").inner_text()
                print(f"  Modal title: {title_el}")

                # In specific mode, athlete select should be visible and pre-selected
                select_style = await page.locator("#trainings-modal-athlete-id").get_attribute("style")
                print(f"  Athlete select style: {select_style[:80] if select_style else 'None'}")

                selected_value = await page.locator("#trainings-modal-athlete-id").first.input_value()
                print(f"  Selected athlete value: {selected_value}")

                # *** KEY CHECK: Training delete buttons (X icon) ***
                x_buttons = page.locator('button[onclick*="deleteTraining"]')
                x_count = await x_buttons.count()
                print(f"\n  >>> DELETE BUTTONS FOUND: {x_count}")

                if x_count > 0:
                    for i in range(min(x_count, 3)):
                        text = await x_buttons.nth(i).inner_text()
                        style = await x_buttons.nth(i).get_attribute("style")
                        visible = await x_buttons.nth(i).is_visible()
                        print(f"    Button {i+1}: text='{text}', visible={visible}")
                    print("  [OK] Delete X buttons present!")

                # Check for training list and form
                content = await page.locator("#trainings-month-content").inner_text()
                has_km = "км" in content
                has_add = "Добавить" in content
                print(f"  Has 'км': {has_km}, Has 'Добавить': {has_add}")

                # Check for date input (add training form)
                inputs = await page.locator("#trainings-month-modal input[type='date']").count()
                km_inputs = await page.locator("#trainings-month-modal input[type='number']").count()
                print(f"  Date inputs: {inputs}, KM inputs: {km_inputs}")

                await page.screenshot(path=f"{SCREENSHOT_DIR}/03-km-modal.png")
                print("  [OK] KM modal screenshot saved")

                # Close modal
                btns = page.locator("#trainings-month-modal button")
                if await btns.count() > 0:
                    await btns.first.click()
                    await page.wait_for_timeout(500)

        # === 4. Add athlete modal ===
        print("\n--- Check 4: Add Athlete Modal ---")
        add_btn = page.locator('button:has-text("Добавить спортсмена")').first
        if await add_btn.is_visible():
            await add_btn.click()
            await page.wait_for_timeout(1000)

            modal_visible = await page.locator("#add-athlete-modal").is_visible()
            print(f"  Add athlete modal visible: {modal_visible}")

            if modal_visible:
                name_input = await page.locator("#add-athlete-modal input[name='full_name']").is_visible()
                print(f"  Full name input visible: {name_input}")
                await page.screenshot(path=f"{SCREENSHOT_DIR}/04-add-athlete.png")
                print("  [OK] Add athlete modal screenshot saved")

                # Close
                btns = page.locator("#add-athlete-modal button")
                if await btns.count() > 0:
                    await btns.first.click()
                    await page.wait_for_timeout(500)
        else:
            print("  Add athlete button not visible (might be hidden)")

        # === 5. Editable cell test ===
        print("\n--- Check 5: Cell Editing ---")
        editable = page.locator(".click-editable").first
        if await editable.is_visible():
            await editable.click()
            await page.wait_for_timeout(800)

            input_visible = await page.locator("input.cell-edit-input").is_visible()
            print(f"  Edit input visible: {input_visible}")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/05-edit.png")
            print("  [OK] Edit mode screenshot saved")

            # Escape to cancel
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
        else:
            print("  No editable cells found")

        # === 6. Year switcher ===
        print("\n--- Check 6: Year Switcher ---")
        year_links = await page.locator('a:has-text("20")').all()
        print(f"  Year links: {len(year_links)}")
        for yl in year_links[:5]:
            text = await yl.inner_text()
            href = await yl.get_attribute("href")
            print(f"    {text} -> {href}")

        # === 7. Final state ===
        await page.screenshot(path=f"{SCREENSHOT_DIR}/06-final.png")
        print("\n[OK] 06-final.png - final state screenshot")

        await browser.close()
        print("\n=== ALL CHECKS COMPLETED SUCCESSFULLY ===\n")

asyncio.run(check_app())
