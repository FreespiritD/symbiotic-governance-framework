"""In-memory polling data store with thread-safe access."""

import logging
import threading
from datetime import date, datetime
from statistics import mean
from typing import Optional

from .models import PartyTrend, PollResult, PollSummary, PollingDataStatus

logger = logging.getLogger(__name__)

PARTY_FIELDS = ("con", "lab", "lib_dem", "reform", "green", "snp", "other")

PARTY_DISPLAY_NAMES = {
    "con": "Conservative",
    "lab": "Labour",
    "lib_dem": "Liberal Democrats",
    "reform": "Reform UK",
    "green": "Green",
    "snp": "SNP",
    "other": "Other",
}


class PollingStore:
    """Thread-safe in-memory store for polling data."""

    def __init__(self) -> None:
        self._polls: list[PollResult] = []
        self._lock = threading.Lock()
        self._last_refreshed: Optional[datetime] = None
        self._source: str = "none"

    @property
    def last_refreshed(self) -> Optional[datetime]:
        return self._last_refreshed

    def load(self, polls: list[PollResult], source: str = "unknown") -> int:
        """Replace all stored polls with new data. Returns count loaded."""
        with self._lock:
            self._polls = sorted(
                polls,
                key=lambda p: p.fieldwork_end or date.min,
                reverse=True,
            )
            self._last_refreshed = datetime.utcnow()
            self._source = source
            logger.info("Loaded %d polls from %s", len(self._polls), source)
            return len(self._polls)

    def get_all(self) -> list[PollResult]:
        with self._lock:
            return list(self._polls)

    def get_latest(self, n: int = 10) -> list[PollResult]:
        with self._lock:
            return list(self._polls[:n])

    def get_by_pollster(self, pollster: str) -> list[PollResult]:
        with self._lock:
            return [
                p for p in self._polls
                if pollster.lower() in p.pollster.lower()
            ]

    def get_by_party(self, party: str) -> list[dict]:
        """Get all data points for a specific party."""
        normalized = party.lower().strip()
        # Resolve display names first (e.g. "Reform UK" -> "reform")
        reverse_map = {v.lower(): k for k, v in PARTY_DISPLAY_NAMES.items()}
        if normalized in reverse_map:
            field = reverse_map[normalized]
        else:
            field = normalized.replace(" ", "_")
        if field not in PARTY_FIELDS:
            return []

        with self._lock:
            results = []
            for p in self._polls:
                value = getattr(p, field, None)
                if value is not None:
                    results.append({
                        "date": (p.fieldwork_end or p.fieldwork_start),
                        "value": value,
                        "pollster": p.pollster,
                    })
            return results

    def get_date_range(
        self, start: date, end: date
    ) -> list[PollResult]:
        with self._lock:
            return [
                p for p in self._polls
                if p.fieldwork_end
                and start <= p.fieldwork_end <= end
            ]

    def get_summary(self, n: int = 10) -> Optional[PollSummary]:
        """Compute an average summary of the last n polls."""
        with self._lock:
            recent = self._polls[:n]

        if not recent:
            return None

        averages: dict[str, Optional[float]] = {}
        for field in PARTY_FIELDS:
            values = [
                getattr(p, field) for p in recent
                if getattr(p, field) is not None
            ]
            averages[PARTY_DISPLAY_NAMES[field]] = (
                round(mean(values), 1) if values else None
            )

        # Determine leader
        leader = max(
            averages,
            key=lambda k: averages[k] if averages[k] is not None else -1,
        )
        leader_val = averages[leader] or 0.0

        # Second place
        second_val = max(
            (v for k, v in averages.items() if k != leader and v is not None),
            default=0.0,
        )
        lead_margin = round(leader_val - second_val, 1)

        dates = [
            p.fieldwork_end for p in recent if p.fieldwork_end is not None
        ]

        return PollSummary(
            period_start=min(dates) if dates else date.today(),
            period_end=max(dates) if dates else date.today(),
            poll_count=len(recent),
            averages=averages,
            leader=leader,
            lead_margin=lead_margin,
        )

    def get_trends(self) -> list[PartyTrend]:
        """Get trend data for all parties."""
        trends = []
        for field in PARTY_FIELDS:
            data_points = self.get_by_party(field)
            if data_points:
                trends.append(PartyTrend(
                    party=PARTY_DISPLAY_NAMES[field],
                    data_points=[
                        {"date": str(dp["date"]), "value": dp["value"]}
                        for dp in data_points
                    ],
                ))
        return trends

    def get_status(self) -> PollingDataStatus:
        with self._lock:
            dates = [
                p.fieldwork_end for p in self._polls
                if p.fieldwork_end is not None
            ]
            return PollingDataStatus(
                total_polls=len(self._polls),
                latest_poll_date=max(dates) if dates else None,
                oldest_poll_date=min(dates) if dates else None,
                last_refreshed=self._last_refreshed,
                source=self._source,
            )


# Singleton instance
polling_store = PollingStore()
