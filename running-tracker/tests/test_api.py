import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Импортируем компоненты ДО изменения состояния
from app.main import app, sanitize_name, get_db
from app.models import Athlete, Training, calculate_dispensary_status
from app.database import Base


# ==================== sanitize_name tests ====================

def test_sanitize_allows_safe_tags():
    """Разрешенные теги должны сохраниться."""
    result = sanitize_name('<b>Жирный</b> <i>Курсив</i> <u>Подчеркнутый</u>')
    assert "<b>Жирный</b>" in result
    assert "<i>Курсив</i>" in result
    assert "<u>Подчеркнутый</u>" in result


def test_sanitize_removes_script():
    """Теги script должны быть вырезаны (текст внутри остается)."""
    result = sanitize_name('<script>alert(1)</script> <b>Иван</b>')
    assert "<script>" not in result
    assert "alert" in result  # bleach оставляет текст внутри удаленных тегов
    assert "<b>Иван</b>" in result


def test_sanitize_removes_img():
    """Теги img должны быть вырезаны."""
    result = sanitize_name('<img src="x" onload="malware()">')
    assert "<img" not in result
    assert "onload" not in result


def test_sanitize_removes_anchor():
    """Теги a должны быть вырезаны."""
    result = sanitize_name('<a href="http://evil.com">клик</a>')
    assert "<a" not in result
    assert "href" not in result


def test_sanitize_removes_div():
    """Теги div должны быть вырезаны."""
    result = sanitize_name('<div>текст</div>')
    assert "<div>" not in result
    assert "текст" in result  # сам текст должен остаться


def test_sanitize_allows_font_attributes():
    """Атрибуты color, face, size тега font должны разрешены."""
    result = sanitize_name('<font color="red" face="Caveat" size="5">Текст</font>')
    assert 'color="red"' in result
    assert 'face="Caveat"' in result


def test_sanitize_allows_span_class():
    """Атрибут class тега span должен разрешен."""
    result = sanitize_name('<span class="highlight">Текст</span>')
    assert 'class="highlight"' in result


def test_sanitize_xss_injection_attempt():
    """Комбинация XSS-атаки должна быть полностью очищена."""
    raw = '<b>Иван</b> <script>alert(1)</script> ?'
    result = sanitize_name(raw)
    # bleach удаляет теги <script>, но оставляет текст внутри
    assert "<script>" not in result
    assert "alert" in result  # текст alert остается после удаления тегов


# ==================== calculate_dispensary_status tests ====================

def test_dispensary_none_returns_none_status():
    """Нет даты -> статус none."""
    assert calculate_dispensary_status(None) == "none"


def test_dispensary_expired_past_date():
    """Прошедшая дата -> expired."""
    past = date.today() - timedelta(days=30)
    assert calculate_dispensary_status(past) == "expired"


def test_dispensary_expired_within_14_days():
    """Дата в течение 14 дней -> expired."""
    future = date.today() + timedelta(days=10)
    assert calculate_dispensary_status(future) == "expired"


def test_dispensary_expired_exactly_14_days():
    """Ровно через 14 дней -> expired (<= 14)."""
    boundary = date.today() + timedelta(days=14)
    assert calculate_dispensary_status(boundary) == "expired"


def test_dispensary_valid_more_than_14_days():
    """Через 15 дней -> valid."""
    future = date.today() + timedelta(days=15)
    assert calculate_dispensary_status(future) == "valid"


# ==================== Test fixtures for API ====================

@pytest.fixture(scope="module")
def test_engine():
    """Создаем тестовую БД в файле, чтобы несколько соединений видели одни и те же данные."""
    import tempfile
    from sqlalchemy import create_engine, text as sql_text
    from app.database import Base
    # In-memory SQLite не шарится между соединениями, используем temp file
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    # Импортируем модели чтобы они зарегистрировались
    from app import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    os.unlink(path)


@pytest.fixture(scope="module")
def test_db(test_engine):
    """Создаем сессию тестовой БД."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def _clear_data(test_db):
    """Очищаем данные перед каждым API-тестом."""
    from sqlalchemy import text
    test_db.execute(text("DELETE FROM athletes"))
    test_db.execute(text("DELETE FROM trainings"))
    test_db.commit()


@pytest.fixture(scope="module")
def client(test_db):
    """Создаем TestClient с подменой зависимости get_db."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ==================== Athlete API tests ====================

def test_create_athlete(client, _clear_data):
    """Создание спортсмена через POST /api/athletes."""
    response = client.post("/api/athletes", json={
        "full_name": "<b>Иван</b> Петров",
        "rank": "КМС",
        "rusada_status": True,
        "dispensary_date": (date.today() + timedelta(days=30)).isoformat(),
        "clinic_status": "Да",
        "is_active": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "<b>Иван</b> Петров"
    assert data["rank"] == "КМС"
    assert data["rusada_status"] is True
    assert data["id"] is not None


def test_create_athlete_with_xss_gets_sanitized(client, _clear_data):
    """Ввод с XSS должен быть очищен при создании."""
    xss_payload = '<b>Иван</b> <script>alert(1)</script> ?'
    response = client.post("/api/athletes", json={
        "full_name": xss_payload,
    })
    assert response.status_code == 200
    data = response.json()
    assert "<script>" not in data["full_name"]
    assert "alert" in data["full_name"]  # bleach оставляет текст внутри тегов
    assert "<b>Иван</b>" in data["full_name"]


def test_get_athletes_empty(client, _clear_data):
    """Пустой список спортсменов."""
    response = client.get("/api/athletes")
    assert response.status_code == 200
    assert response.json() == []


def test_get_athletes_with_data(test_db, client, _clear_data):
    """Список спортсменов с данными."""
    athlete = Athlete(full_name="Тест Спортсмен", rank="I", rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.get("/api/athletes")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["full_name"] == "Тест Спортсмен"


def test_update_athlete(test_db, client, _clear_data):
    """Обновление спортсмена через PUT /api/athletes/{id}."""
    athlete = Athlete(full_name="Новичок", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.put(f"/api/athletes/{athlete.id}", json={
        "full_name": "<b>Обновленный</b> Новичок",
        "rank": "III",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "<b>Обновленный</b> Новичок"
    assert data["rank"] == "III"


def test_update_athlete_xss_gets_sanitized(test_db, client, _clear_data):
    """Обновление имени с XSS должно быть очищено."""
    athlete = Athlete(full_name="Оригинал", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    xss = '<img src="x" onload="hack()"> Улучшенное имя'
    response = client.put(f"/api/athletes/{athlete.id}", json={
        "full_name": xss,
    })
    assert response.status_code == 200
    data = response.json()
    assert "<img" not in data["full_name"]
    assert "onload" not in data["full_name"]
    assert "Улучшенное имя" in data["full_name"]


def test_delete_athlete(test_db, client, _clear_data):
    """Удаление спортсмена."""
    athlete = Athlete(full_name="Удаляемый", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.delete(f"/api/athletes/{athlete.id}")
    assert response.status_code == 200
    detail = response.json()["detail"].lower()
    assert "удалён" in detail or "deleted" in detail


def test_delete_athlete_not_found(client, _clear_data):
    """Удаление несуществующего спортсмена -> 404."""
    response = client.delete("/api/athletes/9999")
    assert response.status_code == 404


# ==================== Training API tests ====================

def test_create_training(test_db, client, _clear_data):
    """Создание тренировки через POST /api/trainings."""
    athlete = Athlete(full_name="Бегун Тест", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    training_date = date(2025, 1, 15)
    response = client.post("/api/trainings", json={
        "athlete_id": athlete.id,
        "date": training_date.isoformat(),
        "distance_km": 10.5,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["distance_km"] == 10.5
    assert data["athlete_id"] == athlete.id


def test_upsert_training_update_distance(test_db, client, _clear_data):
    """Повторный POST с той же датой -> обновление (upsert)."""
    athlete = Athlete(full_name="Регулярный бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    training_date = date(2025, 2, 10)
    first_resp = client.post("/api/trainings", json={
        "athlete_id": athlete.id,
        "date": training_date.isoformat(),
        "distance_km": 5.0,
    })
    assert first_resp.status_code == 200
    assert first_resp.json()["distance_km"] == 5.0

    second_resp = client.post("/api/trainings", json={
        "athlete_id": athlete.id,
        "date": training_date.isoformat(),
        "distance_km": 12.0,
    })
    assert second_resp.status_code == 200
    assert second_resp.json()["distance_km"] == 12.0


def test_get_yearly_km_sum(test_db, client, _clear_data):
    """Подсчет годовой суммы километров."""
    athlete = Athlete(full_name="Годовой бегун", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    for month, dist in [(1, 50.0), (2, 75.5)]:
        training = Training(athlete_id=athlete.id, date=date(2025, month, 15), distance_km=dist)
        test_db.add(training)
    test_db.commit()

    response = client.get("/api/athletes?year=2025")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["yearly_km"] == 125.5


def test_get_yearly_km_empty(test_db, client, _clear_data):
    """Годовая сумма без тренировок -> 0."""
    athlete = Athlete(full_name="Без пробежек", rank=None, rusada_status=False)
    test_db.add(athlete)
    test_db.commit()
    test_db.refresh(athlete)

    response = client.get("/api/athletes?year=2025")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["yearly_km"] == 0.0


def test_athlete_with_dispensary_status_in_response(test_db, client, _clear_data):
    """Статус диспансера включен в ответ GET /api/athletes."""
    valid_date = (date.today() + timedelta(days=30)).isoformat()
    expired_date = (date.today() - timedelta(days=10)).isoformat()

    athlete_valid = Athlete(full_name="Валидный", dispensary_date=date.fromisoformat(valid_date), rusada_status=False)
    athlete_expired = Athlete(full_name="Просроченный", dispensary_date=date.fromisoformat(expired_date), rusada_status=False)
    test_db.add(athlete_valid)
    test_db.add(athlete_expired)
    test_db.commit()

    response = client.get("/api/athletes?year=2025")
    assert response.status_code == 200
    data = {d["full_name"]: d for d in response.json()}
    assert data["Валидный"]["dispensary_status"] == "valid"
    assert data["Просроченный"]["dispensary_status"] == "expired"


def test_health_check(client):
    """Проверка эндпоинта здоровья."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
