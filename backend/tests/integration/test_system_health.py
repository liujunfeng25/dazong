from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[2]))
from main import app


def test_healthz_ok():
    client = TestClient(app)
    resp = client.get("/api/system/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
