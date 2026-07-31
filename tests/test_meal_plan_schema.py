from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.meal_plan import (
    MealPlanCreate,
    MealType,
    default_meal_plan_name,
)

START = date(2026, 1, 1)


def _valid_meal_plan(**overrides):
    payload = {
        "name": None,
        "description": None,
        "start_date": START,
        "end_date": START + timedelta(days=6),
    }
    payload.update(overrides)
    return payload


def test_valid_meal_plan_parses():
    plan = MealPlanCreate(**_valid_meal_plan())
    assert plan.name is None
    assert plan.end_date == START + timedelta(days=6)


def test_single_day_range_is_allowed():
    plan = MealPlanCreate(**_valid_meal_plan(end_date=START))
    assert plan.start_date == plan.end_date


def test_thirty_day_range_is_allowed():
    plan = MealPlanCreate(**_valid_meal_plan(end_date=START + timedelta(days=29)))
    assert (plan.end_date - plan.start_date).days == 29


def test_thirty_one_day_range_rejected():
    with pytest.raises(ValidationError):
        MealPlanCreate(**_valid_meal_plan(end_date=START + timedelta(days=30)))


def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        MealPlanCreate(**_valid_meal_plan(end_date=START - timedelta(days=1)))


def test_blank_name_becomes_none():
    plan = MealPlanCreate(**_valid_meal_plan(name="   "))
    assert plan.name is None


def test_name_over_max_length_rejected():
    with pytest.raises(ValidationError):
        MealPlanCreate(**_valid_meal_plan(name="x" * 121))


def test_description_over_max_length_rejected():
    with pytest.raises(ValidationError):
        MealPlanCreate(**_valid_meal_plan(description="x" * 4099))


def test_default_meal_plan_name_formats_month_and_day():
    name = default_meal_plan_name(date(2026, 1, 1), date(2026, 1, 30))
    assert name == "Meal Plan for January 1 to January 30"


def test_meal_type_enum_has_no_supper():
    assert "supper" not in [value.value for value in MealType]
    assert {m.value for m in MealType} == {
        "breakfast",
        "brunch",
        "lunch",
        "dinner",
        "dessert",
        "snack",
    }
