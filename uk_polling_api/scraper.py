"""Scraper for UK voting intention polling data from Wikipedia."""

import logging
import re
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .models import PollResult

logger = logging.getLogger(__name__)

WIKI_URL = (
    "https://en.wikipedia.org/wiki/"
    "Opinion_polling_for_the_next_United_Kingdom_general_election"
)

USER_AGENT = (
    "UKPollingAPI/1.0 "
    "(Educational governance research project; Python/requests)"
)

# Canonical party column names mapped from common header variations
PARTY_COLUMN_MAP = {
    "con": "con",
    "conservative": "con",
    "lab": "lab",
    "labour": "lab",
    "lib dem": "lib_dem",
    "libdem": "lib_dem",
    "ld": "lib_dem",
    "liberal democrats": "lib_dem",
    "reform": "reform",
    "reform uk": "reform",
    "ref": "reform",
    "green": "green",
    "greens": "green",
    "snp": "snp",
    "other": "other",
    "others": "other",
}


def _parse_percentage(text: str) -> Optional[float]:
    """Extract a numeric percentage from a cell's text."""
    text = text.strip().replace("–", "").replace("—", "").replace("−", "")
    if not text or text == "N/A":
        return None
    match = re.search(r"(\d+\.?\d*)", text)
    if match:
        return float(match.group(1))
    return None


def _parse_sample_size(text: str) -> Optional[int]:
    """Extract sample size from a cell, handling commas and ranges."""
    text = text.strip().replace(",", "").replace(" ", "")
    match = re.search(r"(\d{3,})", text)
    if match:
        return int(match.group(1))
    return None


def _parse_date_text(text: str, year: Optional[int] = None) -> Optional[date]:
    """Parse a date string from Wikipedia polling tables.

    Handles formats like:
    - "1-3 Feb 2026"
    - "3 Feb 2026"
    - "28 Jan – 1 Feb 2026"
    - "3 Feb"  (year inferred)
    """
    text = text.strip()
    if not text:
        return None

    # Common month abbreviations
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4,
        "june": 6, "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }

    if not year:
        year_match = re.search(r"20\d{2}", text)
        if year_match:
            year = int(year_match.group())
        else:
            year = date.today().year

    # Try to extract day and month
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)", text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2).lower()
        month = months.get(month_str)
        if month and 1 <= day <= 31:
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def _parse_fieldwork_dates(
    text: str,
) -> tuple[Optional[date], Optional[date]]:
    """Parse fieldwork date range, returning (start, end)."""
    text = text.strip()
    if not text:
        return None, None

    # Extract year if present
    year_match = re.search(r"(20\d{2})", text)
    year = int(year_match.group(1)) if year_match else date.today().year

    # Split on common range separators
    parts = re.split(r"[–—\-−]", text, maxsplit=1)
    if len(parts) == 2:
        end_date = _parse_date_text(parts[1].strip(), year)
        start_date = _parse_date_text(parts[0].strip(), year)
        # If start didn't get a month, inherit from end
        if start_date is None and end_date is not None:
            day_match = re.search(r"(\d{1,2})", parts[0].strip())
            if day_match:
                try:
                    start_date = date(year, end_date.month, int(day_match.group(1)))
                except ValueError:
                    pass
        return start_date, end_date
    else:
        d = _parse_date_text(text, year)
        return d, d


def _identify_columns(header_cells: list[str]) -> dict[int, str]:
    """Map column indices to field names based on header text."""
    col_map = {}
    for i, header in enumerate(header_cells):
        h = header.strip().lower()
        if h in PARTY_COLUMN_MAP:
            col_map[i] = PARTY_COLUMN_MAP[h]
        elif "date" in h or "fieldwork" in h:
            col_map[i] = "fieldwork"
        elif "polling" in h or "pollster" in h or "organisation" in h:
            col_map[i] = "pollster"
        elif "client" in h or "commissioner" in h:
            col_map[i] = "client"
        elif "sample" in h or "size" in h:
            col_map[i] = "sample_size"
        elif "area" in h:
            col_map[i] = "area"
        elif "lead" in h:
            col_map[i] = "lead"
    return col_map


def _expand_rowspans(table: Tag) -> list[list[str]]:
    """Expand a table with rowspan/colspan into a flat 2D list of cell texts."""
    rows = table.find_all("tr")
    if not rows:
        return []

    # First pass: determine grid dimensions
    max_cols = 0
    for row in rows:
        cols_in_row = 0
        for cell in row.find_all(["th", "td"]):
            colspan = int(cell.get("colspan", 1))
            cols_in_row += colspan
        max_cols = max(max_cols, cols_in_row)

    # Build grid
    grid: list[list[Optional[str]]] = [
        [None] * max_cols for _ in range(len(rows))
    ]

    for row_idx, row in enumerate(rows):
        col_idx = 0
        for cell in row.find_all(["th", "td"]):
            # Find next empty column
            while col_idx < max_cols and grid[row_idx][col_idx] is not None:
                col_idx += 1
            if col_idx >= max_cols:
                break

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))
            text = cell.get_text(strip=True)

            for dr in range(rowspan):
                for dc in range(colspan):
                    r, c = row_idx + dr, col_idx + dc
                    if r < len(grid) and c < max_cols:
                        grid[r][c] = text

            col_idx += colspan

    # Replace remaining None with empty string
    return [[cell or "" for cell in row] for row in grid]


def scrape_polls(url: str = WIKI_URL) -> list[PollResult]:
    """Scrape UK voting intention polls from Wikipedia.

    Returns a list of PollResult objects sorted by date (newest first).
    """
    logger.info("Fetching polling data from %s", url)
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        logger.warning("No wikitable found on the page")
        return []

    # The main voting intention table is typically the first large wikitable
    target_table = None
    for table in tables:
        text = table.get_text(strip=True).lower()
        # The main table will contain all major party names
        if all(p in text for p in ["con", "lab", "reform", "green"]):
            target_table = table
            break

    if target_table is None:
        logger.warning("Could not identify the main polling table")
        return []

    grid = _expand_rowspans(target_table)
    if len(grid) < 3:
        logger.warning("Table too small to contain polling data")
        return []

    # Identify header row — scan first few rows for party names
    header_row_idx = None
    col_map: dict[int, str] = {}
    for i in range(min(4, len(grid))):
        candidate_map = _identify_columns(grid[i])
        party_cols = {
            v for v in candidate_map.values()
            if v in ("con", "lab", "lib_dem", "reform", "green")
        }
        if len(party_cols) >= 3:
            header_row_idx = i
            col_map = candidate_map
            break

    if header_row_idx is None:
        logger.warning("Could not identify header row in polling table")
        return []

    logger.info(
        "Found header at row %d with columns: %s", header_row_idx, col_map
    )

    polls: list[PollResult] = []
    party_fields = {"con", "lab", "lib_dem", "reform", "green", "snp", "other"}

    for row_idx in range(header_row_idx + 1, len(grid)):
        row = grid[row_idx]

        # Skip rows that look like sub-headers or section dividers
        non_empty = [c for c in row if c.strip()]
        if len(non_empty) < 3:
            continue

        data: dict = {}
        party_values: dict[str, Optional[float]] = {}

        for col_idx, field in col_map.items():
            if col_idx >= len(row):
                continue
            cell_text = row[col_idx]

            if field == "fieldwork":
                start, end = _parse_fieldwork_dates(cell_text)
                data["fieldwork_start"] = start
                data["fieldwork_end"] = end
            elif field == "pollster":
                data["pollster"] = cell_text
            elif field == "client":
                data["client"] = cell_text if cell_text else None
            elif field == "sample_size":
                data["sample_size"] = _parse_sample_size(cell_text)
            elif field in party_fields:
                party_values[field] = _parse_percentage(cell_text)
            elif field == "lead":
                pass  # We'll calculate lead ourselves

        # Must have a pollster and at least one party value
        pollster = data.get("pollster", "").strip()
        if not pollster or all(v is None for v in party_values.values()):
            continue

        # Determine the leading party
        best_party = None
        best_val = -1.0
        for p, v in party_values.items():
            if v is not None and v > best_val:
                best_val = v
                best_party = p

        # Calculate lead over second place
        second_val = -1.0
        for p, v in party_values.items():
            if v is not None and p != best_party and v > second_val:
                second_val = v

        lead_pct = round(best_val - second_val, 1) if second_val >= 0 else None

        # Map internal party keys to display names
        party_display = {
            "con": "Conservative",
            "lab": "Labour",
            "lib_dem": "Liberal Democrats",
            "reform": "Reform UK",
            "green": "Green",
            "snp": "SNP",
            "other": "Other",
        }

        poll = PollResult(
            pollster=pollster,
            client=data.get("client"),
            fieldwork_start=data.get("fieldwork_start"),
            fieldwork_end=data.get("fieldwork_end"),
            sample_size=data.get("sample_size"),
            con=party_values.get("con"),
            lab=party_values.get("lab"),
            lib_dem=party_values.get("lib_dem"),
            reform=party_values.get("reform"),
            green=party_values.get("green"),
            snp=party_values.get("snp"),
            other=party_values.get("other"),
            lead_party=party_display.get(best_party, best_party) if best_party else None,
            lead_pct=lead_pct,
            source_url=url,
        )
        polls.append(poll)

    logger.info("Scraped %d polls from Wikipedia", len(polls))

    # Sort by fieldwork_end descending (newest first)
    polls.sort(
        key=lambda p: p.fieldwork_end or date.min,
        reverse=True,
    )
    return polls
