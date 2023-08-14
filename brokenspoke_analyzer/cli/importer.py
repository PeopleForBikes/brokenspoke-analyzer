import asyncio

import typer

app = typer.Typer()


@app.command()
def all():
    """Import all files into database."""
    # Retrieve the state info if needed.
    asyncio.run(all_())


# pylint: disable=too-many-arguments,duplicate-code
def all_():
    """Import all files into database."""
