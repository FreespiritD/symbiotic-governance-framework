"""Tests for the polling data store."""

from datetime import date

from uk_polling_api.models import PollResult
from uk_polling_api.store import PollingStore


def _make_poll(**overrides) -> PollResult:
    defaults = dict(
        pollster="TestPoll",
        client="TestClient",
        fieldwork_start=date(2026, 1, 1),
        fieldwork_end=date(2026, 1, 2),
        sample_size=1000,
        con=20,
        lab=22,
        lib_dem=11,
        reform=28,
        green=12,
        snp=3,
        other=4,
        lead_party="Reform UK",
        lead_pct=6.0,
    )
    defaults.update(overrides)
    return PollResult(**defaults)


class TestPollingStore:
    def setup_method(self):
        self.store = PollingStore()
        self.polls = [
            _make_poll(
                pollster="YouGov",
                fieldwork_end=date(2026, 2, 4),
                reform=26,
                lab=19,
            ),
            _make_poll(
                pollster="Opinium",
                fieldwork_end=date(2026, 1, 24),
                reform=27,
                lab=22,
            ),
            _make_poll(
                pollster="YouGov",
                fieldwork_end=date(2026, 1, 15),
                reform=26,
                lab=21,
            ),
        ]
        self.store.load(self.polls, source="test")

    def test_load_returns_count(self):
        count = self.store.load(self.polls, source="test")
        assert count == 3

    def test_get_all(self):
        assert len(self.store.get_all()) == 3

    def test_get_latest(self):
        latest = self.store.get_latest(2)
        assert len(latest) == 2
        assert latest[0].fieldwork_end >= latest[1].fieldwork_end

    def test_get_by_pollster(self):
        results = self.store.get_by_pollster("yougov")
        assert len(results) == 2

    def test_get_by_pollster_partial(self):
        results = self.store.get_by_pollster("opin")
        assert len(results) == 1
        assert results[0].pollster == "Opinium"

    def test_get_by_party(self):
        results = self.store.get_by_party("reform")
        assert len(results) == 3
        assert all("value" in r for r in results)

    def test_get_by_party_display_name(self):
        results = self.store.get_by_party("Reform UK")
        assert len(results) == 3

    def test_get_by_party_invalid(self):
        results = self.store.get_by_party("pirate")
        assert results == []

    def test_get_date_range(self):
        results = self.store.get_date_range(
            date(2026, 1, 20), date(2026, 2, 28)
        )
        assert len(results) == 2

    def test_get_summary(self):
        summary = self.store.get_summary(3)
        assert summary is not None
        assert summary.poll_count == 3
        assert summary.leader == "Reform UK"
        assert summary.lead_margin > 0
        assert summary.averages["Reform UK"] is not None

    def test_get_trends(self):
        trends = self.store.get_trends()
        party_names = {t.party for t in trends}
        assert "Reform UK" in party_names
        assert "Labour" in party_names

    def test_get_status(self):
        status = self.store.get_status()
        assert status.total_polls == 3
        assert status.latest_poll_date == date(2026, 2, 4)
        assert status.source == "test"
        assert status.last_refreshed is not None

    def test_empty_store(self):
        empty = PollingStore()
        assert empty.get_all() == []
        assert empty.get_summary() is None
        status = empty.get_status()
        assert status.total_polls == 0
