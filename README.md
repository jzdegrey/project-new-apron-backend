# project-new-apron-backend

Backend API for Project New Apron, built with FastAPI, Pydantic, SQLAlchemy, and Typer.

## Stack

- Python 3.14
- [FastAPI](https://fastapi.tiangolo.com/) + [Pydantic](https://docs.pydantic.dev/) — API layer and settings/schema validation
- [SQLAlchemy](https://www.sqlalchemy.org/) — ORM against a MySQL database
- [Typer](https://typer.tiangolo.com/) — CLI (migrations, running the dev server)
- MySQL 8

## Project layout

```
app/
  globals.py         # Settings (env vars + .env), incl. secrets and the ENV switch
  logging_config.py  # Console (+ local file) logging setup
  main.py            # FastAPI app, OpenAPI docs at /docs and /redoc
  cli.py              # Typer CLI: `python -m app.cli migrate|runserver`
  core/
    security.py       # Password hashing (bcrypt) + JWT access-token helpers
  api/                # Routers
    auth.py            # Register/login/me endpoints
    deps.py            # `get_current_user` (bearer token) dependency
  db/
    base.py           # SQLAlchemy declarative base
    session.py        # Engine/session + FastAPI `get_db` dependency
    models/           # ORM models
    migrate.py         # Idempotent migration runner (ORM tables/indexes + raw SQL)
    migrations/sql/    # Raw .sql migrations (stored procedures, triggers, ...)
  schemas/            # Pydantic request/response schemas
tests/
```

## Authentication

Auth follows the OAuth2 password-bearer flow (see FastAPI's own tutorial for this
pattern): clients exchange a username/password for a short-lived JWT bearer token,
then send that token as `Authorization: Bearer <token>` on subsequent requests.

- `POST /api/v1/auth/register` — create an account. Body validation (username,
  password, name, date-of-birth, optional email/phone, terms acceptance, etc.)
  lives in `app.schemas.user.UserCreate` and mirrors the rules enforced
  client-side in the frontend and react-native apps.
- `POST /api/v1/auth/login` — OAuth2 password flow (`application/x-www-form-urlencoded`
  `username`/`password`), returns a bearer `access_token`. After
  `LOGIN_LOCKOUT_THRESHOLD` consecutive failed attempts, further attempts are
  rejected with `423 Locked` under an exponential backoff (doubling each
  additional failure) until the lockout expires.
- `GET /api/v1/auth/me` — returns the authenticated user (requires a bearer token).

Passwords are hashed with bcrypt and never stored or returned in plaintext.

## Configuration

All configuration is read through `app.globals.settings`, which loads from process
env vars first and then a `.env` file. Copy `.env.example` to `.env` and fill in
real values before running locally; never commit `.env`.

`ENV` must be one of `local`, `stg`, or `prod`. When `ENV=local`, logs are also
written to `logs/app.log` in addition to the console; in `stg`/`prod` logging is
console-only.

## Running locally

### With Docker Compose (recommended)

```bash
cp .env.example .env
docker compose up --build
```

This starts the API (`http://localhost:8000`) and a MySQL 8 instance. Interactive
API docs are available at `/docs` (Swagger UI) and `/redoc`.

### Without Docker

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # point DB_HOST at a MySQL instance you have running
python -m app.cli migrate
python -m app.cli runserver --reload
```

## Migrations

```bash
python -m app.cli migrate
```

This is idempotent and safe to re-run: it creates ORM-managed tables/indexes via
`Base.metadata.create_all(checkfirst=True)`, then applies any new raw `.sql`
files under `app/db/migrations/sql/` (for stored procedures, triggers, etc.),
tracking what's already been applied in a `schema_migrations` table.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
