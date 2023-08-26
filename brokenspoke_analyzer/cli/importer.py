import typer

app = typer.Typer()


@app.command()
def all() -> None:
    """Import all files into database."""
    # Retrieve the state info if needed.
    all_()


# pylint: disable=too-many-arguments,duplicate-code
def all_() -> None:
    """Import all files into database."""
    return None
