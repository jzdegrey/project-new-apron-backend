from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

RECIPE_NAME_MAX_LENGTH = 60
RECIPE_TEXT_MAX_LENGTH = 4098  # Description / Notes, per ticket spec.

INGREDIENT_NAME_MIN_LENGTH = 1
INGREDIENT_NAME_MAX_LENGTH = 30
INGREDIENT_QUANTITY_MIN = Decimal("0")  # exclusive
INGREDIENT_QUANTITY_MAX = Decimal("99")  # inclusive
INGREDIENT_COST_MIN = Decimal("0.00")  # inclusive
INGREDIENT_COST_MAX = Decimal("1000")  # inclusive

DIRECTION_STEP_MIN_LENGTH = 1
DIRECTION_STEP_MAX_LENGTH = 255

RECIPE_LIST_PAGE_SIZE = 15


class IngredientUnit(StrEnum):
    """Measurement types available for a recipe ingredient, US customary + metric."""

    TSP = "tsp"
    TBSP = "tbsp"
    CUP = "cup"
    FL_OZ = "fl_oz"
    PINT = "pint"
    QUART = "quart"
    GALLON = "gallon"
    OZ = "oz"
    LB = "lb"
    ML = "ml"
    L = "l"
    G = "g"
    KG = "kg"
    PINCH = "pinch"
    DASH = "dash"
    WHOLE = "whole"
    CLOVE = "clove"
    SLICE = "slice"
    CAN = "can"
    PACKAGE = "package"


class RecipeSortOrder(StrEnum):
    RECENTLY_ADDED = "recently_added"
    RECENTLY_USED = "recently_used"
    MOST_USED = "most_used"


def _is_blank_ingredient(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    name = str(item.get("name") or "").strip()
    unit = str(item.get("unit") or "").strip()
    return not name and not unit


def _is_blank_direction(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    return not str(item.get("step_text") or "").strip()


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return -exponent if isinstance(exponent, int) else 0


class RecipeIngredientIn(BaseModel):
    quantity: Decimal = Decimal("1")
    unit: IngredientUnit
    name: str
    cost: Decimal = Decimal("0.00")

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: Decimal) -> Decimal:
        if value <= INGREDIENT_QUANTITY_MIN or value > INGREDIENT_QUANTITY_MAX:
            raise ValueError("Quantity must be greater than 0 and no more than 99.")
        if _decimal_places(value) > 4:
            raise ValueError("Quantity supports at most 4 decimal places.")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not (INGREDIENT_NAME_MIN_LENGTH <= len(value) <= INGREDIENT_NAME_MAX_LENGTH):
            raise ValueError(
                f"Ingredient name must be {INGREDIENT_NAME_MIN_LENGTH}-"
                f"{INGREDIENT_NAME_MAX_LENGTH} characters."
            )
        return value

    @field_validator("cost")
    @classmethod
    def validate_cost(cls, value: Decimal) -> Decimal:
        if value < INGREDIENT_COST_MIN or value > INGREDIENT_COST_MAX:
            raise ValueError("Cost must be between 0.00 and 1000.00.")
        if _decimal_places(value) > 2:
            raise ValueError("Cost supports at most 2 decimal places.")
        return value


class RecipeIngredientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    quantity: Decimal
    unit: IngredientUnit
    name: str
    cost: Decimal


class RecipeDirectionIn(BaseModel):
    step_text: str

    @field_validator("step_text")
    @classmethod
    def validate_step_text(cls, value: str) -> str:
        value = value.strip()
        if not (DIRECTION_STEP_MIN_LENGTH <= len(value) <= DIRECTION_STEP_MAX_LENGTH):
            raise ValueError(
                f"Each direction step must be {DIRECTION_STEP_MIN_LENGTH}-"
                f"{DIRECTION_STEP_MAX_LENGTH} characters."
            )
        return value


class RecipeDirectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_text: str


class RecipeWrite(BaseModel):
    """Shared shape for create and edit: the ticket applies identical rules to both."""

    name: str
    description: str | None = None
    notes: str | None = None
    ingredients: list[RecipeIngredientIn] = []
    directions: list[RecipeDirectionIn] = []

    @model_validator(mode="before")
    @classmethod
    def filter_blank_entries(cls, data: object) -> object:
        """Silently drop ingredient/direction rows the user left entirely blank.

        Must run before per-item validation, since a blank row (e.g. no name,
        no unit) would otherwise fail required-field checks instead of being
        ignored, per the ticket's "don't throw an error unless at least one
        field has something in it" rule.
        """
        if not isinstance(data, dict):
            return data
        result = dict(data)
        ingredients = result.get("ingredients")
        if isinstance(ingredients, list):
            result["ingredients"] = [i for i in ingredients if not _is_blank_ingredient(i)]
        directions = result.get("directions")
        if isinstance(directions, list):
            result["directions"] = [d for d in directions if not _is_blank_direction(d)]
        return result

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not (1 <= len(value) <= RECIPE_NAME_MAX_LENGTH):
            raise ValueError(f"Recipe name must be 1-{RECIPE_NAME_MAX_LENGTH} characters.")
        return value

    @field_validator("description", "notes")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > RECIPE_TEXT_MAX_LENGTH:
            raise ValueError(f"Must be no more than {RECIPE_TEXT_MAX_LENGTH} characters.")
        return value

    @field_validator("ingredients")
    @classmethod
    def validate_ingredients_required(
        cls, value: list[RecipeIngredientIn]
    ) -> list[RecipeIngredientIn]:
        if not value:
            raise ValueError("At least one ingredient is required.")
        return value

    @field_validator("directions")
    @classmethod
    def validate_directions_required(
        cls, value: list[RecipeDirectionIn]
    ) -> list[RecipeDirectionIn]:
        if not value:
            raise ValueError("At least one direction step is required.")
        return value


class RecipeCreate(RecipeWrite):
    pass


class RecipeUpdate(RecipeWrite):
    pass


class RecipeRead(BaseModel):
    """Full recipe detail. Created/modified timestamps are intentionally omitted:
    the ticket stores them but explicitly says not to surface them in the UI."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    notes: str | None
    image_url: str | None = None
    ingredients: list[RecipeIngredientOut]
    directions: list[RecipeDirectionOut]
    # Name of the meal plan this recipe is scheduled in, via the meal_recipes
    # join (see app/db/models/meal_plan.py): the plan covering today if any,
    # else the most recently ended past plan. Null if never used in a meal.
    last_used_in_meal_plan: str | None = None


class RecipeListItem(BaseModel):
    """Card-view projection for the paginated recipe list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    image_url: str | None = None
    # See RecipeRead.last_used_in_meal_plan for how this is derived.
    last_used_in_meal_plan: str | None = None


class RecipeListPage(BaseModel):
    items: list[RecipeListItem]
    page_size: int
    has_more: bool
