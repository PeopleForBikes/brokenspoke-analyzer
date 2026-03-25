"""Test the exporter module."""

from __future__ import annotations

import pathlib
from datetime import date
from typing import TYPE_CHECKING

import obstore
import pytest

from brokenspoke_analyzer.core import exporter

if TYPE_CHECKING:
    from obstore.store import (
        MemoryStore,
        ObjectStore,
    )


@pytest.mark.asyncio
async def test_mkdir_calver_directory():
    """Ensure calver directory are created correctly."""
    today = date.today()
    calver = f"{today.strftime('%y.%m')}"
    store = obstore.store.MemoryStore()

    directory = await exporter.mkdir_calver_directory(store, "usa", "austin", "tx")
    assert directory == pathlib.Path(f"usa/tx/austin/{calver}")
    directory = await exporter.mkdir_calver_directory(store, "usa", "austin", "tx")
    assert directory == pathlib.Path(f"usa/tx/austin/{calver}.1")
    directory = await exporter.mkdir_calver_directory(store, "usa", "austin", "tx")
    assert directory == pathlib.Path(f"usa/tx/austin/{calver}.2")
