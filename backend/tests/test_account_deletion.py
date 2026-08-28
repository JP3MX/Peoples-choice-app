"""Account deletion policy regression test."""
import os
import uuid
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


def test_account_deletion_removes_user_and_owned_data():
    email = f"delete-test-{uuid.uuid4().hex[:10]}@example.com"
    password = "DeleteTest-1234"
    session = requests.Session()

    registered = session.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "name": "Deletion Test"},
        timeout=30,
    )
    assert registered.status_code == 200, registered.text
    token = registered.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    aircraft = session.post(
        f"{API}/aircraft",
        json={"tail_number": "NDELETE", "make": "Test", "model": "Test", "confirmed": False},
        headers=headers,
        timeout=30,
    )
    assert aircraft.status_code == 200, aircraft.text

    deleted = session.delete(
        f"{API}/auth/account",
        json={"password": password, "confirm": "DELETE"},
        headers=headers,
        timeout=60,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] is True

    assert session.get(f"{API}/auth/me", headers=headers, timeout=30).status_code == 401
    assert session.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    ).status_code == 401
