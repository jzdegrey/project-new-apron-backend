-- This file previously created a demo trigger/procedure against the old
-- `recipes` stub schema (id, title, description, created_at). SCRUM-23
-- replaced that schema entirely (see 0002), and this trigger's
-- `SET NEW.title = ...` body now references a column that no longer exists
-- on a fresh install -- create_all's first pass already builds the new
-- schema before any .sql file runs, so a fresh DB never has `title` at all.
--
-- Rewriting an applied migration is normally off-limits, but it's safe here:
-- `schema_migrations` tracks files by filename, so any environment where
-- this already ran (and holds "0001_recipe_procedures.sql") skips it
-- unconditionally and never re-executes this content. Only environments that
-- have *never* migrated before -- where the old trigger was never created in
-- the first place -- run this file's body, so turning it into a no-op only
-- changes behavior exactly where the old body would otherwise fail. 0002
-- handles dropping the trigger/procedure in environments where the original
-- version of this file did create them.

SELECT 1;
