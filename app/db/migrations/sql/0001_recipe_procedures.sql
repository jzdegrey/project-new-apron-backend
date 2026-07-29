-- Example stored procedure + trigger, kept idempotent via DROP ... IF EXISTS
-- since MySQL has no CREATE PROCEDURE/TRIGGER IF NOT EXISTS syntax.

DROP PROCEDURE IF EXISTS get_recipe_count;

CREATE PROCEDURE get_recipe_count(OUT recipe_count INT)
BEGIN
    SELECT COUNT(*) INTO recipe_count FROM recipes;
END;

DROP TRIGGER IF EXISTS recipes_before_insert;

CREATE TRIGGER recipes_before_insert
BEFORE INSERT ON recipes
FOR EACH ROW
SET NEW.title = TRIM(NEW.title);
