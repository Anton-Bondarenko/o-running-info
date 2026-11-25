import os
import tempfile
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Импортируем компоненты ДО изменения состояния
from app.main import app, get_db
from app.models import Athlete
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
    os.unlink(path)


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
    assert response.text == "updated"


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
