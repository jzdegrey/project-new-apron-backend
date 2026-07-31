from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User
from app.db.session import get_db
from app.globals import settings
from app.logging_config import get_logger
from app.schemas.auth import Token
from app.schemas.user import UserCreate, UserRead

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Bcrypt hash of an unguessable placeholder, used to keep the login-failure
# code path's timing similar whether or not the username exists.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password-used-for-timing-only")


def _lockout_duration(failed_attempts: int) -> timedelta:
    """Exponential backoff: the (threshold + 1)th failure locks for `base` minutes,
    doubling for each failure after that.
    """
    overage = failed_attempts - settings.login_lockout_threshold - 1
    minutes = settings.login_lockout_base_minutes * (2**max(overage, 0))
    return timedelta(minutes=minutes)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_in: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.username == user_in.username).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Username is already taken."
        )
    if user_in.email is not None:
        if db.query(User).filter(User.email == user_in.email).first() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email is already registered."
            )

    user = User(
        username=user_in.username,
        password_hash=hash_password(user_in.password),
        first_name=user_in.first_name,
        last_name=user_in.last_name,
        date_of_birth=user_in.date_of_birth,
        email=user_in.email,
        phone_number=user_in.phone_number,
        terms_accepted_at=datetime.now(timezone.utc),
        email_subscription_opt_in=user_in.email_subscription_opt_in,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Registered new user %s", user.username)
    return user


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    invalid_credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user = db.query(User).filter(User.username == form_data.username).first()

    if user is not None and user.locked_until is not None:
        now = datetime.now(timezone.utc)
        locked_until = user.locked_until.replace(tzinfo=timezone.utc)
        if locked_until > now:
            retry_after_seconds = int((locked_until - now).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=(
                    "Too many failed login attempts. "
                    f"Try again in {max(retry_after_seconds, 1)} seconds."
                ),
                headers={"Retry-After": str(max(retry_after_seconds, 1))},
            )

    password_hash = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_ok = verify_password(form_data.password, password_hash)

    if user is None or not password_ok:
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts > settings.login_lockout_threshold:
                user.locked_until = datetime.now(timezone.utc) + _lockout_duration(
                    user.failed_login_attempts
                )
            db.commit()
            logger.warning(
                "Failed login for user %s (attempt %d)", user.username, user.failed_login_attempts
            )
        raise invalid_credentials_error

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    access_token = create_access_token(subject=user.username)
    logger.info("User %s logged in", user.username)
    return Token(access_token=access_token)


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
