"""Test module."""

from loguru import logger

logger.enable("brokenspoke_analyzer")


def test_truthy() -> None:
    """Dummy test."""
    assert True, "This is a dummy test"
