from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.globals import settings
from app.main import app

VALID_DOB = date.today().replace(year=date.today().year - 25).isoformat()

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
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


def _valid_ingredient(**overrides):
    payload = {"quantity": "2", "unit": "tsp", "name": "vanilla", "cost": "0.50"}
    payload.update(overrides)
    return payload


def _recipe_payload(**overrides):
    payload = {
        "name": "Pancakes",
        "description": "Fluffy breakfast pancakes.",
        "notes": None,
        "ingredients": [_valid_ingredient()],
        "directions": [{"step_text": "Mix and cook."}],
    }
    payload.update(overrides)
    return payload


def _create_recipe(client, headers, **overrides):
    return client.post("/api/v1/recipes", json=_recipe_payload(**overrides), headers=headers)


def test_create_recipe_requires_auth(client):
    response = client.post("/api/v1/recipes", json=_recipe_payload())
    assert response.status_code == 401


def test_create_recipe_returns_full_recipe(client):
    headers = _register_and_login(client)
    response = _create_recipe(client, headers)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pancakes"
    assert len(body["ingredients"]) == 1
    assert body["ingredients"][0]["name"] == "vanilla"
    assert len(body["directions"]) == 1
    assert body["last_used_in_meal_plan"] is None
    assert body["image_url"] is None
    assert "created_at" not in body  # explicitly excluded from the UI-facing schema


def test_create_recipe_rejects_invalid_payload(client):
    headers = _register_and_login(client)
    response = _create_recipe(client, headers, name="")
    assert response.status_code == 422


def test_get_recipe_returns_created_recipe(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]
    response = client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["id"] == recipe_id


def test_get_missing_recipe_is_404(client):
    headers = _register_and_login(client)
    response = client.get("/api/v1/recipes/999", headers=headers)
    assert response.status_code == 404


def test_recipe_is_scoped_to_owner(client):
    owner_headers = _register_and_login(client, username="owner1")
    other_headers = _register_and_login(client, username="other1")
    recipe_id = _create_recipe(client, owner_headers).json()["id"]

    get_response = client.get(f"/api/v1/recipes/{recipe_id}", headers=other_headers)
    assert get_response.status_code == 404

    update_response = client.put(
        f"/api/v1/recipes/{recipe_id}", json=_recipe_payload(name="Hijacked"), headers=other_headers
    )
    assert update_response.status_code == 404

    delete_response = client.delete(f"/api/v1/recipes/{recipe_id}", headers=other_headers)
    assert delete_response.status_code == 404


def test_update_recipe_replaces_fields_and_children(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    response = client.put(
        f"/api/v1/recipes/{recipe_id}",
        json=_recipe_payload(
            name="Waffles",
            ingredients=[_valid_ingredient(name="cinnamon")],
            directions=[{"step_text": "Mix."}, {"step_text": "Cook in waffle iron."}],
        ),
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Waffles"
    assert [i["name"] for i in body["ingredients"]] == ["cinnamon"]
    assert len(body["directions"]) == 2


def test_delete_recipe_soft_deletes_and_hides_it(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    delete_response = client.delete(f"/api/v1/recipes/{recipe_id}", headers=headers)
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/recipes/{recipe_id}", headers=headers).status_code == 404
    listing = client.get("/api/v1/recipes", headers=headers).json()
    assert listing["items"] == []


def test_list_recipes_defaults_to_recently_added_first(client):
    headers = _register_and_login(client)
    first_id = _create_recipe(client, headers, name="First").json()["id"]
    second_id = _create_recipe(client, headers, name="Second").json()["id"]

    response = client.get("/api/v1/recipes", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [second_id, first_id]
    assert body["page_size"] == 15
    assert body["has_more"] is False


def test_list_recipes_paginates_with_has_more(client):
    headers = _register_and_login(client)
    for i in range(16):
        _create_recipe(client, headers, name=f"Recipe {i}")

    first_page = client.get("/api/v1/recipes?limit=15", headers=headers).json()
    assert len(first_page["items"]) == 15
    assert first_page["has_more"] is True

    second_page = client.get("/api/v1/recipes?limit=15&offset=15", headers=headers).json()
    assert len(second_page["items"]) == 1
    assert second_page["has_more"] is False


def test_list_recipes_only_returns_current_users_recipes(client):
    owner_headers = _register_and_login(client, username="owner2")
    other_headers = _register_and_login(client, username="other2")
    _create_recipe(client, owner_headers)

    response = client.get("/api/v1/recipes", headers=other_headers)
    assert response.json()["items"] == []


def test_upload_image_sets_image_url(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    response = client.post(
        f"/api/v1/recipes/{recipe_id}/image",
        headers=headers,
        files={"file": ("photo.png", PNG_HEADER + b"0" * 100, "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["image_url"] is not None
    assert body["image_url"].startswith("/media/recipes/")


def test_upload_image_rejects_invalid_file_type(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    response = client.post(
        f"/api/v1/recipes/{recipe_id}/image",
        headers=headers,
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )
    assert response.status_code == 422


def test_upload_image_rejects_oversized_file(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    oversized = PNG_HEADER + b"0" * (settings.max_image_size_bytes + 1)
    response = client.post(
        f"/api/v1/recipes/{recipe_id}/image",
        headers=headers,
        files={"file": ("photo.png", oversized, "image/png")},
    )
    assert response.status_code == 422


def test_delete_image_clears_image_url(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]
    client.post(
        f"/api/v1/recipes/{recipe_id}/image",
        headers=headers,
        files={"file": ("photo.png", PNG_HEADER + b"0" * 100, "image/png")},
    )

    response = client.delete(f"/api/v1/recipes/{recipe_id}/image", headers=headers)
    assert response.status_code == 200
    assert response.json()["image_url"] is None


# --- SCRUM-24: last_used_in_meal_plan / recently_used / most_used, now backed
# --- by the meal_recipes join (previously always-None/fallback stubs). ---


def _create_meal_plan(client, headers, **overrides):
    payload = {
        "name": "Test Plan",
        "description": None,
        "start_date": "2026-01-01",
        "end_date": "2026-01-10",
    }
    payload.update(overrides)
    return client.post("/api/v1/meal-plans", json=payload, headers=headers)


def _create_meal(client, headers, plan_id, **overrides):
    payload = {"meal_type": "breakfast", "day": "2026-01-02"}
    payload.update(overrides)
    return client.post(f"/api/v1/meal-plans/{plan_id}/meals", json=payload, headers=headers)


def _attach_recipe(client, headers, plan_id, meal_id, recipe_id):
    return client.post(
        f"/api/v1/meal-plans/{plan_id}/meals/{meal_id}/recipes",
        json={"recipe_id": recipe_id},
        headers=headers,
    )


def test_recipe_never_used_has_null_last_used_in_meal_plan(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]
    assert client.get(f"/api/v1/recipes/{recipe_id}", headers=headers).json()[
        "last_used_in_meal_plan"
    ] is None


def test_recipe_used_in_past_plan_reports_that_plan_name(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]
    plan_id = _create_meal_plan(
        client, headers, name="Old Plan", start_date="2020-01-01", end_date="2020-01-10"
    ).json()["id"]
    meal_id = _create_meal(client, headers, plan_id, day="2020-01-02").json()["id"]
    _attach_recipe(client, headers, plan_id, meal_id, recipe_id)

    response = client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
    assert response.json()["last_used_in_meal_plan"] == "Old Plan"


def test_recipe_used_in_current_plan_takes_priority_over_past(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]

    past_plan_id = _create_meal_plan(
        client, headers, name="Old Plan", start_date="2020-01-01", end_date="2020-01-10"
    ).json()["id"]
    past_meal_id = _create_meal(client, headers, past_plan_id, day="2020-01-02").json()["id"]
    _attach_recipe(client, headers, past_plan_id, past_meal_id, recipe_id)

    today = date.today()
    current_plan_id = _create_meal_plan(
        client,
        headers,
        name="Current Plan",
        start_date=today.isoformat(),
        end_date=today.isoformat(),
    ).json()["id"]
    current_meal_id = _create_meal(
        client, headers, current_plan_id, day=today.isoformat()
    ).json()["id"]
    _attach_recipe(client, headers, current_plan_id, current_meal_id, recipe_id)

    response = client.get(f"/api/v1/recipes/{recipe_id}", headers=headers)
    assert response.json()["last_used_in_meal_plan"] == "Current Plan"


def test_list_recipes_sort_most_used_orders_by_attachment_count(client):
    headers = _register_and_login(client)
    low_id = _create_recipe(client, headers, name="Low").json()["id"]
    high_id = _create_recipe(client, headers, name="High").json()["id"]

    plan_id = _create_meal_plan(client, headers).json()["id"]
    meal1 = _create_meal(client, headers, plan_id, meal_type="breakfast", day="2026-01-02").json()["id"]
    meal2 = _create_meal(client, headers, plan_id, meal_type="lunch", day="2026-01-02").json()["id"]
    meal3 = _create_meal(client, headers, plan_id, meal_type="dinner", day="2026-01-02").json()["id"]

    _attach_recipe(client, headers, plan_id, meal1, high_id)
    _attach_recipe(client, headers, plan_id, meal2, high_id)
    _attach_recipe(client, headers, plan_id, meal3, low_id)

    response = client.get("/api/v1/recipes?sort=most_used", headers=headers)
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [high_id, low_id]


def test_list_recipes_sort_recently_used_orders_unused_last(client):
    headers = _register_and_login(client)
    unused_id = _create_recipe(client, headers, name="Unused").json()["id"]
    used_id = _create_recipe(client, headers, name="Used").json()["id"]

    plan_id = _create_meal_plan(client, headers).json()["id"]
    meal_id = _create_meal(client, headers, plan_id).json()["id"]
    _attach_recipe(client, headers, plan_id, meal_id, used_id)

    response = client.get("/api/v1/recipes?sort=recently_used", headers=headers)
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [used_id, unused_id]


def test_recipe_list_item_includes_last_used_in_meal_plan(client):
    headers = _register_and_login(client)
    recipe_id = _create_recipe(client, headers).json()["id"]
    plan_id = _create_meal_plan(client, headers, name="Old Plan").json()["id"]
    meal_id = _create_meal(client, headers, plan_id).json()["id"]
    _attach_recipe(client, headers, plan_id, meal_id, recipe_id)

    items = client.get("/api/v1/recipes", headers=headers).json()["items"]
    assert items[0]["last_used_in_meal_plan"] == "Old Plan"
