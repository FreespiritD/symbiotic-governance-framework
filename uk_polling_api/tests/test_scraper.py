"""Tests for the polling data scraper parsing utilities."""

from datetime import date

from uk_polling_api.scraper import (
    _identify_columns,
    _parse_date_text,
    _parse_fieldwork_dates,
    _parse_percentage,
    _parse_sample_size,
)


class TestParsePercentage:
    def test_integer(self):
        assert _parse_percentage("26") == 26.0

    def test_decimal(self):
        assert _parse_percentage("19.3") == 19.3

    def test_with_whitespace(self):
        assert _parse_percentage("  14  ") == 14.0

    def test_dash_returns_none(self):
        assert _parse_percentage("–") is None

    def test_empty_returns_none(self):
        assert _parse_percentage("") is None

    def test_na_returns_none(self):
        assert _parse_percentage("N/A") is None

    def test_with_surrounding_text(self):
        assert _parse_percentage("26%") == 26.0


class TestParseSampleSize:
    def test_simple_number(self):
        assert _parse_sample_size("2089") == 2089

    def test_with_comma(self):
        assert _parse_sample_size("2,089") == 2089

    def test_with_spaces(self):
        assert _parse_sample_size("2 089") == 2089

    def test_empty(self):
        assert _parse_sample_size("") is None

    def test_small_number_ignored(self):
        assert _parse_sample_size("12") is None


class TestParseDateText:
    def test_full_date(self):
        assert _parse_date_text("3 Feb 2026") == date(2026, 2, 3)

    def test_date_without_year(self):
        result = _parse_date_text("3 Feb", 2026)
        assert result == date(2026, 2, 3)

    def test_full_month_name(self):
        assert _parse_date_text("15 January 2026") == date(2026, 1, 15)

    def test_empty(self):
        assert _parse_date_text("") is None


class TestParseFieldworkDates:
    def test_range_same_month(self):
        start, end = _parse_fieldwork_dates("1-3 Feb 2026")
        assert end == date(2026, 2, 3)
        assert start == date(2026, 2, 1)

    def test_range_cross_month(self):
        start, end = _parse_fieldwork_dates("28 Jan – 1 Feb 2026")
        assert end == date(2026, 2, 1)
        assert start == date(2026, 1, 28)

    def test_single_date(self):
        start, end = _parse_fieldwork_dates("4 Feb 2026")
        assert start == date(2026, 2, 4)
        assert end == date(2026, 2, 4)

    def test_empty(self):
        start, end = _parse_fieldwork_dates("")
        assert start is None
        assert end is None


class TestIdentifyColumns:
    def test_standard_headers(self):
        headers = [
            "Dates conducted", "Polling organisation/client",
            "Sample size", "Con", "Lab", "Lib Dem", "Reform",
            "Green", "SNP", "Other", "Lead",
        ]
        col_map = _identify_columns(headers)
        assert col_map[0] == "fieldwork"
        assert col_map[1] == "pollster"
        assert col_map[2] == "sample_size"
        assert col_map[3] == "con"
        assert col_map[4] == "lab"
        assert col_map[5] == "lib_dem"
        assert col_map[6] == "reform"
        assert col_map[7] == "green"
        assert col_map[8] == "snp"
        assert col_map[9] == "other"
        assert col_map[10] == "lead"

    def test_alternative_names(self):
        headers = ["Date", "Pollster", "Sample", "Conservative", "Labour"]
        col_map = _identify_columns(headers)
        assert col_map[0] == "fieldwork"
        assert col_map[1] == "pollster"
        assert col_map[2] == "sample_size"
        assert col_map[3] == "con"
        assert col_map[4] == "lab"
