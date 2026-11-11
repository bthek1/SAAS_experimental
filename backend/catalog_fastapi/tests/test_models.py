from datetime import UTC, datetime, timedelta, timezone

import pytest

from catalog_fastapi.models import UTCDateTime

BRISBANE = timezone(timedelta(hours=10))


def test_results_are_utc_whatever_the_connection_zone():
    local = datetime(2026, 1, 2, 13, 4, 5, 123456, tzinfo=BRISBANE)
    result = UTCDateTime().process_result_value(local, None)
    assert result.tzinfo is UTC
    assert result.isoformat() == "2026-01-02T03:04:05.123456+00:00"


def test_naive_results_are_read_as_utc():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert UTCDateTime().process_result_value(naive, None).tzinfo is UTC


def test_naive_values_are_refused():
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 2), None)
