from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phone_agent.api.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    with TestClient(app) as c:
        yield c


def _record(number: str = "9876543210", language: str = "en", **extra) -> dict:
    return {"rawTranscript": "nine eight seven ...", "parsedNumber": number, "language": language, **extra}


def test_create_and_list(client: TestClient) -> None:
    resp = client.post("/api/phone", json=_record())
    assert resp.status_code == 201
    body = resp.json()
    assert body["parsedNumber"] == "9876543210"
    assert body["rawTranscript"] == "nine eight seven ..."
    assert body["language"] == "en"
    assert body["collectedAt"].endswith(("Z", "+00:00"))

    listed = client.get("/api/phone").json()
    assert [r["id"] for r in listed] == [body["id"]]


@pytest.mark.parametrize("bad", ["12345", "1234567890", "98765432101", "98765abcde"])
def test_rejects_invalid_numbers(client: TestClient, bad: str) -> None:
    assert client.post("/api/phone", json=_record(bad)).status_code == 422
    assert client.get("/api/phone").json() == []


def test_rejects_unknown_language(client: TestClient) -> None:
    assert client.post("/api/phone", json=_record(language="fr")).status_code == 422


def test_delete(client: TestClient) -> None:
    rid = client.post("/api/phone", json=_record()).json()["id"]
    assert client.delete(f"/api/phone/{rid}").status_code == 204
    assert client.delete(f"/api/phone/{rid}").status_code == 404
    assert client.get("/api/phone").json() == []


def test_filters_and_stats(client: TestClient) -> None:
    client.post("/api/phone", json=_record("9876543210", "en", collectedAt="2026-01-01T10:00:00Z"))
    client.post("/api/phone", json=_record("8123456789", "hi", collectedAt="2026-02-01T10:00:00Z"))
    client.post("/api/phone", json=_record("7000000001", "mixed", collectedAt="2026-03-01T10:00:00Z"))

    assert [r["parsedNumber"] for r in client.get("/api/phone?search=8123").json()] == ["8123456789"]
    assert [r["language"] for r in client.get("/api/phone?language=mixed").json()] == ["mixed"]
    in_range = client.get("/api/phone", params={"from": "2026-01-15T00:00:00Z", "to": "2026-02-15T00:00:00Z"})
    assert [r["parsedNumber"] for r in in_range.json()] == ["8123456789"]
    # newest first
    assert [r["language"] for r in client.get("/api/phone").json()] == ["mixed", "hi", "en"]

    stats = client.get("/api/phone/stats").json()
    assert stats == {"total": 3, "byLanguage": {"en": 1, "hi": 1, "mixed": 1}}


def test_parse_endpoint(client: TestClient) -> None:
    body = client.post("/api/parse", json={"transcript": "nine aath saat 6 5 chaar 3 2 1 zero"}).json()
    assert body["digits"] == "9876543210"
    assert body["isValid"] is True
    assert body["language"] == "mixed"


def test_frontend_is_served(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "Collected numbers" in page.text
    for asset in ("app.js", "style.css", "config.js"):
        assert client.get(f"/{asset}").status_code == 200
    assert client.get("/api/health").json() == {"status": "ok"}  # API not shadowed
