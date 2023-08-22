import typer

app = typer.Typer()


@app.command()
def s3() -> None:
    """Export results to S3."""
    # Retrieve the state info if needed.
    s3_()


# pylint: disable=too-many-arguments,duplicate-code
def s3_() -> None:
    """Export results to S3."""
    return None
