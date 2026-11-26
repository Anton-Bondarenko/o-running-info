import httpx
import asyncio
import datetime
import sys
sys.stdout.reconfigure(encoding='utf-8')

URL = "http://localhost:8000"

async def add_test_data():
    async with httpx.AsyncClient() as client:
        # Get athletes
        resp = await client.get(f"{URL}/api/athletes")
        athletes = resp.json() if resp.is_success else []
        print(f"Athletes before: {len(athletes)}")

        # Add trainings for athlete 7 (the one that exists)
        today = datetime.date.today()
        year = today.year
        month = today.month

        added = 0
        for day in [5, 12, 20]:
            try:
                training_data = {
                    "athlete_id": athletes[0]["id"] if athletes else None,
                    "date": f"{year}-{month:02d}-{day:02d}",
                    "distance_km": 10.5 + added
                }
                r = await client.post(f"{URL}/api/trainings", json=training_data)
                if r.is_success:
                    print(f"  Added training: {r.json()}")
                    added += 1
                else:
                    print(f"  Failed to add: {r.status_code} {r.text[:200]}")
            except Exception as e:
                print(f"  Error adding: {e}")

        # Verify
        tr_resp = await client.get(f"{URL}/api/trainings")
        all_t = tr_resp.json() if tr_resp.is_success else []
        print(f"\nTrainings after: {len(all_t)}")

        # Also add another athlete if none exist
        if not athletes:
            new_athlete = {"full_name": "Тест Спортсмен 1", "notes": ""}
            r = await client.post(f"{URL}/api/athletes", json=new_athlete)
            if r.is_success:
                print(f"Added athlete: {r.json()}")

asyncio.run(add_test_data())
