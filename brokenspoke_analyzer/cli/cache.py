"""Define the cache sub-command."""

import typing

import rich
import typer
from loguru import logger
from typing_extensions import Annotated

from brokenspoke_analyzer.core import (
    file_utils,
)

app = typer.Typer()
console = rich.get_console()


@app.command()
def clean(
    dry_run: Annotated[
        typing.Optional[bool], typer.Option("--dry-run", "-n", help="Dry run")
    ] = False,
    quiet: Annotated[
        typing.Optional[bool], typer.Option("--quiet", "-q", help="Quiet mode")
    ] = False,
) -> None:
    """Clean the cache directory."""
    console.log("[green]Cleaning cache...")
    cache_dir = file_utils.get_user_cache_dir()
    try:
        result = file_utils.delete_folder_contents_safe(
            cache_dir, dry_run=bool(dry_run)
        )
        if not quiet:
            if dry_run:
                print(f"=== DRY RUN PREVIEW ===")
            print(f"Deleted {result.total_item_count} items (including hidden)")
            print(f"Space reclaimed: {result.space_gb} GB")
    except Exception as e:
        print(f"Error: {e}")
    logger.info("Cache cleaned.")


@app.command()
def dir() -> None:
    """Show the cache directory."""
    print(file_utils.get_user_cache_dir())
