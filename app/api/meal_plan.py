from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.images import image_url
from app.db.models.meal_plan import Meal, MealPlan, MealRecipe
from app.db.models.recipe import Recipe
from app.db.models.user import User
from app.db.session import get_db
from app.logging_config import get_logger
from app.schemas.meal_plan import (
    MEAL_PLAN_LIST_PAGE_SIZE,
    MEAL_TYPE_SORT_ORDER,
    MealCreate,
    MealOut,
    MealPlanCreate,
    MealPlanListItem,
    MealPlanListPage,
    MealPlanRead,
    MealPlanUpdate,
    MealRecipeAttach,
    MealRecipeOut,
    MealType,
    MealUpdate,
    default_meal_plan_name,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/meal-plans", tags=["meal-plans"])


def _get_owned_meal_plan(db: Session, meal_plan_id: int, owner: User) -> MealPlan:
    meal_plan = (
        db.query(MealPlan)
        .filter(
            MealPlan.id == meal_plan_id,
            MealPlan.owner_id == owner.id,
            MealPlan.deleted_at.is_(None),
        )
        .first()
    )
    if meal_plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal plan not found.")
    return meal_plan


def _get_meal_in_plan(db: Session, meal_plan: MealPlan, meal_id: int) -> Meal:
    meal = (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.meal_plan_id == meal_plan.id)
        .first()
    )
    if meal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meal not found.")
    return meal


def _validate_meal_day_in_range(meal_plan: MealPlan, day: date) -> None:
    if day < meal_plan.start_date or day > meal_plan.end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The meal's day must fall within the meal plan's date range.",
        )


def _validate_meal_type_unique_for_day(
    db: Session,
    meal_plan_id: int,
    meal_type: MealType,
    day: date,
    exclude_meal_id: int | None,
) -> None:
    query = db.query(Meal.id).filter(
        Meal.meal_plan_id == meal_plan_id, Meal.meal_type == meal_type.value, Meal.day == day
    )
    if exclude_meal_id is not None:
        query = query.filter(Meal.id != exclude_meal_id)
    if query.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A {meal_type.value} meal already exists for this day.",
        )


def _to_meal_recipe_out(meal_recipe: MealRecipe) -> MealRecipeOut:
    return MealRecipeOut(
        id=meal_recipe.recipe.id,
        name=meal_recipe.recipe.name,
        image_url=image_url(meal_recipe.recipe.image_path),
    )


def _to_meal_out(meal: Meal) -> MealOut:
    return MealOut(
        id=meal.id,
        meal_type=MealType(meal.meal_type),
        day=meal.day,
        recipes=[_to_meal_recipe_out(mr) for mr in meal.meal_recipes],
    )


def _to_meal_plan_read(meal_plan: MealPlan) -> MealPlanRead:
    sorted_meals = sorted(
        meal_plan.meals,
        key=lambda meal: (meal.day, MEAL_TYPE_SORT_ORDER[MealType(meal.meal_type)]),
    )
    return MealPlanRead(
        id=meal_plan.id,
        name=meal_plan.name,
        description=meal_plan.description,
        start_date=meal_plan.start_date,
        end_date=meal_plan.end_date,
        created_at=meal_plan.created_at,
        updated_at=meal_plan.updated_at,
        meals=[_to_meal_out(meal) for meal in sorted_meals],
    )


def _to_meal_plan_list_item(meal_plan: MealPlan, meal_count: int) -> MealPlanListItem:
    return MealPlanListItem(
        id=meal_plan.id,
        name=meal_plan.name,
        description=meal_plan.description,
        start_date=meal_plan.start_date,
        end_date=meal_plan.end_date,
        meal_count=meal_count,
    )


def _meal_counts_for(db: Session, meal_plan_ids: list[int]) -> dict[int, int]:
    if not meal_plan_ids:
        return {}
    rows = (
        db.query(Meal.meal_plan_id, func.count(Meal.id))
        .filter(Meal.meal_plan_id.in_(meal_plan_ids))
        .group_by(Meal.meal_plan_id)
        .all()
    )
    return dict(rows)


@router.get(
    "",
    response_model=MealPlanListPage,
    summary="List the current user's meal plans",
    response_description="A page of meal plan cards plus whether more pages remain",
)
def list_meal_plans(
    offset: int = Query(0, ge=0, description="Number of meal plans to skip, for pagination."),
    limit: int = Query(
        MEAL_PLAN_LIST_PAGE_SIZE, ge=1, le=50, description="Page size (defaults to 15)."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealPlanListPage:
    """Paginated, card-view list of the caller's own (non-deleted) meal plans.

    Ordered so that plans covering today come first, then upcoming plans, then
    past plans (each group ascending by start date). The frontend still does
    the authoritative current/upcoming/past bucketing against the viewer's
    local date — this ordering just keeps that bucketing coherent across
    pages of an infinite scroll.
    """
    today = date.today()
    bucket = case(
        (and_(MealPlan.start_date <= today, MealPlan.end_date >= today), 0),
        (MealPlan.start_date > today, 1),
        else_=2,
    )
    query = (
        db.query(MealPlan)
        .filter(MealPlan.owner_id == current_user.id, MealPlan.deleted_at.is_(None))
        .order_by(bucket, MealPlan.start_date.asc(), MealPlan.id.asc())
    )

    rows = query.offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    plans = rows[:limit]
    meal_counts = _meal_counts_for(db, [plan.id for plan in plans])
    items = [_to_meal_plan_list_item(plan, meal_counts.get(plan.id, 0)) for plan in plans]
    return MealPlanListPage(items=items, page_size=limit, has_more=has_more)


@router.post(
    "",
    response_model=MealPlanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a meal plan",
    response_description="The newly created meal plan",
)
def create_meal_plan(
    meal_plan_in: MealPlanCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealPlanRead:
    """Create a new meal plan owned by the current user. Meals aren't accepted
    here by design; add them afterward via the meals endpoints below."""
    name = meal_plan_in.name or default_meal_plan_name(meal_plan_in.start_date, meal_plan_in.end_date)
    meal_plan = MealPlan(
        owner_id=current_user.id,
        name=name,
        description=meal_plan_in.description,
        start_date=meal_plan_in.start_date,
        end_date=meal_plan_in.end_date,
    )
    db.add(meal_plan)
    db.commit()
    db.refresh(meal_plan)
    logger.info("User %s created meal plan %d", current_user.username, meal_plan.id)
    return _to_meal_plan_read(meal_plan)


@router.get(
    "/{meal_plan_id}",
    response_model=MealPlanRead,
    summary="Get a single meal plan",
    response_description="The full meal plan, including its meals and their recipes",
)
def get_meal_plan(
    meal_plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealPlanRead:
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    return _to_meal_plan_read(meal_plan)


@router.put(
    "/{meal_plan_id}",
    response_model=MealPlanRead,
    summary="Update a meal plan's name, description, or date range",
    response_description="The updated meal plan",
)
def update_meal_plan(
    meal_plan_id: int,
    meal_plan_in: MealPlanUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealPlanRead:
    """Only name/description/start_date/end_date are editable here — the
    ticket explicitly disallows editing the meals list from this endpoint."""
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)

    out_of_range_days = [
        meal.day
        for meal in meal_plan.meals
        if meal.day < meal_plan_in.start_date or meal.day > meal_plan_in.end_date
    ]
    if out_of_range_days:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The new date range must still include every existing meal's day.",
        )

    meal_plan.name = meal_plan_in.name or default_meal_plan_name(
        meal_plan_in.start_date, meal_plan_in.end_date
    )
    meal_plan.description = meal_plan_in.description
    meal_plan.start_date = meal_plan_in.start_date
    meal_plan.end_date = meal_plan_in.end_date
    meal_plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(meal_plan)
    logger.info("User %s updated meal plan %d", current_user.username, meal_plan.id)
    return _to_meal_plan_read(meal_plan)


@router.delete(
    "/{meal_plan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a meal plan",
    response_description="No content",
)
def delete_meal_plan(
    meal_plan_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-deletes the meal plan (sets `deleted_at`); it and its meals are
    excluded from all reads from this point on, but the rows are retained."""
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    meal_plan.deleted_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("User %s deleted meal plan %d", current_user.username, meal_plan.id)


@router.post(
    "/{meal_plan_id}/meals",
    response_model=MealOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a meal to a meal plan",
    response_description="The newly created meal",
)
def create_meal(
    meal_plan_id: int,
    meal_in: MealCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealOut:
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    _validate_meal_day_in_range(meal_plan, meal_in.day)
    _validate_meal_type_unique_for_day(db, meal_plan.id, meal_in.meal_type, meal_in.day, None)

    meal = Meal(meal_plan_id=meal_plan.id, meal_type=meal_in.meal_type.value, day=meal_in.day)
    db.add(meal)
    db.commit()
    db.refresh(meal)
    logger.info("User %s added meal %d to meal plan %d", current_user.username, meal.id, meal_plan.id)
    return _to_meal_out(meal)


@router.put(
    "/{meal_plan_id}/meals/{meal_id}",
    response_model=MealOut,
    summary="Update a meal's type or day",
    response_description="The updated meal",
)
def update_meal(
    meal_plan_id: int,
    meal_id: int,
    meal_in: MealUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealOut:
    """Only meal_type/day are editable — recipes are managed via the
    attach/detach endpoints below."""
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    meal = _get_meal_in_plan(db, meal_plan, meal_id)
    _validate_meal_day_in_range(meal_plan, meal_in.day)
    _validate_meal_type_unique_for_day(db, meal_plan.id, meal_in.meal_type, meal_in.day, meal.id)

    meal.meal_type = meal_in.meal_type.value
    meal.day = meal_in.day
    db.commit()
    db.refresh(meal)
    logger.info("User %s updated meal %d", current_user.username, meal.id)
    return _to_meal_out(meal)


@router.delete(
    "/{meal_plan_id}/meals/{meal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a meal",
    response_description="No content",
)
def delete_meal(
    meal_plan_id: int,
    meal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Hard-deletes the meal (and, via cascade, its attached-recipe rows) —
    unlike recipes/meal plans, meals have no soft-delete/undo requirement."""
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    meal = _get_meal_in_plan(db, meal_plan, meal_id)
    db.delete(meal)
    db.commit()
    logger.info("User %s deleted meal %d", current_user.username, meal_id)


@router.post(
    "/{meal_plan_id}/meals/{meal_id}/recipes",
    response_model=MealOut,
    summary="Attach a recipe to a meal",
    response_description="The meal with its updated recipe list",
)
def attach_recipe_to_meal(
    meal_plan_id: int,
    meal_id: int,
    attach_in: MealRecipeAttach,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealOut:
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    meal = _get_meal_in_plan(db, meal_plan, meal_id)
    recipe = (
        db.query(Recipe)
        .filter(
            Recipe.id == attach_in.recipe_id,
            Recipe.owner_id == current_user.id,
            Recipe.deleted_at.is_(None),
        )
        .first()
    )
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found.")

    already_attached = any(mr.recipe_id == recipe.id for mr in meal.meal_recipes)
    if not already_attached:
        db.add(MealRecipe(meal_id=meal.id, recipe_id=recipe.id))
        db.commit()
        db.refresh(meal)
        logger.info(
            "User %s attached recipe %d to meal %d", current_user.username, recipe.id, meal.id
        )
    return _to_meal_out(meal)


@router.delete(
    "/{meal_plan_id}/meals/{meal_id}/recipes/{recipe_id}",
    response_model=MealOut,
    summary="Detach a recipe from a meal",
    response_description="The meal with its updated recipe list",
)
def detach_recipe_from_meal(
    meal_plan_id: int,
    meal_id: int,
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MealOut:
    meal_plan = _get_owned_meal_plan(db, meal_plan_id, current_user)
    meal = _get_meal_in_plan(db, meal_plan, meal_id)
    meal_recipe = next((mr for mr in meal.meal_recipes if mr.recipe_id == recipe_id), None)
    if meal_recipe is not None:
        db.delete(meal_recipe)
        db.commit()
        db.refresh(meal)
        logger.info(
            "User %s detached recipe %d from meal %d", current_user.username, recipe_id, meal.id
        )
    return _to_meal_out(meal)
