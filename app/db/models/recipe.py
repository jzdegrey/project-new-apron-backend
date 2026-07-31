from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Recipe(Base):
    """A user-owned recipe: name/description/notes plus ordered ingredients and directions."""

    __tablename__ = "recipes"
    __table_args__ = (
        Index("ix_recipes_owner_id", "owner_id"),
        Index("ix_recipes_owner_id_deleted_at", "owner_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4098), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(4098), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Soft-delete marker. Never surfaced in API responses or the UI.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        "RecipeIngredient",
        back_populates="recipe",
        order_by="RecipeIngredient.position",
        cascade="all, delete-orphan",
    )
    directions: Mapped[list["RecipeDirection"]] = relationship(
        "RecipeDirection",
        back_populates="recipe",
        order_by="RecipeDirection.position",
        cascade="all, delete-orphan",
    )


class RecipeIngredient(Base):
    """A single ingredient line within a recipe, in display order."""

    __tablename__ = "recipe_ingredients"
    __table_args__ = (Index("ix_recipe_ingredients_recipe_id", "recipe_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    quantity: Mapped["Numeric"] = mapped_column(Numeric(6, 4), nullable=False, server_default="1")
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(30), nullable=False)
    # Not shown on the frontend yet; reserved for future cost/shopping-list features.
    cost: Mapped["Numeric"] = mapped_column(Numeric(6, 2), nullable=False, server_default="0.00")

    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")


class RecipeDirection(Base):
    """A single numbered step within a recipe, in display order."""

    __tablename__ = "recipe_directions"
    __table_args__ = (Index("ix_recipe_directions_recipe_id", "recipe_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_text: Mapped[str] = mapped_column(String(255), nullable=False)

    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="directions")
