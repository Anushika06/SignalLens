from datetime import UTC, datetime, timedelta, timezone

import pytest

from signallens.search import SearchResult, parse_published_date

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3 hours ago", NOW - timedelta(hours=3)),
        ("2 days ago", NOW - timedelta(days=2)),
        ("1 day ago", NOW - timedelta(days=1)),
        ("an hour ago", NOW - timedelta(hours=1)),
        ("45 mins ago", NOW - timedelta(minutes=45)),
        ("2 weeks ago", NOW - timedelta(weeks=2)),
        ("yesterday", NOW - timedelta(days=1)),
        ("Sep 21, 2026", datetime(2026, 9, 21, tzinfo=UTC)),
        ("21 September 2026", datetime(2026, 9, 21, tzinfo=UTC)),
        ("2026-09-21", datetime(2026, 9, 21, tzinfo=UTC)),
        ("2026-09-21T10:15:00+05:30", datetime(2026, 9, 21, 4, 45, tzinfo=UTC)),
        ("Sun, 21 Sep 2026 10:15:00 GMT", datetime(2026, 9, 21, 10, 15, tzinfo=UTC)),
    ],
)
def test_parse_published_date(raw, expected):
    assert parse_published_date(raw, now=NOW) == expected


@pytest.mark.parametrize("raw", [None, "", "whenever", "N/A", 12345, "Dec 31, 2030"])
def test_unparseable_or_future_dates_are_none(raw):
    assert parse_published_date(raw, now=NOW) is None


def test_year_less_dates_in_the_future_mean_last_year():
    now = datetime(2027, 1, 5, tzinfo=UTC)
    assert parse_published_date("Dec 30", now=now) == datetime(2026, 12, 30, tzinfo=UTC)


def test_search_result_normalises_timezone_and_publisher():
    ist = timezone(timedelta(hours=5, minutes=30))
    r = SearchResult(
        url="https://economictimes.indiatimes.com/x",
        title="t",
        snippet="s",
        published_at=datetime(2026, 9, 21, 10, 15, tzinfo=ist),
    )
    assert r.published_at == datetime(2026, 9, 21, 4, 45, tzinfo=UTC)
    assert r.published_at.tzinfo == UTC
    assert r.publisher == "indiatimes.com"
    naive = SearchResult(url="https://a.com", title="t", snippet="s", published_at=datetime(2026, 1, 1))
    assert naive.published_at.tzinfo == UTC
