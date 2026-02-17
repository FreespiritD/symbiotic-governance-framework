"""Tests for the UK Polling API endpoints."""

import pytest
from fastapi.testclient import TestClient

from uk_polling_api.app import app
from uk_polling_api.seed_data import SEED_POLLS
from uk_polling_api.store import polling_store


@pytest.fixture(autouse=True)
def _load_seed_data():
    """Ensure seed data is loaded before each test."""
    polling_store.load(SEED_POLLS, source="test")
    yield


client = TestClient(app, raise_server_exceptions=False)


class TestRoot:
    def test_root_returns_api_info(self):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "UK Polling Voting Intentions API"
        assert "endpoints" in data

    def test_docs_available(self):
        resp = client.get("/docs")
        assert resp.status_code == 200


class TestLatestPolls:
    def test_default_returns_10(self):
        resp = client.get("/polls/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 10

    def test_custom_count(self):
        resp = client.get("/polls/latest?n=3")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_sorted_newest_first(self):
        resp = client.get("/polls/latest?n=5")
        data = resp.json()
        dates = [p["fieldwork_end"] for p in data if p["fieldwork_end"]]
        assert dates == sorted(dates, reverse=True)

    def test_poll_has_expected_fields(self):
        resp = client.get("/polls/latest?n=1")
        poll = resp.json()[0]
        assert "pollster" in poll
        assert "con" in poll
        assert "lab" in poll
        assert "reform" in poll
        assert "green" in poll
        assert "lib_dem" in poll
        assert "lead_party" in poll


class TestAllPolls:
    def test_returns_all_polls(self):
        resp = client.get("/polls")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == len(SEED_POLLS)


class TestSummary:
    def test_summary_returns_averages(self):
        resp = client.get("/polls/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "averages" in data
        assert "leader" in data
        assert "lead_margin" in data
        assert "poll_count" in data
        assert data["poll_count"] == 10

    def test_summary_custom_n(self):
        resp = client.get("/polls/summary?n=5")
        data = resp.json()
        assert data["poll_count"] == 5

    def test_averages_contain_all_parties(self):
        resp = client.get("/polls/summary")
        averages = resp.json()["averages"]
        for party in [
            "Conservative", "Labour", "Liberal Democrats",
            "Reform UK", "Green",
        ]:
            assert party in averages
            assert isinstance(averages[party], (int, float))


class TestByPollster:
    def test_yougov(self):
        resp = client.get("/polls/pollster/YouGov")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert all("YouGov" in p["pollster"] for p in data)

    def test_case_insensitive(self):
        resp = client.get("/polls/pollster/yougov")
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_not_found(self):
        resp = client.get("/polls/pollster/nonexistent")
        assert resp.status_code == 404


class TestByParty:
    def test_reform(self):
        resp = client.get("/polls/party/reform")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        assert all("value" in dp for dp in data)
        assert all("date" in dp for dp in data)

    def test_labour(self):
        resp = client.get("/polls/party/labour")
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_conservative(self):
        resp = client.get("/polls/party/conservative")
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_invalid_party(self):
        resp = client.get("/polls/party/pirate")
        assert resp.status_code == 404


class TestTrends:
    def test_trends_returns_all_parties(self):
        resp = client.get("/polls/trends")
        assert resp.status_code == 200
        data = resp.json()
        party_names = {t["party"] for t in data}
        assert "Reform UK" in party_names
        assert "Labour" in party_names
        assert "Conservative" in party_names

    def test_trend_has_data_points(self):
        resp = client.get("/polls/trends")
        data = resp.json()
        for trend in data:
            assert len(trend["data_points"]) > 0
            assert "date" in trend["data_points"][0]
            assert "value" in trend["data_points"][0]


class TestDateRange:
    def test_valid_range(self):
        resp = client.get("/polls/range?start=2026-01-01&end=2026-02-28")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    def test_narrow_range(self):
        resp = client.get("/polls/range?start=2026-02-01&end=2026-02-04")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_inverted_range(self):
        resp = client.get("/polls/range?start=2026-03-01&end=2026-01-01")
        assert resp.status_code == 400

    def test_empty_range(self):
        resp = client.get("/polls/range?start=2020-01-01&end=2020-01-31")
        assert resp.status_code == 404


class TestStatus:
    def test_status_fields(self):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_polls" in data
        assert "latest_poll_date" in data
        assert "last_refreshed" in data
        assert "source" in data
        assert data["total_polls"] == len(SEED_POLLS)


class TestRefresh:
    def test_manual_refresh(self):
        resp = client.post("/polls/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "source" in data
