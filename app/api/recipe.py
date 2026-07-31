from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.images import (
    ImageValidationError,
    delete_recipe_image,
    image_url,
    save_recipe_image,
)
from app.db.models.meal_plan import Meal, MealPlan, MealRecipe
from app.db.models.recipe import Recipe, RecipeDirection, RecipeIngredient
from app.db.models.user import User
from app.db.session import get_db
from app.logging_config import get_logger
from app.schemas.recipe import (
    RECIPE_LIST_PAGE_SIZE,
    RecipeCreate,
    RecipeDirectionOut,
    RecipeIngredientOut,
    RecipeListItem,
    RecipeListPage,
    RecipeRead,
    RecipeSortOrder,
    RecipeUpdate,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _get_owned_recipe(db: Session, recipe_id: int, owner: User) -> Recipe:
    recipe = (
        db.query(Recipe)
        .filter(Recipe.id == recipe_id, Recipe.owner_id == owner.id, Recipe.deleted_at.is_(None))
        .first()
    )
    if recipe is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipe not found.")
    return recipe


def _last_used_in_meal_plan(db: Session, recipe_id: int) -> str | None:
    """The meal plan this recipe is scheduled in: the one covering today, if
    any, else the most recently ended past one. See app/schemas/recipe.py."""
    today = date.today()

    def _joined_plans(db: Session):
        return (
            db.query(MealPlan)
            .join(Meal, Meal.meal_plan_id == MealPlan.id)
            .join(MealRecipe, MealRecipe.meal_id == Meal.id)
            .filter(MealRecipe.recipe_id == recipe_id, MealPlan.deleted_at.is_(None))
        )

    current = (
        _joined_plans(db)
        .filter(MealPlan.start_date <= today, MealPlan.end_date >= today)
        .order_by(MealPlan.start_date.asc())
        .first()
    )
    if current is not None:
        return current.name

    past = (
        _joined_plans(db)
        .filter(MealPlan.end_date < today)
        .order_by(MealPlan.end_date.desc())
        .first()
    )
    return past.name if past is not None else None


def _to_recipe_read(db: Session, recipe: Recipe) -> RecipeRead:
    return RecipeRead(
        id=recipe.id,
        name=recipe.name,
        description=recipe.description,
        notes=recipe.notes,
        image_url=image_url(recipe.image_path),
        ingredients=[RecipeIngredientOut.model_validate(i) for i in recipe.ingredients],
        directions=[RecipeDirectionOut.model_validate(d) for d in recipe.directions],
        last_used_in_meal_plan=_last_used_in_meal_plan(db, recipe.id),
    )


def _to_recipe_list_item(db: Session, recipe: Recipe) -> RecipeListItem:
    return RecipeListItem(
        id=recipe.id,
        name=recipe.name,
        description=recipe.description,
        image_url=image_url(recipe.image_path),
        last_used_in_meal_plan=_last_used_in_meal_plan(db, recipe.id),
    )


def _apply_ingredients_and_directions(recipe: Recipe, recipe_in: RecipeCreate | RecipeUpdate) -> None:
    recipe.ingredients = [
        RecipeIngredient(
            position=position,
            quantity=item.quantity,
            unit=item.unit.value,
            name=item.name,
            cost=item.cost,
        )
        for position, item in enumerate(recipe_in.ingredients)
    ]
    recipe.directions = [
        RecipeDirection(position=position, step_text=item.step_text)
        for position, item in enumerate(recipe_in.directions)
    ]


@router.get(
    "",
    response_model=RecipeListPage,
    summary="List the current user's recipes",
    response_description="A page of recipe cards plus whether more pages remain",
)
def list_recipes(
    sort: RecipeSortOrder = Query(
        RecipeSortOrder.RECENTLY_ADDED, description="Sort order for the recipe list."
    ),
    offset: int = Query(0, ge=0, description="Number of recipes to skip, for pagination."),
    limit: int = Query(
        RECIPE_LIST_PAGE_SIZE, ge=1, le=50, description="Page size (defaults to 15)."
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeListPage:
    """Paginated, card-view list of the caller's own (non-deleted) recipes.

    `sort=recently_used` orders by the latest scheduled day (`meals.day`) a
    recipe was attached to via `meal_recipes`; `sort=most_used` orders by how
    many `meal_recipes` rows reference it (each meal a recipe is attached to
    counts once, so the same recipe on 3 different days counts as 3). Recipes
    never used sort after ones that have been, in both cases.
    """
    query = (
        db.query(Recipe)
        .outerjoin(MealRecipe, MealRecipe.recipe_id == Recipe.id)
        .outerjoin(Meal, Meal.id == MealRecipe.meal_id)
        .filter(Recipe.owner_id == current_user.id, Recipe.deleted_at.is_(None))
        .group_by(Recipe.id)
    )
    if sort == RecipeSortOrder.RECENTLY_USED:
        last_used = func.max(Meal.day)
        query = query.order_by(
            last_used.is_(None), last_used.desc(), Recipe.created_at.desc(), Recipe.id.desc()
        )
    elif sort == RecipeSortOrder.MOST_USED:
        usage_count = func.count(MealRecipe.id)
        query = query.order_by(usage_count.desc(), Recipe.created_at.desc(), Recipe.id.desc())
    else:
        query = query.order_by(Recipe.created_at.desc(), Recipe.id.desc())

    rows = query.offset(offset).limit(limit + 1).all()
    has_more = len(rows) > limit
    items = [_to_recipe_list_item(db, recipe) for recipe in rows[:limit]]
    return RecipeListPage(items=items, page_size=limit, has_more=has_more)


@router.post(
    "",
    response_model=RecipeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a recipe",
    response_description="The newly created recipe",
)
def create_recipe(
    recipe_in: RecipeCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeRead:
    """Create a new recipe owned by the current user."""
    recipe = Recipe(
        owner_id=current_user.id,
        name=recipe_in.name,
        description=recipe_in.description,
        notes=recipe_in.notes,
    )
    _apply_ingredients_and_directions(recipe, recipe_in)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    logger.info("User %s created recipe %d", current_user.username, recipe.id)
    return _to_recipe_read(db, recipe)


@router.get(
    "/{recipe_id}",
    response_model=RecipeRead,
    summary="Get a single recipe",
    response_description="The full recipe, including ingredients and directions",
)
def get_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeRead:
    recipe = _get_owned_recipe(db, recipe_id, current_user)
    return _to_recipe_read(db, recipe)


@router.put(
    "/{recipe_id}",
    response_model=RecipeRead,
    summary="Replace a recipe's editable fields",
    response_description="The updated recipe",
)
def update_recipe(
    recipe_id: int,
    recipe_in: RecipeUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeRead:
    """Full-replace update: the same validation rules as create apply, and the
    entire ingredients/directions lists are replaced with the ones supplied."""
    recipe = _get_owned_recipe(db, recipe_id, current_user)
    recipe.name = recipe_in.name
    recipe.description = recipe_in.description
    recipe.notes = recipe_in.notes
    recipe.updated_at = datetime.now(timezone.utc)
    _apply_ingredients_and_directions(recipe, recipe_in)
    db.commit()
    db.refresh(recipe)
    logger.info("User %s updated recipe %d", current_user.username, recipe.id)
    return _to_recipe_read(db, recipe)


@router.delete(
    "/{recipe_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a recipe",
    response_description="No content",
)
def delete_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """Soft-deletes the recipe (sets `deleted_at`); it's excluded from all reads
    from this point on, but the row and its timestamp are retained in the DB."""
    recipe = _get_owned_recipe(db, recipe_id, current_user)
    recipe.deleted_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("User %s deleted recipe %d", current_user.username, recipe.id)


@router.post(
    "/{recipe_id}/image",
    response_model=RecipeRead,
    summary="Upload or replace a recipe's photo",
    response_description="The recipe with its new image URL",
)
async def upload_recipe_image(
    recipe_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeRead:
    """Accepts a single JPEG/PNG/GIF/WEBP image up to 2MB, replacing any existing photo."""
    recipe = _get_owned_recipe(db, recipe_id, current_user)
    try:
        relative_path = await save_recipe_image(file)
    except ImageValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    previous_path = recipe.image_path
    recipe.image_path = relative_path
    recipe.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(recipe)
    if previous_path is not None:
        delete_recipe_image(previous_path)
    logger.info("User %s uploaded image for recipe %d", current_user.username, recipe.id)
    return _to_recipe_read(db, recipe)


@router.delete(
    "/{recipe_id}/image",
    response_model=RecipeRead,
    summary="Remove a recipe's photo",
    response_description="The recipe with its image removed",
)
def delete_recipe_image_endpoint(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecipeRead:
    recipe = _get_owned_recipe(db, recipe_id, current_user)
    if recipe.image_path is not None:
        delete_recipe_image(recipe.image_path)
        recipe.image_path = None
        recipe.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(recipe)
    return _to_recipe_read(db, recipe)
