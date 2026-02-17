"""Data models for UK polling voting intentions."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class PollResult(BaseModel):
    """A single opinion poll result."""

    pollster: str = Field(description="Polling organisation name")
    client: Optional[str] = Field(default=None, description="Commissioning client")
    fieldwork_start: Optional[date] = Field(
        default=None, description="Start date of fieldwork"
    )
    fieldwork_end: Optional[date] = Field(
        default=None, description="End date of fieldwork"
    )
    sample_size: Optional[int] = Field(
        default=None, description="Number of respondents"
    )
    con: Optional[float] = Field(default=None, description="Conservative Party %")
    lab: Optional[float] = Field(default=None, description="Labour Party %")
    lib_dem: Optional[float] = Field(default=None, description="Liberal Democrats %")
    reform: Optional[float] = Field(default=None, description="Reform UK %")
    green: Optional[float] = Field(default=None, description="Green Party %")
    snp: Optional[float] = Field(default=None, description="Scottish National Party %")
    other: Optional[float] = Field(default=None, description="Other parties %")
    lead_party: Optional[str] = Field(
        default=None, description="Party with highest vote share"
    )
    lead_pct: Optional[float] = Field(
        default=None, description="Lead in percentage points"
    )
    source_url: Optional[str] = Field(
        default=None, description="URL source of the poll"
    )


class PollSummary(BaseModel):
    """Aggregated summary of recent polling."""

    period_start: date
    period_end: date
    poll_count: int
    averages: dict[str, Optional[float]] = Field(
        description="Average vote share per party"
    )
    leader: str = Field(description="Party currently leading in the average")
    lead_margin: float = Field(description="Average lead in percentage points")


class PollingDataStatus(BaseModel):
    """Status of the polling data store."""

    total_polls: int
    latest_poll_date: Optional[date]
    oldest_poll_date: Optional[date]
    last_refreshed: Optional[datetime]
    source: str


class PartyTrend(BaseModel):
    """Trend data for a single party over time."""

    party: str
    data_points: list[dict] = Field(
        description="List of {date, value} data points"
    )
