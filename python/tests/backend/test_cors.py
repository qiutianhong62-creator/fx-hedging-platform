import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)
def test_local_frontend_origin_can_preflight(origin: str) -> None:
    response = client.options(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_unapproved_origin_does_not_receive_allow_origin_header() -> None:
    response = client.options(
        "/api/v1/analysis/forward-strategy/automatic-probability",
        headers={
            "Origin": "https://unapproved.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
