from app.schemas.auth import LoginRequest


def test_login_request_normalizes_username() -> None:
    payload = LoginRequest(username="  Admin  ", password="secret")

    assert payload.username == "admin"
