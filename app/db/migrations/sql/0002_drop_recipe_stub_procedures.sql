-- The original recipes stub (0001) was a minimal demo table (id, title,
-- description, created_at) with a trigger and a row-count procedure, never
-- wired up to any API endpoint. SCRUM-23 replaces it with a real schema
-- (owner_id, name, notes, image_path, updated_at, deleted_at) plus two new
-- child tables (recipe_ingredients, recipe_directions).
--
-- `Base.metadata.create_all(checkfirst=True)` only creates tables that don't
-- exist yet, so it won't alter an already-provisioned `recipes` table to the
-- new columns. By the time this file runs, `run_orm_migrations()` has
-- already created `recipe_ingredients`/`recipe_directions` fresh (they never
-- existed before), with FKs pointing at `recipes.id` -- so `recipes` can't be
-- dropped on its own; its two new (still-empty) child tables have to go
-- first. `run_migrations()` re-runs `run_orm_migrations()` after SQL
-- migrations, which recreates all three tables with the current schema.

DROP TABLE IF EXISTS recipe_ingredients;

DROP TABLE IF EXISTS recipe_directions;

DROP TABLE IF EXISTS recipes;

DROP PROCEDURE IF EXISTS get_recipe_count;
