from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

TODAY = date.today()
VALID_DOB = date.today().replace(year=date.today().year - 25).isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.globals import settings

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _register_and_login(client: TestClient, username: str = "janedoe1") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "password": "sup3rSecret!",
            "confirm_password": "sup3rSecret!",
            "first_name": "Jane",
            "last_name": "Doe",
            "date_of_birth": VALID_DOB,
            "agreed_to_terms": True,
        },
    )
    token = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": "sup3rSecret!"},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _meal_plan_payload(**overrides):
    payload = {
        "name": "Week One",
        "description": "First week of meals.",
        "start_date": (TODAY - timedelta(days=2)).isoformat(),
        "end_date": (TODAY + timedelta(days=4)).isoformat(),
    }
    payload.update(overrides)
    return payload


def _create_meal_plan(client, headers, **overrides):
    return client.post("/api/v1/meal-plans", json=_meal_plan_payload(**overrides), headers=headers)


def _recipe_payload(**overrides):
    payload = {
        "name": "Pancakes",
        "description": None,
        "notes": None,
        "ingredients": [{"quantity": "2", "unit": "tsp", "name": "vanilla", "cost": "0.50"}],
        "directions": [{"step_text": "Mix and cook."}],
    }
    payload.update(overrides)
    return payload


def _create_recipe(client, headers, **overrides):
    return client.post("/api/v1/recipes", json=_recipe_payload(**overrides), headers=headers)


def test_create_meal_plan_requires_auth(client):
    response = client.post("/api/v1/meal-plans", json=_meal_plan_payload())
    assert response.status_code == 401


def test_create_meal_plan_returns_full_plan(client):
    headers = _register_and_login(client)
    response = _create_meal_plan(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Week One"
    assert body["meals"] == []


def test_create_meal_plan_default_name(client):
    headers = _register_and_login(client)
    response = _create_meal_plan(
        client, headers, name=None, start_date="2026-01-01", end_date="2026-01-07"
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Meal Plan for January 1 to January 7"


def test_create_meal_plan_rejects_invalid_range(client):
    headers = _register_and_login(client)
    response = _create_meal_plan(
        client, headers, start_date="2026-01-31", end_date="2026-01-01"
    )
    assert response.status_code == 422


def test_get_missing_meal_plan_is_404(client):
    headers = _register_and_login(client)
    response = client.get("/api/v1/meal-plans/999", headers=headers)
    assert response.status_code == 404


def test_meal_plan_is_scoped_to_owner(client):
    owner_headers = _register_and_login(client, username="owner1")
    other_headers = _register_and_login(client, username="other1")
    plan_id = _create_meal_plan(client, owner_headers).json()["id"]

    assert client.get(f"/api/v1/meal-plans/{plan_id}", headers=other_headers).status_code == 404
    assert (
        client.put(
            f"/api/v1/meal-plans/{plan_id}", json=_meal_plan_payload(), headers=other_headers
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/meal-plans/{plan_id}", headers=other_headers).status_code == 404


def test_update_meal_plan_replaces_editable_fields(client):
    headers = _register_and_login(client)
    plan_id = _create_meal_plan(client, headers).json()["id"]

    response = client.put(
        f"/api/v1/meal-plans/{plan_id}",
        json=_meal_plan_payload(name="Week Two", description="Updated."),
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Week Two"
    assert body["description"] == "Updated."


def test_update_meal_plan_rejects_shrinking_range_past_existing_meal(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-10"
    ).json()
    client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-09"},
        headers=headers,
    )

    response = client.put(
        f"/api/v1/meal-plans/{plan['id']}",
        json=_meal_plan_payload(start_date="2026-01-01", end_date="2026-01-05"),
        headers=headers,
    )
    assert response.status_code == 422


def test_delete_meal_plan_soft_deletes_and_hides_it(client):
    headers = _register_and_login(client)
    plan_id = _create_meal_plan(client, headers).json()["id"]

    assert client.delete(f"/api/v1/meal-plans/{plan_id}", headers=headers).status_code == 204
    assert client.get(f"/api/v1/meal-plans/{plan_id}", headers=headers).status_code == 404
    assert client.get("/api/v1/meal-plans", headers=headers).json()["items"] == []


def test_list_meal_plans_paginates_with_has_more(client):
    headers = _register_and_login(client)
    for i in range(16):
        _create_meal_plan(
            client,
            headers,
            start_date=(TODAY + timedelta(days=100 + i)).isoformat(),
            end_date=(TODAY + timedelta(days=101 + i)).isoformat(),
        )

    first_page = client.get("/api/v1/meal-plans?limit=15", headers=headers).json()
    assert len(first_page["items"]) == 15
    assert first_page["has_more"] is True

    second_page = client.get("/api/v1/meal-plans?limit=15&offset=15", headers=headers).json()
    assert len(second_page["items"]) == 1
    assert second_page["has_more"] is False


def test_list_meal_plans_orders_current_then_upcoming_then_past(client):
    headers = _register_and_login(client)
    past_id = _create_meal_plan(
        client,
        headers,
        start_date=(TODAY - timedelta(days=10)).isoformat(),
        end_date=(TODAY - timedelta(days=5)).isoformat(),
    ).json()["id"]
    upcoming_id = _create_meal_plan(
        client,
        headers,
        start_date=(TODAY + timedelta(days=5)).isoformat(),
        end_date=(TODAY + timedelta(days=10)).isoformat(),
    ).json()["id"]
    current_id = _create_meal_plan(
        client,
        headers,
        start_date=(TODAY - timedelta(days=1)).isoformat(),
        end_date=(TODAY + timedelta(days=1)).isoformat(),
    ).json()["id"]

    items = client.get("/api/v1/meal-plans", headers=headers).json()["items"]
    assert [item["id"] for item in items] == [current_id, upcoming_id, past_id]


def test_list_meal_plans_only_returns_current_users_plans(client):
    owner_headers = _register_and_login(client, username="owner2")
    other_headers = _register_and_login(client, username="other2")
    _create_meal_plan(client, owner_headers)

    response = client.get("/api/v1/meal-plans", headers=other_headers)
    assert response.json()["items"] == []


def test_create_meal_requires_day_within_plan_range(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()

    response = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-08"},
        headers=headers,
    )
    assert response.status_code == 422


def test_create_meal_within_range_succeeds_and_appears_in_plan(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()

    response = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    )
    assert response.status_code == 201
    meal = response.json()
    assert meal["meal_type"] == "breakfast"
    assert meal["recipes"] == []

    detail = client.get(f"/api/v1/meal-plans/{plan['id']}", headers=headers).json()
    assert len(detail["meals"]) == 1
    assert detail["meals"][0]["id"] == meal["id"]


def test_create_meal_rejects_duplicate_type_on_same_day(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    )

    response = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    )
    assert response.status_code == 409


def test_meals_sorted_by_day_then_meal_type_order(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    for meal_type, day in [
        ("dinner", "2026-01-01"),
        ("breakfast", "2026-01-02"),
        ("breakfast", "2026-01-01"),
        ("lunch", "2026-01-01"),
    ]:
        client.post(
            f"/api/v1/meal-plans/{plan['id']}/meals",
            json={"meal_type": meal_type, "day": day},
            headers=headers,
        )

    detail = client.get(f"/api/v1/meal-plans/{plan['id']}", headers=headers).json()
    ordered = [(m["day"], m["meal_type"]) for m in detail["meals"]]
    assert ordered == [
        ("2026-01-01", "breakfast"),
        ("2026-01-01", "lunch"),
        ("2026-01-01", "dinner"),
        ("2026-01-02", "breakfast"),
    ]


def test_update_meal_changes_type_and_day(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    ).json()["id"]

    response = client.put(
        f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}",
        json={"meal_type": "lunch", "day": "2026-01-03"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meal_type"] == "lunch"
    assert body["day"] == "2026-01-03"


def test_delete_meal_removes_it_from_plan(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    ).json()["id"]

    assert (
        client.delete(
            f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}", headers=headers
        ).status_code
        == 204
    )
    detail = client.get(f"/api/v1/meal-plans/{plan['id']}", headers=headers).json()
    assert detail["meals"] == []


def test_attach_recipe_to_meal(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    ).json()["id"]
    recipe_id = _create_recipe(client, headers).json()["id"]

    response = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}/recipes",
        json={"recipe_id": recipe_id},
        headers=headers,
    )
    assert response.status_code == 200
    recipes = response.json()["recipes"]
    assert len(recipes) == 1
    assert recipes[0]["id"] == recipe_id
    assert recipes[0]["name"] == "Pancakes"


def test_attach_recipe_is_idempotent(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    ).json()["id"]
    recipe_id = _create_recipe(client, headers).json()["id"]

    for _ in range(2):
        response = client.post(
            f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}/recipes",
            json={"recipe_id": recipe_id},
            headers=headers,
        )
    assert len(response.json()["recipes"]) == 1


def test_attach_recipe_rejects_other_users_recipe(client):
    owner_headers = _register_and_login(client, username="owner3")
    other_headers = _register_and_login(client, username="other3")
    plan = _create_meal_plan(
        client, owner_headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=owner_headers,
    ).json()["id"]
    other_recipe_id = _create_recipe(client, other_headers).json()["id"]

    response = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}/recipes",
        json={"recipe_id": other_recipe_id},
        headers=owner_headers,
    )
    assert response.status_code == 404


def test_detach_recipe_removes_it(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    meal_id = client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    ).json()["id"]
    recipe_id = _create_recipe(client, headers).json()["id"]
    client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}/recipes",
        json={"recipe_id": recipe_id},
        headers=headers,
    )

    response = client.delete(
        f"/api/v1/meal-plans/{plan['id']}/meals/{meal_id}/recipes/{recipe_id}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["recipes"] == []


def test_meal_plan_list_item_reports_meal_count(client):
    headers = _register_and_login(client)
    plan = _create_meal_plan(
        client, headers, start_date="2026-01-01", end_date="2026-01-07"
    ).json()
    client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "breakfast", "day": "2026-01-02"},
        headers=headers,
    )
    client.post(
        f"/api/v1/meal-plans/{plan['id']}/meals",
        json={"meal_type": "lunch", "day": "2026-01-02"},
        headers=headers,
    )

    items = client.get("/api/v1/meal-plans", headers=headers).json()["items"]
    assert items[0]["meal_count"] == 2
