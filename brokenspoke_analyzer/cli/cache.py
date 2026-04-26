"""Define the cache sub-command."""

from typing import Annotated

import rich
import typer
from loguru import logger

from brokenspoke_analyzer.core import (
    file_utils,
)

app = typer.Typer()
console = rich.get_console()


@app.command()
def clean(
    dry_run: Annotated[  # noqa: FBT002
        bool | None,
        typer.Option("--dry-run", "-n", help="Dry run"),
    ] = False,
    quiet: Annotated[  # noqa: FBT002
        bool | None,
        typer.Option("--quiet", "-q", help="Quiet mode"),
    ] = False,
) -> None:
    """Clean the cache directory."""
    console.log("[green]Cleaning cache...")
    cache_dir = file_utils.get_user_cache_dir()
    try:
        result = file_utils.delete_folder_contents_safe(
            cache_dir,
            dry_run=bool(dry_run),
        )
        if not quiet:
            if dry_run:
                typer.echo("=== DRY RUN PREVIEW ===")
            typer.echo(f"Deleted {result.total_item_count} items (including hidden)")
            typer.echo(f"Space reclaimed: {result.space_gb} GB")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Error: {e}")
    logger.info("Cache cleaned.")


@app.command(name="dir")
def dir_() -> None:
    """Show the cache directory."""
    typer.echo(file_utils.get_user_cache_dir())
