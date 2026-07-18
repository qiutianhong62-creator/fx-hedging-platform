from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_endpoint_identifies_backend() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fx-hedging-backend",
        "version": "0.1.0",
    }
