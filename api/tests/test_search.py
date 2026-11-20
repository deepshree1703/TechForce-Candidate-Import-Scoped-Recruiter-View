"""Unit tests for the search helpers. No database needed."""

import pytest

from app.search import escape_like, search_condition


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        pytest.param("plain", "plain", id="plain-text"),
        pytest.param("50%", "50/%", id="percent"),
        pytest.param("a_b", "a/_b", id="underscore"),
        pytest.param("a/b", "a//b", id="escape-char"),
        pytest.param("\\", "\\", id="backslash-is-ordinary"),
        pytest.param("%_/", "/%/_//", id="all-three"),
    ],
)
def test_escape_like(term: str, expected: str) -> None:
    """Wildcards and the escape character are escaped; everything else is left alone."""
    assert escape_like(term) == expected


@pytest.mark.parametrize("term", [None, "", "   "])
def test_blank_search_means_no_filter(term: str | None) -> None:
    """A missing or blank search adds no filter."""
    assert search_condition(term) is None


def test_real_search_builds_a_filter() -> None:
    """A normal search text builds a filter."""
    assert search_condition("ann") is not None