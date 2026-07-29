from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate

TODAY = date.today()
VALID_DOB = TODAY.replace(year=TODAY.year - 25)


def _valid_payload(**overrides):
    payload = {
        "username": "validuser1",
        "password": "sup3rSecret!",
        "confirm_password": "sup3rSecret!",
        "first_name": "Jane",
        "last_name": "Doe",
        "date_of_birth": VALID_DOB,
        "agreed_to_terms": True,
    }
    payload.update(overrides)
    return payload


def test_valid_payload_passes():
    user = UserCreate(**_valid_payload())
    assert user.username == "validuser1"
    assert user.email_subscription_opt_in is True


@pytest.mark.parametrize("username", ["abcd", "a" * 33, "has spaces", "has-dash", ""])
def test_invalid_usernames_are_rejected(username):
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(username=username))


@pytest.mark.parametrize("password", ["short", "a" * 65])
def test_invalid_password_length_is_rejected(password):
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(password=password, confirm_password=password))


def test_mismatched_passwords_are_rejected():
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(password="sup3rSecret!", confirm_password="different!"))


@pytest.mark.parametrize("name", ["ab", "a" * 65, "has$ymbol"])
def test_invalid_names_are_rejected(name):
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(first_name=name))


def test_name_allows_dashes_underscores_and_spaces():
    user = UserCreate(**_valid_payload(first_name="Mary-Jane_Anne Doe"))
    assert user.first_name == "Mary-Jane_Anne Doe"


def test_future_date_of_birth_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(date_of_birth=TODAY + timedelta(days=1)))


def test_under_18_is_rejected():
    almost_18 = TODAY.replace(year=TODAY.year - 18) + timedelta(days=1)
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(date_of_birth=almost_18))


def test_exactly_18_today_is_accepted():
    turns_18_today = TODAY.replace(year=TODAY.year - 18)
    user = UserCreate(**_valid_payload(date_of_birth=turns_18_today))
    assert user.date_of_birth == turns_18_today


def test_must_agree_to_terms():
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(agreed_to_terms=False))


def test_valid_email_is_accepted():
    user = UserCreate(**_valid_payload(email="jane@example.com"))
    assert user.email == "jane@example.com"


def test_invalid_email_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(email="not-an-email"))


def test_valid_phone_number_is_accepted():
    user = UserCreate(**_valid_payload(phone_number="+1 (555) 123-4567"))
    assert user.phone_number == "+1 (555) 123-4567"


def test_invalid_phone_number_is_rejected():
    with pytest.raises(ValidationError):
        UserCreate(**_valid_payload(phone_number="abc"))


def test_email_and_phone_are_optional():
    user = UserCreate(**_valid_payload())
    assert user.email is None
    assert user.phone_number is None
