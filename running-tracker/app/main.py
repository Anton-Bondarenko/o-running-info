import html
import os
import datetime
from typing import List, Optional

import bleach
from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
import jinja2
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import get_db, init_db, SessionLocal
from app.models import Athlete, Training, calculate_dispensary_status
from app.schemas import (
    AthleteCreate,
    AthleteResponse,
    AthleteUpdate,
    TrainingCreate,
    TrainingResponse,
)

# Use jinja2.Environment directly (bypasses Starlette wrapper which crashes
# with cache_size=0 in tests — dict gets passed as template name)
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("app/templates"),
    autoescape=jinja2.select_autoescape(),
    cache_size=0,
)


def render(template_name: str, context: dict) -> HTMLResponse:
    """Render a Jinja2 template and return an HTMLResponse."""
    t = _jinja_env.get_template(template_name)
    rendered_html = t.render(**context)
    return HTMLResponse(content=rendered_html)


app = FastAPI(title="Running Tracker API")

_app_dir = os.path.dirname(__file__)
_static_dir = os.path.join(_app_dir, "static")

if not os.path.isdir(_static_dir):
    raise RuntimeError(f"Static directory not found: {_static_dir}")

app.mount("/static", StaticFiles(directory=_static_dir), name="static")

ALLOWED_TAGS = ["b", "i", "u", "s", "em", "strong", "mark", "font", "span", "marquee"]
ALLOWED_ATTRS = {"font": ["color", "face", "size"], "span": ["class"]}


def sanitize_name(raw_name: str) -> str:
    """Очистка имени спортсмена от опасного HTML."""
    return bleach.clean(raw_name, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


@app.on_event("startup")
def startup():
    init_db()

def seed_if_empty():
    """Заполняем базу тестовыми спортсменами и тренировками, если пуста."""
    from sqlalchemy import inspect
    from app.database import engine

    insp = inspect(engine)
    tables = insp.get_table_names()
    if not tables:
        return  # база только создана, таблицы пустые

    session = SessionLocal()
    count = session.query(Athlete).count()
    if count > 0:
        session.close()
        return

    today = datetime.date.today()
    athletes_data = [
        {
            "full_name": "<b>Иванов</b> Иван Иванович",
            "rank": "КМС",
            "rusada_status": True,
            "dispensary_date": (today + datetime.timedelta(days=180)).isoformat(),
            "clinic_status": "Допущен",
        },
        {
            "full_name": "<span class='text-blue-600'>Петрова</span> Анна Сергеевна",
            "rank": "МС",
            "rusada_status": False,
            "dispensary_date": (today - datetime.timedelta(days=30)).isoformat(),
            "clinic_status": "Не надо",
        },
        {
            "full_name": "<i>Сидоров</i> Пётр Алексеевич",
            "rank": None,
            "rusada_status": True,
            "dispensary_date": (today + datetime.timedelta(days=10)).isoformat(),
            "clinic_status": "На проверке",
        },
    ]

    for adata in athletes_data:
        athlete = Athlete(
            full_name=sanitize_name(adata["full_name"]),
            rank=adata.get("rank"),
            rusada_status=adata.get("rusada_status", False),
            dispensary_date=datetime.date.fromisoformat(adata["dispensary_date"]) if adata.get("dispensary_date") else None,
            clinic_status=adata.get("clinic_status") or "Не надо",
            is_active=True,
        )
        session.add(athlete)
    session.commit()

    # Тренировки для первого спортсмена
    first_athlete = session.query(Athlete).first()
    if first_athlete:
        for month in range(1, 8):
            training = Training(
                athlete_id=first_athlete.id,
                date=datetime.date(today.year, month, 15),
                distance_km=round(40 + month * 5, 1),
            )
            session.add(training)
        # Для второго
        second_athlete = session.query(Athlete).order_by(Athlete.id.desc()).first()
        if second_athlete and second_athlete.id != first_athlete.id:
            for month in range(1, 8):
                training = Training(
                    athlete_id=second_athlete.id,
                    date=datetime.date(today.year, month, 20),
                    distance_km=round(60 + month * 10, 1),
                )
                session.add(training)
    session.commit()
    session.close()


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

@app.get("/api/trainings")
def get_trainings(
    athlete_id: int = Query(...),
    month: Optional[int] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Training).filter(Training.athlete_id == athlete_id)
    if month is not None:
        y = year or datetime.date.today().year
        start = datetime.date(y, month, 1)
        next_month = datetime.date(y, month + 1, 1) if month < 12 else datetime.date(y + 1, 1, 1)
        end = next_month - datetime.timedelta(days=1)
        q = q.filter(Training.date >= start, Training.date <= end)
    trainings = q.order_by(Training.date).all()
    result = []
    for t in trainings:
        result.append({
            "id": t.id,
            "athlete_id": t.athlete_id,
            "date": t.date.isoformat(),
            "distance_km": t.distance_km,
        })
    return result


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


@app.delete("/api/trainings/{training_id}")
def delete_training(training_id: int, db: Session = Depends(get_db)):
    training = db.query(Training).filter(Training.id == training_id).first()
    if not training:
        raise HTTPException(status_code=404, detail="Тренировка не найдена")
    db.delete(training)
    db.commit()
    return {"detail": "deleted"}


# ==================== HEALTH CHECK ====================

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


# ==================== HTML ROUTES (HTMX Frontend) ====================

def _get_monthly_km(athlete_id: int, year: int, db: Session) -> dict:
    """Подсчет ежемесячного объема для спортсмена."""
    monthly = {}
    trainings = (
        db.query(Training.distance_km, Training.date)
        .filter(
            Training.athlete_id == athlete_id,
            Training.date >= datetime.date(year, 1, 1),
            Training.date <= datetime.date(year, 12, 31),
        )
        .all()
    )
    for dist, d in trainings:
        month_key = f"monthly_km_{d.month}"
        monthly[month_key] = monthly.get(month_key, 0) + dist
    return monthly


def _render_athletes_tbody(athletes, target_year: int, current_month: int, db: Session) -> str:
    """Render the full <tbody> HTML for the athletes table."""
    monthly_data = {}
    yearly_totals = {}
    for a in athletes:
        md = _get_monthly_km(a.id, target_year, db)
        mv = list(md.values())
        yearly_totals[a.id] = sum(mv) if mv else 0.0
        monthly_data[a.id] = md

    best_month = None
    for m in range(current_month, 0, -1):
        if any(monthly_data.get(a.id, {}).get(f"monthly_km_{m}", 0) or 0 > 0 for a in athletes):
            best_month = m
            break

    ranked = []
    if best_month:
        for a in athletes:
            km_val = monthly_data.get(a.id, {}).get(f"monthly_km_{best_month}", 0) or 0
            if km_val > 0:
                ranked.append((a.id, km_val))
        ranked.sort(key=lambda x: x[1], reverse=True)

    tmpl = _jinja_env.get_template("partials/athlete_row.html")

    out = []
    for a in athletes:
        status = calculate_dispensary_status(a.dispensary_date)
        row_data = {
            "id": a.id,
            "full_name": a.full_name,
            "rank": a.rank,
            "rusada_status": a.rusada_status,
            "dispensary_date": a.dispensary_date.isoformat() if a.dispensary_date else None,
            "dispensary_status": status,
            "clinic_status": a.clinic_status,
            "is_active": a.is_active,
            "yearly_km": yearly_totals.get(a.id, 0.0),
        }
        for k, v in monthly_data.get(a.id, {}).items():
            row_data[k] = v or 0.0

        month_rank = None
        if best_month and ranked:
            for idx, (aid, km_val) in enumerate(ranked):
                if aid == a.id:
                    if km_val > 0:
                        if idx > 0 and ranked[idx - 1][1] == km_val:
                            month_rank = ranked[idx - 1][2]["month_rank"] if hasattr(ranked[idx - 1][2], 'month_rank') else ranked[idx - 1][0]
                        else:
                            month_rank = idx + 1
                    break

        row_data["month_rank"] = month_rank
        out.append(tmpl.module.render_athlete_row(row_data, target_year))
    return "\n".join(out)


@app.get("/")
async def index(request: Request, year: Optional[int] = None, db: Session = Depends(get_db)):
    if year is None:
        year = datetime.date.today().year
    athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
    today = datetime.date.today()
    current_month = today.month
    athletes_list = []
    for a in athletes:
        status = calculate_dispensary_status(a.dispensary_date)
        monthly_km = _get_monthly_km(a.id, year, db)
        yearly_km = 0.0
        if month_vals := list(monthly_km.values()):
            yearly_km = sum(month_vals)
        athletes_list.append({
            "id": a.id,
            "full_name": a.full_name,
            "rank": a.rank,
            "rusada_status": a.rusada_status,
            "dispensary_date": a.dispensary_date.isoformat() if a.dispensary_date else None,
            "dispensary_status": status,
            "clinic_status": a.clinic_status,
            "is_active": a.is_active,
            "yearly_km": yearly_km,
            **monthly_km,
        })
    # Определяем месяц для отображения места
    best_month = current_month
    for m in range(current_month, 0, -1):
        has_data = any((athletes_list[i].get(f"monthly_km_{m}", 0) or 0) > 0 for i in range(len(athletes_list)))
        if has_data:
            best_month = m
            break
    else:
        best_month = None
    for athlete in athletes_list:
        if best_month is None:
            athlete["month_km"] = 0.0
            athlete["month_rank"] = None
        else:
            athlete["month_km"] = athlete.get(f"monthly_km_{best_month}", 0) or 0.0
    if best_month is not None and any(a["month_km"] > 0 for a in athletes_list):
        ranked = sorted(athletes_list, key=lambda x: x["month_km"] or 0, reverse=True)
        for rank_idx, athlete in enumerate(ranked):
            km_val = athlete.get("month_km") or 0.0
            if km_val == 0:
                athlete["month_rank"] = None
            else:
                if rank_idx > 0 and ranked[rank_idx - 1].get("month_km", 0) == km_val:
                    athlete["month_rank"] = ranked[rank_idx - 1]["month_rank"]
                else:
                    athlete["month_rank"] = rank_idx + 1
    current_year = datetime.date.today().year
    years = list(range(current_year - 2, current_year + 3))
    if year not in years:
        years.insert(0, year)
    years.sort()
    MONTH_NAMES = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    ]
    month_title = "---" if best_month is None else MONTH_NAMES[best_month]
    return render("index.html", {
        "request": request,
        "athletes": athletes_list,
        "selected_year": year,
        "years": years,
        "months": ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"],
        "month_title": month_title,
    })


@app.get("/htmx/athletes-tbody/{year}")
async def htmx_get_athletes_tbody(year: int, db: Session = Depends(get_db)):
    """Возвращает обновлённый tbody с спортсменами (месячные км + итоги)."""
    athletes = db.query(Athlete).filter(Athlete.is_active == True).all()
    current_month = datetime.date.today().month
    rows_html = _render_athletes_tbody(athletes, year, current_month, db)
    return HTMLResponse(content=rows_html)


@app.post("/htmx/athlete")
async def htmx_create_athlete(
        request: Request,
        full_name: str = Form(...),
        rank: Optional[str] = Form(None),
        rusada_status: bool = Form(False),
        dispensary_date: Optional[str] = Form(None),
        clinic_status: Optional[str] = Form(None),
        db: Session = Depends(get_db),
):
    clean_name = sanitize_name(full_name)

    date_val = None
    if dispensary_date:
        try:
            date_val = datetime.date.fromisoformat(dispensary_date)
        except ValueError:
            pass
    athlete = Athlete(
        full_name=clean_name,
        rank=rank or None,
        rusada_status=rusada_status,
        dispensary_date=date_val,
        clinic_status=clinic_status or "Не надо",
        is_active=True,
    )
    db.add(athlete)
    db.commit()
    db.refresh(athlete)
    tmpl = _jinja_env.get_template("partials/athlete_row.html")
    row_html = tmpl.module.render_athlete_row(
        {
            "id": athlete.id,
            "full_name": athlete.full_name,
            "rank": athlete.rank,
            "rusada_status": athlete.rusada_status,
            "dispensary_date": athlete.dispensary_date.isoformat() if athlete.dispensary_date else None,
            "dispensary_status": calculate_dispensary_status(athlete.dispensary_date),
            "clinic_status": athlete.clinic_status,
            "is_active": athlete.is_active,
            "yearly_km": 0.0,
        },
        datetime.date.today().year,
    )
    return HTMLResponse(content=row_html)

@app.delete("/htmx/athlete/{athlete_id}")
async def htmx_delete_athlete(athlete_id: int, request: Request, db: Session = Depends(get_db)):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()

    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    db.delete(athlete)
    db.commit()
    return PlainTextResponse("deleted")

@app.patch("/htmx/athlete/{athlete_id}/cell/{field}")
async def htmx_update_cell(
        athlete_id: int,
        field: str,
        request: Request,
        db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()

    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")
    body = await request.json()
    if field == "full_name":
        value = sanitize_name(body.get("value", ""))
        athlete.full_name = value
        db.commit()
        return HTMLResponse(content=value)
    elif field == "rank":
        value = body.get("value") or None
        athlete.rank = value
    elif field == "dispensary_date":
        raw = body.get("value")
        if raw:
            try:
                date_val = datetime.date.fromisoformat(raw)
                athlete.dispensary_date = date_val
            except ValueError:
                return PlainTextResponse("error", status_code=400)
        else:
            athlete.dispensary_date = None
    elif field == "clinic_status":
        value = body.get("value") or None
        athlete.clinic_status = value
    elif field == "rusada_status":
        value = str(body.get("value", "")).lower() == "true"
        athlete.rusada_status = value
    else:
        raise HTTPException(status_code=400, detail=f"Неизвестное поле: {field}")
    db.commit()
    return PlainTextResponse("updated")

# ==================== TRAININGS BY MONTH ====================

@app.get("/htmx/athlete/{athlete_id}/trainings")
async def htmx_get_month_trainings(
    athlete_id: int,
    request: Request,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(datetime.date.today().year),
    db: Session = Depends(get_db),
):
    """Возвращает HTML со списком тренировок за указанный месяц."""
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    start = datetime.date(year, month, 1)
    next_month = datetime.date(year, month + 1, 1) if month < 12 else datetime.date(year + 1, 1, 1)
    end = next_month - datetime.timedelta(days=1)

    trainings = (
        db.query(Training)
        .filter(
            Training.athlete_id == athlete_id,
            Training.date >= start,
            Training.date <= end,
        )
        .order_by(Training.date)
        .all()
    )

    month_name = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month]

    total_km = sum(t.distance_km for t in trainings)

    tmpl_html = f'''<p class="text-sm text-gray-600 font-semibold">{month_name} {year}</p>
<div class="bg-gray-50 rounded-lg p-3">
    <p class="text-sm text-gray-600">Спортсмен: <span class="font-semibold">{html.escape(athlete.full_name or "")}</span></p>
    <p class="text-sm text-gray-600 mt-1">Всего за месяц: <span class="font-bold text-emerald-700">{total_km:.1f} км</span></p>
</div>
{('<ul class="divide-y divide-gray-200 bg-white rounded-lg shadow-sm">' if trainings else '') + ''.join(
    '<li class="px-4 py-3 flex justify-between items-center hover:bg-gray-50" data-training-id="' + str(t.id) + '">'
    + '<span class="text-gray-700 font-medium">' + t.date.strftime("%d.%m.%Y") + '</span>'
    + '<span class="text-gray-900 font-bold">' + f'{t.distance_km:.1f}' + ' км</span>'
    + '<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button>'
    + '</li>' for t in trainings) + ('</ul>' if trainings else '')}
{('<p class="text-center text-gray-400 py-4">Нет тренировок за этот месяц</p>' if not trainings else '')}
<form onsubmit="addTrainingForMonth(event, {athlete_id}, {year}, {month})" class="flex gap-2 items-end">
    <div class="flex-1">
        <label class="block text-xs font-medium text-gray-600 mb-1">Дата</label>
        <input type="date" id="new-training-date-for-month" required class="w-full border border-gray-300 rounded px-2 py-1 text-sm">
    </div>
    <div class="w-28">
        <label class="block text-xs font-medium text-gray-600 mb-1">Км</label>
        <input type="number" step="0.1" min="0" id="new-training-km-for-month" required placeholder="10.5" class="w-full border border-gray-300 rounded px-2 py-1 text-sm">
    </div>
    <button type="submit" class="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg whitespace-nowrap">Добавить</button>
</form>'''
    return HTMLResponse(content=tmpl_html)


@app.get("/htmx/trainings-all")
async def htmx_get_all_trainings(
    request: Request,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(datetime.date.today().year),
    db: Session = Depends(get_db),
):
    """Возвращает HTML со списком тренировок всех спортсменов за указанный месяц."""
    athletes = db.query(Athlete).order_by(Athlete.id).all()
    month_name = ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
                  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"][month]

    start = datetime.date(year, month, 1)
    next_month = datetime.date(year, month + 1, 1) if month < 12 else datetime.date(year + 1, 1, 1)
    end = next_month - datetime.timedelta(days=1)

    cards = []
    total_all = 0.0
    for athlete in athletes:
        trainings = (
            db.query(Training)
            .filter(
                Training.athlete_id == athlete.id,
                Training.date >= start,
                Training.date <= end,
            )
            .order_by(Training.date)
            .all()
        )
        total_km = sum(t.distance_km for t in trainings)
        total_all += total_km

        name_escaped = html.escape(athlete.full_name or 'Неизвестно')
        training_items = ''.join(
            f'<li class="px-4 py-2 flex justify-between items-center hover:bg-gray-50" data-training-id="{t.id}">'
            f'<span class="text-gray-700 font-medium">{t.date.strftime("%d.%m.%Y")}</span>'
            f'<span class="text-gray-900 font-bold">{t.distance_km:.1f} км</span>'
            f'<button type="button" onclick="deleteTraining(this)" title="Удалить тренировку" class="ml-2 text-red-400 hover:text-red-600 transition">&times;</button></li>'
            for t in trainings
        )

        card = f'''<div class="border border-gray-200 rounded-lg p-3">
    <div class="flex justify-between items-center mb-2">
        <p class="text-sm font-semibold text-gray-800">{name_escaped}</p>
        <p class="text-sm text-emerald-700 font-bold">{total_km:.1f} км</p>
    </div>
    {'<ul class="space-y-1">' + training_items + '</ul>' if trainings else '<p class="text-xs text-gray-400 italic">Нет тренировок</p>'}
    <form onsubmit="addTrainingForMonth(event, {athlete.id}, {year}, {month})" class="mt-2 flex gap-2 items-end">
        <input type="date" id="new-training-date-for-month-{athlete.id}" required
               class="border border-gray-300 rounded px-2 py-1 text-sm w-36"
               name="training_date">
        <input type="number" step="0.1" min="0" id="new-training-km-for-month-{athlete.id}" required placeholder="км"
               class="border border-gray-300 rounded px-2 py-1 text-sm w-20"
               name="training_km">
        <button type="submit" class="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded whitespace-nowrap">Добавить</button>
    </form>
</div>'''
        cards.append(card)

    total_html = f'<p class="text-sm font-bold text-gray-800 pt-2 border-t border-gray-200 mt-2">Итого за месяц: {total_all:.1f} км</p>' if total_all > 0 else ''

    tmpl_html = f'''
<div class="space-y-3">
    <!-- Год/месяц отображается в заголовке модалки (обновляется JS) -->
    <p class="text-sm text-gray-600 font-semibold">{month_name} {year}</p>
    {''.join(cards)}
    {total_html}
</div>
'''
    return HTMLResponse(content=tmpl_html)


@app.get("/htmx/athlete/{athlete_id}/input/{field}")
async def htmx_get_input(
    athlete_id: int,
    field: str,
    request: Request,
    db: Session = Depends(get_db),
):
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise HTTPException(status_code=404, detail="Спортсмен не найден")

    input_htmls = {
        "full_name": (
            '<input type="text" value="' + html.escape(athlete.full_name or "") + '" '
            'data-original-value="' + html.escape(athlete.full_name or "") + '" '
            'data-tag="div" '
            'data-classes="click-editable name-isolated rounded px-2 py-1 text-sm w-full cursor-pointer hover:bg-blue-50" '
            'class="border border-blue-400 rounded px-2 py-1 text-sm w-full cell-edit-input" '
            'data-hx-get="/htmx/athlete/' + str(athlete_id) + '/input/full_name" '
            'data-save-url="/htmx/athlete/' + str(athlete_id) + '/cell/full_name" autofocus>'
        ),
        "rank": (
            '<input type="text" value="' + html.escape(athlete.rank or "") + '" '
            'data-original-value="' + html.escape(athlete.rank or "") + '" '
            'data-tag="span" '
            'data-classes="click-editable px-2 py-1 bg-gray-100 rounded text-sm font-semibold text-gray-700 w-28 inline-block cursor-pointer hover:bg-blue-50" '
            'class="border border-blue-400 rounded px-2 py-1 text-sm w-28 cell-edit-input" '
            'data-hx-get="/htmx/athlete/' + str(athlete_id) + '/input/rank" '
            'data-save-url="/htmx/athlete/' + str(athlete_id) + '/cell/rank" autofocus>'
        ),
        "dispensary_date": (
            '<input type="date" value="' + (athlete.dispensary_date.isoformat() if athlete.dispensary_date else "") + '" '
            'data-original-value="' + html.escape(athlete.dispensary_date.isoformat() if athlete.dispensary_date else "") + '" '
            'data-tag="span" '
            'data-classes="click-editable px-3 py-1 rounded-lg text-sm inline-block dispensary-cell cursor-pointer bg-gray-100 text-gray-600" '
            'class="border border-blue-400 rounded px-2 py-1 text-sm cell-edit-input" '
            'data-hx-get="/htmx/athlete/' + str(athlete_id) + '/input/dispensary_date" '
            'data-save-url="/htmx/athlete/' + str(athlete_id) + '/cell/dispensary_date" autofocus>'
        ),
        "clinic_status": (
            '<input type="text" value="' + html.escape(athlete.clinic_status or "") + '" '
            'data-original-value="' + html.escape(athlete.clinic_status or "") + '" '
            'data-tag="span" '
            'data-classes="click-editable px-3 py-1 rounded-lg text-sm inline-block clinic-cell w-full cursor-pointer bg-gray-100 text-gray-700" '
            'class="border border-blue-400 rounded px-2 py-1 text-sm w-full cell-edit-input" '
            'data-hx-get="/htmx/athlete/' + str(athlete_id) + '/input/clinic_status" '
            'data-save-url="/htmx/athlete/' + str(athlete_id) + '/cell/clinic_status" autofocus>'
        ),
    }

    if field not in input_htmls:
        raise HTTPException(status_code=400, detail=f"Неизвестное поле: {field}")

    return HTMLResponse(input_htmls[field])
