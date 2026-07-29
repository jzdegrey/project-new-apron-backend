import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9]{5,32}$")
NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{3,64}$")
PHONE_RE = re.compile(r"^\+?[0-9()\-.\s]{7,20}$")

MIN_AGE_YEARS = 18


def _age_in_years(dob: date, today: date) -> int:
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


class UserBase(BaseModel):
    username: str
    first_name: str
    last_name: str
    date_of_birth: date
    email: EmailStr | None = None
    phone_number: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not USERNAME_RE.match(value):
            raise ValueError(
                "Username must be 5-32 characters and contain only letters and numbers."
            )
        return value

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not NAME_RE.match(value):
            raise ValueError(
                "Must be 3-64 characters and contain only letters, numbers, spaces, "
                "dashes, and underscores."
            )
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date) -> date:
        today = datetime.now(timezone.utc).date()
        if value > today:
            raise ValueError("Date of birth cannot be in the future.")
        if _age_in_years(value, today) < MIN_AGE_YEARS:
            raise ValueError(f"You must be at least {MIN_AGE_YEARS} years old to register.")
        return value

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not PHONE_RE.match(value):
            raise ValueError("Enter a valid phone number.")
        return value


class UserCreate(UserBase):
    password: str
    confirm_password: str
    agreed_to_terms: bool
    email_subscription_opt_in: bool = True

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not (6 <= len(value) <= 64):
            raise ValueError("Password must be 6-64 characters.")
        return value

    @field_validator("agreed_to_terms")
    @classmethod
    def validate_agreed_to_terms(cls, value: bool) -> bool:
        if not value:
            raise ValueError("You must agree to the Terms of Service and Privacy Policy.")
        return value

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "UserCreate":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email_subscription_opt_in: bool
    created_at: datetime
