from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

MEAL_PLAN_NAME_MAX_LENGTH = 120
MEAL_PLAN_TEXT_MAX_LENGTH = 4098  # Description, matching the recipe description/notes limit.
MEAL_PLAN_MIN_DAYS = 1
MEAL_PLAN_MAX_DAYS = 30

MEAL_PLAN_LIST_PAGE_SIZE = 15


class MealType(StrEnum):
    """A meal's time-of-day slot. Sort order (Breakfast, Brunch, Lunch, Dinner,
    Dessert, Snack) is the order the values are declared in, per the ticket's
    'View Meal Plan Page' sort spec."""

    BREAKFAST = "breakfast"
    BRUNCH = "brunch"
    LUNCH = "lunch"
    DINNER = "dinner"
    DESSERT = "dessert"
    SNACK = "snack"


MEAL_TYPE_SORT_ORDER: dict[MealType, int] = {
    meal_type: index for index, meal_type in enumerate(MealType)
}

# Default-next-meal suggestion order per the ticket: Breakfast, Lunch, and
# Dinner are the "core" meals; once all three are taken for a day, offer
# Dessert, then Snack, then Brunch last.
MEAL_TYPE_DEFAULT_SUGGESTION_ORDER: list[MealType] = [
    MealType.BREAKFAST,
    MealType.LUNCH,
    MealType.DINNER,
    MealType.DESSERT,
    MealType.SNACK,
    MealType.BRUNCH,
]


def default_meal_plan_name(start_date: date, end_date: date) -> str:
    return (
        f"Meal Plan for {start_date.strftime('%B')} {start_date.day} "
        f"to {end_date.strftime('%B')} {end_date.day}"
    )


class MealPlanWrite(BaseModel):
    """Shared shape for create and edit: the ticket applies identical rules to both.
    Deliberately excludes the meals list — meals are managed via their own endpoints."""

    name: str | None = None
    description: str | None = None
    start_date: date
    end_date: date

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > MEAL_PLAN_NAME_MAX_LENGTH:
            raise ValueError(f"Meal plan name must be no more than {MEAL_PLAN_NAME_MAX_LENGTH} characters.")
        return value

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > MEAL_PLAN_TEXT_MAX_LENGTH:
            raise ValueError(f"Must be no more than {MEAL_PLAN_TEXT_MAX_LENGTH} characters.")
        return value

    @model_validator(mode="after")
    def validate_date_range(self) -> "MealPlanWrite":
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date.")
        duration_days = (self.end_date - self.start_date).days + 1
        if duration_days < MEAL_PLAN_MIN_DAYS or duration_days > MEAL_PLAN_MAX_DAYS:
            raise ValueError(
                f"Meal plan range must be between {MEAL_PLAN_MIN_DAYS} and "
                f"{MEAL_PLAN_MAX_DAYS} days."
            )
        return self


class MealPlanCreate(MealPlanWrite):
    pass


class MealPlanUpdate(MealPlanWrite):
    pass


class MealRecipeOut(BaseModel):
    """Brief recipe projection for display inside a meal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    image_url: str | None = None


class MealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meal_type: MealType
    day: date
    recipes: list[MealRecipeOut]


class MealPlanRead(BaseModel):
    """Full meal plan detail, including its meals (sorted by day, then meal
    type). Created/modified timestamps are surfaced here only, per the ticket;
    deleted_at is never surfaced."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime
    meals: list[MealOut]


class MealPlanListItem(BaseModel):
    """Card-view projection for the paginated meal plan list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    start_date: date
    end_date: date
    meal_count: int


class MealPlanListPage(BaseModel):
    items: list[MealPlanListItem]
    page_size: int
    has_more: bool


class MealCreate(BaseModel):
    meal_type: MealType
    day: date


class MealUpdate(BaseModel):
    meal_type: MealType
    day: date


class MealRecipeAttach(BaseModel):
    recipe_id: int
