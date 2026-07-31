from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RecipeBase(BaseModel):
    title: str
    description: str | None = None


class RecipeCreate(RecipeBase):
    pass


class RecipeRead(RecipeBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
