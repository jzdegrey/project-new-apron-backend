from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.recipe import RecipeCreate, RecipeDirectionIn, RecipeIngredientIn


def _valid_ingredient(**overrides):
    payload = {"quantity": "2", "unit": "tsp", "name": "vanilla", "cost": "0.50"}
    payload.update(overrides)
    return payload


def _valid_recipe(**overrides):
    payload = {
        "name": "Pancakes",
        "description": "Fluffy breakfast pancakes.",
        "notes": None,
        "ingredients": [_valid_ingredient()],
        "directions": [{"step_text": "Mix and cook."}],
    }
    payload.update(overrides)
    return payload


def test_valid_recipe_parses():
    recipe = RecipeCreate(**_valid_recipe())
    assert recipe.name == "Pancakes"
    assert len(recipe.ingredients) == 1
    assert len(recipe.directions) == 1


def test_blank_ingredient_row_is_dropped_not_rejected():
    recipe = RecipeCreate(
        **_valid_recipe(
            ingredients=[
                _valid_ingredient(),
                {"quantity": "1", "unit": "", "name": "", "cost": "0"},
            ]
        )
    )
    assert len(recipe.ingredients) == 1


def test_blank_direction_step_is_dropped_not_rejected():
    recipe = RecipeCreate(
        **_valid_recipe(directions=[{"step_text": "Mix and cook."}, {"step_text": "   "}])
    )
    assert len(recipe.directions) == 1


def test_ingredient_with_only_name_still_requires_unit():
    with pytest.raises(ValidationError):
        RecipeCreate(**_valid_recipe(ingredients=[{"quantity": "1", "unit": "", "name": "salt"}]))


@pytest.mark.parametrize("field", ["ingredients", "directions"])
def test_at_least_one_required(field):
    with pytest.raises(ValidationError):
        RecipeCreate(**_valid_recipe(**{field: []}))


@pytest.mark.parametrize("name", ["", "x" * 61])
def test_recipe_name_length_bounds(name):
    with pytest.raises(ValidationError):
        RecipeCreate(**_valid_recipe(name=name))


def test_recipe_name_max_length_boundary_is_allowed():
    recipe = RecipeCreate(**_valid_recipe(name="x" * 60))
    assert len(recipe.name) == 60


@pytest.mark.parametrize("field", ["description", "notes"])
def test_optional_text_over_max_length_rejected(field):
    with pytest.raises(ValidationError):
        RecipeCreate(**_valid_recipe(**{field: "x" * 4099}))


@pytest.mark.parametrize("field", ["description", "notes"])
def test_optional_text_blank_string_becomes_none(field):
    recipe = RecipeCreate(**_valid_recipe(**{field: "   "}))
    assert getattr(recipe, field) is None


@pytest.mark.parametrize("quantity", ["0", "-1", "99.00001", "100"])
def test_ingredient_quantity_out_of_bounds_rejected(quantity):
    with pytest.raises(ValidationError):
        RecipeIngredientIn(**_valid_ingredient(quantity=quantity))


def test_ingredient_quantity_supports_fractions():
    ingredient = RecipeIngredientIn(**_valid_ingredient(quantity="0.3333"))
    assert ingredient.quantity == Decimal("0.3333")


def test_ingredient_quantity_max_boundary_allowed():
    ingredient = RecipeIngredientIn(**_valid_ingredient(quantity="99"))
    assert ingredient.quantity == Decimal("99")


@pytest.mark.parametrize("name", ["", "x" * 31])
def test_ingredient_name_length_bounds(name):
    with pytest.raises(ValidationError):
        RecipeIngredientIn(**_valid_ingredient(name=name))


def test_ingredient_unit_must_be_known_value():
    with pytest.raises(ValidationError):
        RecipeIngredientIn(**_valid_ingredient(unit="handful"))


@pytest.mark.parametrize("cost", ["-0.01", "1000.01"])
def test_ingredient_cost_out_of_bounds_rejected(cost):
    with pytest.raises(ValidationError):
        RecipeIngredientIn(**_valid_ingredient(cost=cost))


def test_ingredient_cost_more_than_two_decimal_places_rejected():
    with pytest.raises(ValidationError):
        RecipeIngredientIn(**_valid_ingredient(cost="1.005"))


def test_ingredient_cost_defaults_to_zero():
    ingredient = RecipeIngredientIn(unit="tsp", name="salt")
    assert ingredient.cost == Decimal("0.00")


def test_ingredient_quantity_defaults_to_one():
    ingredient = RecipeIngredientIn(unit="tsp", name="salt")
    assert ingredient.quantity == Decimal("1")


@pytest.mark.parametrize("step_text", ["", "x" * 256])
def test_direction_step_length_bounds(step_text):
    with pytest.raises(ValidationError):
        RecipeDirectionIn(step_text=step_text)


def test_direction_step_max_length_boundary_is_allowed():
    direction = RecipeDirectionIn(step_text="x" * 255)
    assert len(direction.step_text) == 255
