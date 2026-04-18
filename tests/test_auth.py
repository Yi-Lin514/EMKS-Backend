from datetime import datetime, timedelta

from app.models import UserStatus
from app.services.auth import create_access_token, verify_token


def test_login_success_returns_tokens(client, make_user):
    make_user(email="alice@demo.com", password="secret123")

    res = client.post("/auth/login", json={"email": "alice@demo.com", "password": "secret123"})

    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["email"] == "alice@demo.com"


def test_login_wrong_password_returns_401(client, make_user):
    make_user(email="bob@demo.com", password="correct")

    res = client.post("/auth/login", json={"email": "bob@demo.com", "password": "wrong"})

    assert res.status_code == 401


def test_login_unknown_email_returns_401(client):
    res = client.post("/auth/login", json={"email": "ghost@demo.com", "password": "x"})

    assert res.status_code == 401


def test_login_locked_account_returns_423(client, make_user, db):
    user = make_user(email="locked@demo.com", password="pw")
    user.locked_until = datetime.now() + timedelta(minutes=10)
    db.commit()

    res = client.post("/auth/login", json={"email": "locked@demo.com", "password": "pw"})

    assert res.status_code == 423


def test_verify_token_roundtrip_and_rejects_garbage(make_user):
    user = make_user(email="charlie@demo.com")

    token = create_access_token(user.id)
    assert verify_token(token) == user.id
    assert verify_token("not-a-valid-jwt") is None
