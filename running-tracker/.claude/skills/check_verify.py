import asyncio
from playwright.async_api import async_playwright
import os
import sys
import datetime

URL = "http://localhost:8001"
SCREENSHOT_DIR = r"E:\git\o-running-info\running-tracker\test-screenshots"

sys.stdout.reconfigure(encoding='utf-8')

async def verify_delete_buttons():
    print(f"\n=== Verify Delete Buttons at {datetime.datetime.now().strftime('%H:%M:%S')} ===")
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})

        # Go to homepage
        print("\n--- Opening homepage ---")
        await page.goto(URL)
        await page.wait_for_timeout(2000)
        title = await page.title()
        print(f"  Title: {title}")
        await page.screenshot(path=f"{SCREENSHOT_DIR}/v01-homepage.png")
        print("  [OK] v01-homepage.png")

        # Open modal for athlete 7, January (has 3 trainings)
        print("\n--- Opening training modal (athlete 7, January 2026) ---")
        await page.evaluate('''() => { openTrainingsModal(1, 7); }''')
        await page.wait_for_timeout(2000)

        # Check content
        content_html = await page.locator('#trainings-month-content').inner_html()
        has_delete = 'deleteTraining' in content_html and '&times;' in content_html
        print(f"  Content contains delete button: {has_delete}")

        # Count training items
        li_count = await page.locator('#trainings-month-content li[data-training-id]').count()
        print(f"  Training items: {li_count}")

        # Count delete buttons
        btn_count = await page.locator('#trainings-month-content button[onclick*="deleteTraining"]').count()
        print(f"\n  >>> DELETE BUTTONS FOUND: {btn_count}")

        if btn_count > 0:
            for i in range(btn_count):
                li = page.locator('#trainings-month-content li[data-training-id]').nth(i)
                date_text = await li.locator('span').first.inner_text()
                km_span = li.locator('span').nth(1)
                km_text = await km_span.inner_text() if await km_span.count() > 0 else '?'

                btn = page.locator('#trainings-month-content button[onclick*="deleteTraining"]').nth(i)
                visible = await btn.is_visible()
                color = await btn.evaluate("el => window.getComputedStyle(el).color")

                print(f"    Button {i+1}: date={date_text}, km={km_text}, visible={visible}, color={color}")

            # Take screenshot with delete buttons highlighted
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v02-delete-visible.png")
            print("  [OK] v02-delete-visible.png - delete buttons present!")

            # Hover over first button to show hover state
            btn = page.locator('#trainings-month-content button[onclick*="deleteTraining"]').first
            bbox = await btn.bounding_box()
            if bbox:
                mid_x = bbox['x'] + bbox['width'] / 2
                mid_y = bbox['y'] + bbox['height'] / 2
                await page.mouse.move(mid_x, mid_y)
                await page.wait_for_timeout(500)

                hover_color = await btn.evaluate("el => window.getComputedStyle(el).color")
                print(f"\n  Hover color (red-400 -> red-600): {hover_color}")

            await page.screenshot(path=f"{SCREENSHOT_DIR}/v03-delete-hover.png")
            print("  [OK] v03-delete-hover.png - delete button on hover")
        else:
            print("  [FAIL] No delete buttons found!")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v04-no-delete.png")

        # Close modal and verify it closes properly
        await page.evaluate('''() => { closeTrainingsModal(); }''')
        await page.wait_for_timeout(500)

        modal_hidden = await page.locator('#trainings-month-modal').evaluate("el => window.getComputedStyle(el).display === 'none' || window.getComputedStyle(el).classList.contains('hidden')")
        print(f"\n  Modal closed: {modal_hidden}")

        # Final screenshot
        await page.screenshot(path=f"{SCREENSHOT_DIR}/v99-final.png")
        print("  [OK] v99-final.png")

        await browser.close()
        print("\n=== VERIFICATION COMPLETED SUCCESSFULLY ===\n" if btn_count > 0 else "\n=== VERIFICATION FAILED ===\n")

asyncio.run(verify_delete_buttons())
