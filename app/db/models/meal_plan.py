from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MealPlan(Base):
    """A user-owned meal plan: a named date range containing zero or more meals."""

    __tablename__ = "meal_plans"
    __table_args__ = (
        Index("ix_meal_plans_owner_id", "owner_id"),
        Index("ix_meal_plans_owner_id_deleted_at", "owner_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4098), nullable=True)
    # Date-only (no time): the ticket stores these as UTC dates, converted to
    # local time for display, but since there's no time component there's no
    # actual timezone math to do — the value is stored exactly as submitted.
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Soft-delete marker. Never surfaced in API responses or the UI.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    meals: Mapped[list["Meal"]] = relationship(
        "Meal",
        back_populates="meal_plan",
        order_by="Meal.day",
        cascade="all, delete-orphan",
    )


class Meal(Base):
    """A single meal (breakfast, lunch, ...) on a given day within a meal plan."""

    __tablename__ = "meals"
    __table_args__ = (
        Index("ix_meals_meal_plan_id", "meal_plan_id"),
        UniqueConstraint("meal_plan_id", "meal_type", "day", name="uq_meals_plan_type_day"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False
    )
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)

    meal_plan: Mapped["MealPlan"] = relationship("MealPlan", back_populates="meals")
    meal_recipes: Mapped[list["MealRecipe"]] = relationship(
        "MealRecipe",
        back_populates="meal",
        order_by="MealRecipe.id",
        cascade="all, delete-orphan",
    )


class MealRecipe(Base):
    """Join row attaching a Recipe to a Meal. A plain link — no extra state
    needed beyond when it was created, which drives 'recently used' sorting."""

    __tablename__ = "meal_recipes"
    __table_args__ = (
        Index("ix_meal_recipes_meal_id", "meal_id"),
        Index("ix_meal_recipes_recipe_id", "recipe_id"),
        UniqueConstraint("meal_id", "recipe_id", name="uq_meal_recipes_meal_recipe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meals.id", ondelete="CASCADE"), nullable=False
    )
    recipe_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    meal: Mapped["Meal"] = relationship("Meal", back_populates="meal_recipes")
    recipe: Mapped["Recipe"] = relationship("Recipe")
