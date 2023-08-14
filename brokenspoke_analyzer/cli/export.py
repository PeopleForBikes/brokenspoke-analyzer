import asyncio

import typer

app = typer.Typer()


@app.command()
def s3():
    """Export results to S3."""
    # Retrieve the state info if needed.
    asyncio.run(s3_())


# pylint: disable=too-many-arguments,duplicate-code
def s3_():
    """Export results to S3."""
