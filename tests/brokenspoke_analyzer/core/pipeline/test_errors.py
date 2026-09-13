"""Test the pipeline exception hierarchy.

Guarantee that callers can catch every pipeline failure with one `except`,
which is the whole point of introducing the hierarchy.
"""

import pytest

from brokenspoke_analyzer.core.pipeline import errors


@pytest.mark.parametrize(
    "error",
    [errors.IngestError, errors.InsufficientDataError, errors.ReachabilityError],
)
def test_stage_errors_share_a_base(error: type[errors.PipelineError]) -> None:
    """Every stage error is catchable as a `PipelineError`."""
    with pytest.raises(errors.PipelineError):
        raise error("boom")


def test_pipeline_error_is_an_exception() -> None:
    """`PipelineError` stays catchable as a plain `Exception`."""
    assert issubclass(errors.PipelineError, Exception)


def test_errors_carry_their_message() -> None:
    """The raised message survives, so failures stay diagnosable."""
    with pytest.raises(errors.InsufficientDataError, match="zero population"):
        raise errors.InsufficientDataError("zero population")
