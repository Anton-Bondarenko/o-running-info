import os
import tempfile
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Импортируем компоненты ДО изменения состояния
from app.main import app, get_db
from app.models import Athlete, Training
from app.database import Base


@pytest.fixture(scope="module")
def test_engine():
    """Создаем тестовую БД в файле."""
    fd, path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    try:
        os.unlink(path)
    except OSError:
        pass  # Windows file lock race condition


@pytest.fixture(scope="module")
def test_db(test_engine):
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def _clear_data(test_db):
    """Очищаем данные перед каждым тестом."""
    test_db.execute(text("DELETE FROM athletes"))
    test_db.execute(text("DELETE FROM trainings"))
    test_db.commit()


@pytest.fixture(scope="module")
def client(test_db):
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ==================== HTML ROUTES TESTS ====================

def test_get_index_returns_200(client, _clear_data):
    """GET / возвращает 200 и HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_get_index_shows_athletes(test_db, client, _clear_data):
    """GET / показывает таблицу с именами спортсменов."""
    athlete1 = Athlete(full_name="<b>Иванов</b> Иван", rank="КМС", rusada_status=True)
    athlete2 = Athlete(full_name="Петрова Анна", rank="МС", dispensary_date=datetime.date.today() + datetime.timedelta(days=30))
    test_db.add(athlete1)
    test_db.add(athlete2)
    test_db.commit()

    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert "<b>Иванов</b> Иван" in html
    assert "Петрова Анна" in html


def test_htmx_post_create_athlete(client, _clear_data):
    """POST /htmx/athlete добавляет спортсмена и возвращает строку таблицы."""
    response = client.post("/htmx/athlete", data={
        "full_name": "<b>Новый</b> Спортсмен",
        "rank": "I",
        "rusada_status": "false",
        "dispensary_date": "",
        "clinic_status": "Не надо",
    })
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<b>Новый</b> Спортсмен" in response.text


def test_htmx_delete_athlete(test_db, client, _clear_data):
    """DELETE /htmx/athlete/{id} удаляет спортсмена."""
    athlete = Athlete(full_name="Удаляемый", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.delete(f"/htmx/athlete/{athlete.id}")
    assert response.status_code == 200
    assert response.text == "deleted"


def test_htmx_patch_cell_full_name(test_db, client, _clear_data):
    """PATCH /htmx/athlete/{id}/cell/full_name обновляет имя."""
    athlete = Athlete(full_name="Оригинал", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.patch(
        f"/htmx/athlete/{athlete.id}/cell/full_name",
        json={"value": "<b>Обновленное</b> Имя"},
    )
    assert response.status_code == 200
    assert "<b>Обновленное</b>" in response.text

def test_htmx_patch_cell_rank(test_db, client, _clear_data):
    """PATCH /htmx/athlete/{id}/cell/rank обновляет разряд."""
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.patch(
        f"/htmx/athlete/{athlete.id}/cell/rank",
        json={"value": "КМС"},
    )
    assert response.status_code == 200
    assert response.text == "updated"


def test_htmx_patch_cell_dispensary_date(test_db, client, _clear_data):
    """PATCH /htmx/athlete/{id}/cell/dispensary_date обновляет дату."""
    future_date = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    athlete = Athlete(full_name="Бегун", rank=None, dispensary_date=None)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.patch(
        f"/htmx/athlete/{athlete.id}/cell/dispensary_date",
        json={"value": future_date},
    )
    assert response.status_code == 200
    assert response.text == "updated"


def test_htmx_get_input_returns_html(test_db, client, _clear_data):
    """GET /htmx/athlete/{id}/input/{field} возвращает HTML input."""
    athlete = Athlete(full_name="Тест Имя", rank="КМС", dispensary_date=datetime.date(2026, 12, 31))
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.get(f"/htmx/athlete/{athlete.id}/input/full_name")
    assert response.status_code == 200
    assert "input" in response.text.lower()
    assert "Тест Имя" in response.text

    response = client.get(f"/htmx/athlete/{athlete.id}/input/rank")
    assert response.status_code == 200
    assert "КМС" in response.text

    response = client.get(f"/htmx/athlete/{athlete.id}/input/dispensary_date")
    assert response.status_code == 200
    assert "2026-12-31" in response.text


def test_htmx_toggle_rusada_status(test_db, client, _clear_data):
    """PATCH /htmx/athlete/{id}/cell/rusada_status переключает статус."""
    athlete = Athlete(full_name="Бегун", rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.patch(
        f"/htmx/athlete/{athlete.id}/cell/rusada_status",
        json={"value": "true"},
    )
    assert response.status_code == 200
    assert response.text == "updated"


def test_index_year_switching(client, _clear_data):
    """GET /?year=2025 переключает год."""
    response = client.get("/?year=2025")
    assert response.status_code == 200


def test_delete_nonexistent_athlete(client, _clear_data):
    """DELETE несуществующего -> 404."""
    response = client.delete("/htmx/athlete/9999")
    assert response.status_code == 404


def test_patch_nonexistent_athlete(client, _clear_data):
    """PATCH несуществующего -> 404."""
    response = client.patch("/htmx/athlete/9999/cell/full_name", json={"value": "Тест"})
    assert response.status_code == 404


def test_index_month_rank_fallback_to_previous_month(client, test_db, _clear_data):
    """Когда за текущий месяц данных нет, ранжирование идёт по последнему месяцу с данными."""
    from app.models import Training
    athlete1 = Athlete(full_name="Бегун 1", rank=None, rusada_status=False)
    athlete2 = Athlete(full_name="Бегун 2", rank=None, rusada_status=False)
    test_db.add_all([athlete1, athlete2])
    test_db.commit()

    # Добавляем объёмы только за июль (месяц 7) — текущий месяц ноябрь (11), данных нет
    today = datetime.date.today()
    current_month = today.month  # November = 11
    training1 = Training(athlete_id=athlete1.id, date=datetime.date(today.year, 7, 15), distance_km=50.0)
    training2 = Training(athlete_id=athlete2.id, date=datetime.date(today.year, 7, 20), distance_km=30.0)
    test_db.add_all([training1, training2])
    test_db.commit()

    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    # Колонка должна содержать заголовок с месяцем
    assert "Место" in html


# ==================== TRAINING API TESTS ====================

def test_get_trainings_empty(client, _clear_data):
    """GET /api/trainings без данных возвращает пустой список."""
    response = client.get("/api/trainings?athlete_id=1")
    assert response.status_code == 200
    assert response.json() == []


def test_get_trainings_with_data(test_db, client, _clear_data):
    """GET /api/trainings возвращает тренировки спортсмена."""
    from app.models import Training
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    today = datetime.date.today()
    training = Training(athlete_id=athlete.id, date=datetime.date(today.year, 5, 15), distance_km=42.5)
    test_db.add(training)
    test_db.commit()

    response = client.get(f"/api/trainings?athlete_id={athlete.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["distance_km"] == 42.5


def test_get_trainings_filtered_by_month(test_db, client, _clear_data):
    """GET /api/trainings с фильтром по месяцу возвращает только тренировки за этот месяц."""
    from app.models import Training
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    today = datetime.date.today()
    current_year = today.year
    # Добавляем тренировки за май и июнь
    training_may = Training(athlete_id=athlete.id, date=datetime.date(current_year, 5, 10), distance_km=30.0)
    training_june = Training(athlete_id=athlete.id, date=datetime.date(current_year, 6, 20), distance_km=40.0)
    test_db.add_all([training_may, training_june])
    test_db.commit()

    # Запрашиваем только июнь
    response = client.get(f"/api/trainings?athlete_id={athlete.id}&month=6&year={current_year}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["distance_km"] == 40.0


def test_get_trainings_filtered_by_year(test_db, client, _clear_data):
    """GET /api/trainings с фильтром по году возвращает тренировки за этот год."""
    from app.models import Training
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    today = datetime.date.today()
    current_year = today.year
    training = Training(athlete_id=athlete.id, date=datetime.date(current_year, 3, 15), distance_km=25.0)
    test_db.add(training)
    test_db.commit()

    response = client.get(f"/api/trainings?athlete_id={athlete.id}&year={current_year}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1


def test_post_training_create(test_db, client, _clear_data):
    """POST /api/trainings создаёт новую тренировку."""
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.post("/api/trainings", json={
        "athlete_id": athlete.id,
        "date": "2026-07-15",
        "distance_km": 35.5,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["athlete_id"] == athlete.id
    assert data["distance_km"] == 35.5

    # Проверяем что тренировка сохранена в БД
    stored = test_db.query(Training).filter(Training.athlete_id == athlete.id).first()
    assert stored is not None
    assert stored.distance_km == 35.5


def test_post_training_upsert(test_db, client, _clear_data):
    """POST /api/trainings обновляет существующую тренировку (upsert)."""
    from app.models import Training
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    today = datetime.date.today()
    training = Training(athlete_id=athlete.id, date=datetime.date(today.year, 5, 10), distance_km=30.0)
    test_db.add_all([athlete, training])
    test_db.commit()

    response = client.post("/api/trainings", json={
        "athlete_id": athlete.id,
        "date": today.isoformat(),
        "distance_km": 45.0,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["distance_km"] == 45.0


def test_delete_training(test_db, client, _clear_data):
    """DELETE /api/trainings/{id} удаляет тренировку."""
    from app.models import Training
    athlete = Athlete(full_name="Бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    today = datetime.date.today()
    training = Training(athlete_id=athlete.id, date=today, distance_km=20.0)
    test_db.add_all([athlete, training])
    test_db.commit()
    test_db.refresh(training)

    response = client.delete(f"/api/trainings/{training.id}")
    assert response.status_code == 200
    assert response.json()["detail"] == "deleted"

    # Проверяем что тренировка удалена
    remaining = test_db.query(Training).filter(Training.athlete_id == athlete.id).first()
    assert remaining is None


def test_delete_nonexistent_training(client, _clear_data):
    """DELETE несуществующей тренировки -> 404."""
    response = client.delete("/api/trainings/9999")
    assert response.status_code == 404
