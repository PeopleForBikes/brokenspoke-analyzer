"""
Define the pipeline exception hierarchy.

Give each pipeline stage a typed failure mode instead of letting raw
`KeyError`/`ValueError`/library exceptions escape, so a caller can tell a
bad-input condition apart from a bug. This is an internal quality improvement
rather than a parity requirement: the SQL pipeline surfaced undifferentiated
`sqlalchemy` errors, and nothing downstream depends on matching that.
"""


class PipelineError(Exception):
    """Raise for any failure originating in the analysis pipeline.

    Serve as the base class every other pipeline error derives from, so
    callers can catch the whole family with a single `except`.
    """


class IngestError(PipelineError):
    """Raise when the OSM extract or boundary data cannot be ingested.

    Cover unreadable or malformed extracts, missing layers, and topology that
    cannot be assembled into a routable graph.
    """


class InsufficientDataError(PipelineError):
    """Raise when the inputs are readable but too sparse to analyze.

    Mirror the current `ingestor.py` behavior of rejecting an area with zero
    population, which cannot produce a meaningful score.
    """


class ReachabilityError(PipelineError):
    """Raise when the reachability computation cannot be completed.

    Cover a malformed network graph and census blocks that cannot be tied to
    any network vertex.
    """
