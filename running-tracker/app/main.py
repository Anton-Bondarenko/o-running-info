import os
import datetime
from typing import List, Optional

import bleach
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db, init_db
from app.models import Athlete, Training, calculate_dispensary_status
from app.schemas import (
    AthleteCreate,
    AthleteResponse,
    AthleteUpdate,
    TrainingCreate,
    TrainingResponse,
)

app = FastAPI(title="Running Tracker API")

templates = Jinja2Templates(directory="app/templates")


ALLOWED_TAGS = ["b", "i", "u", "s", "em", "strong", "mark", "font", "span", "marquee"]
ALLOWED_ATTRS = {"font": ["color", "face", "size"], "span": ["class"]}


def sanitize_name(raw_name: str) -> str:
    """Очистка имени спортсмена от опасного HTML."""
    return bleach.clean(raw_name, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


@app.on_event("startup")
def startup():
    init_db()
    seed_if_empty()


def seed_if_empty():
    """Сеeding тестовыми данными, если база пуста (для отладки)."""
    pass  # Этот метод будет заполнен на Этапе 2


# ==================== ATHLETES ====================

@app.get("/api/athletes", response_model=List[dict])
def get_athletes(year: Optional[int] = None, db: Session = Depends(get_db)):
    athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
    result = []
    for a in athletes:
        status = calculate_dispensary_status(a.dispensary_date)
        yearly_km = 0.0
        if year is not None:
            start = datetime.date(year, 1, 1)
            end = datetime.date(year, 12, 31)
            trainings = (
                db.query(Training.distance_km)
                .filter(
                    Training.athlete_id == a.id,
                    Training.date >= start,
                    Training.date <= end,
                )
                .all()
            )
            yearly_km = sum(t[0] for t in trainings) if trainings else 0.0
        result.append({
            "id": a.id,
            "full_name": a.full_name,
            "rank": a.rank,
            "rusada_status": a.rusada_status,
            "dispensary_date": a.dispensary_date.isoformat() if a.dispensary_date else None,
            "dispensary_status": status,
            "clinic_status": a.clinic_status,
            "is_active": a.is_active,
            "yearly_km": yearly_km,
        })
    return result


@app.post("/api/athletes", response_model=AthleteResponse)
def create_athlete(data: AthleteCreate, db: Session = Depends(get_db)):
    clean_name = sanitize_name(data.full_name)
    athlete = Athlete(
        full_name=clean_name,
        rank=data.rank,
        rusada_status=data.rusada_status,
        dispensary_date=data.dispensary_date,
        clinic_status=data.clinic_status or "Не надо",
        is_active=data.is_active,
    )
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    return athlete


@app.put("/api/athletes/{athlete_id}", response_model=AthleteResponse)
def update_athlete(athlete_id: int, data: AthleteUpdate, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    update_dict = data.model_dump(exclude_unset=True)
    if "full_name" in update_dict and update_dict["full_name"] is not None:
        update_dict["full_name"] = sanitize_name(update_dict["full_name"])

    for key, value in update_dict.items():
        setattr(athlete, key, value)

    db.commit()
    db.refresh(athlete)
    return athlete


@app.delete("/api/athletes/{athlete_id}")
def delete_athlete(athlete_id: int, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    db.delete(athlete)
    db.commit()
    return {"detail": f"Спортсмен {athlete_id} удалён"}


# ==================== TRAININGS ====================

@app.post("/api/trainings", response_model=TrainingResponse)
def upsert_training(data: TrainingCreate, db: Session = Depends(get_db)):
    existing = (
        db.query(Training)
        .filter(Training.athlete_id == data.athlete_id, Training.date == data.date)
        .first()
    )
    if existing:
        existing.distance_km = data.distance_km
        db.commit()
        db.refresh(existing)
        return existing

    training = Training(
        athlete_id=data.athlete_id,
        date=data.date,
        distance_km=data.distance_km,
    )
    db.add(training)
    db.commit()
    db.refresh(training)
    return training


# ==================== HEALTH CHECK ====================

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
