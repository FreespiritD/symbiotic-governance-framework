"""UK Polling Voting Intentions API.

A REST API that captures and serves the latest UK opinion polling data
on Westminster voting intentions.
"""

import logging
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import PartyTrend, PollResult, PollSummary, PollingDataStatus
from .store import polling_store

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS = 6

VALID_PARTIES = [
    "conservative", "labour", "liberal democrats", "lib_dem",
    "reform", "reform uk", "green", "snp", "other",
    "con", "lab",
]


def refresh_polling_data() -> int:
    """Fetch fresh polling data. Falls back to seed data on failure."""
    try:
        from .scraper import scrape_polls

        polls = scrape_polls()
        if polls:
            return polling_store.load(polls, source="wikipedia")
    except Exception:
        logger.exception("Failed to scrape live polling data")

    # Fall back to seed data if scraping fails or returns nothing
    if polling_store.get_status().total_polls == 0:
        logger.info("Loading seed data as fallback")
        from .seed_data import SEED_POLLS

        return polling_store.load(SEED_POLLS, source="seed_data")
    return 0


scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: load data on startup, schedule refreshes."""
    refresh_polling_data()
    scheduler.add_job(
        refresh_polling_data,
        "interval",
        hours=REFRESH_INTERVAL_HOURS,
        id="refresh_polls",
    )
    scheduler.start()
    logger.info(
        "Scheduler started — refreshing every %d hours", REFRESH_INTERVAL_HOURS
    )
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="UK Polling Voting Intentions API",
    description=(
        "REST API providing the latest UK Westminster voting intention "
        "polling data. Sourced from publicly available opinion polls "
        "conducted by BPC-member pollsters.\n\n"
        "Data is refreshed automatically every 6 hours from Wikipedia's "
        "opinion polling tracker for the next UK general election."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── Endpoints ──────────────────────────────────────────────────────────


@app.get("/", tags=["info"])
def root():
    """API welcome and link to documentation."""
    return {
        "name": "UK Polling Voting Intentions API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "latest": "/polls/latest",
            "all": "/polls",
            "summary": "/polls/summary",
            "by_pollster": "/polls/pollster/{name}",
            "by_party": "/polls/party/{name}",
            "trends": "/polls/trends",
            "date_range": "/polls/range?start=YYYY-MM-DD&end=YYYY-MM-DD",
            "status": "/status",
        },
    }


@app.get(
    "/polls/latest",
    response_model=list[PollResult],
    tags=["polls"],
    summary="Get the most recent polls",
)
def get_latest_polls(
    n: int = Query(default=10, ge=1, le=100, description="Number of polls"),
):
    """Return the *n* most recent voting intention polls (default 10)."""
    return polling_store.get_latest(n)


@app.get(
    "/polls",
    response_model=list[PollResult],
    tags=["polls"],
    summary="Get all stored polls",
)
def get_all_polls():
    """Return every poll currently stored, newest first."""
    return polling_store.get_all()


@app.get(
    "/polls/summary",
    response_model=PollSummary,
    tags=["polls"],
    summary="Polling average summary",
)
def get_summary(
    n: int = Query(
        default=10, ge=1, le=50,
        description="Number of recent polls to average",
    ),
):
    """Compute a weighted average of the last *n* polls."""
    summary = polling_store.get_summary(n)
    if summary is None:
        raise HTTPException(status_code=404, detail="No polling data available")
    return summary


@app.get(
    "/polls/pollster/{name}",
    response_model=list[PollResult],
    tags=["polls"],
    summary="Filter polls by pollster",
)
def get_by_pollster(name: str):
    """Return all polls conducted by the given polling organisation.

    Performs a case-insensitive partial match (e.g. 'yougov' matches 'YouGov').
    """
    results = polling_store.get_by_pollster(name)
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No polls found for pollster '{name}'",
        )
    return results


@app.get(
    "/polls/party/{name}",
    response_model=list[dict],
    tags=["polls"],
    summary="Get data points for a specific party",
)
def get_by_party(name: str):
    """Return all data points for a given party.

    Accepts party names like 'reform', 'labour', 'conservative',
    'lib_dem', 'green', 'snp', or 'other'.
    """
    results = polling_store.get_by_party(name)
    if not results:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No data for party '{name}'. "
                f"Valid parties: {', '.join(VALID_PARTIES)}"
            ),
        )
    return results


@app.get(
    "/polls/trends",
    response_model=list[PartyTrend],
    tags=["polls"],
    summary="Get trend data for all parties",
)
def get_trends():
    """Return time-series trend data for every tracked party."""
    return polling_store.get_trends()


@app.get(
    "/polls/range",
    response_model=list[PollResult],
    tags=["polls"],
    summary="Filter polls by date range",
)
def get_date_range(
    start: date = Query(description="Start date (YYYY-MM-DD)"),
    end: date = Query(description="End date (YYYY-MM-DD)"),
):
    """Return polls whose fieldwork ended within the given date range."""
    if start > end:
        raise HTTPException(
            status_code=400, detail="start must be before end"
        )
    results = polling_store.get_date_range(start, end)
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No polls found between {start} and {end}",
        )
    return results


@app.post(
    "/polls/refresh",
    tags=["admin"],
    summary="Trigger a manual data refresh",
)
def trigger_refresh():
    """Manually trigger a refresh of polling data from the source."""
    count = refresh_polling_data()
    status = polling_store.get_status()
    return {
        "message": f"Refreshed {count} polls",
        "source": status.source,
        "last_refreshed": status.last_refreshed,
    }


@app.get(
    "/status",
    response_model=PollingDataStatus,
    tags=["info"],
    summary="Data store status",
)
def get_status():
    """Return metadata about the current polling data store."""
    return polling_store.get_status()
