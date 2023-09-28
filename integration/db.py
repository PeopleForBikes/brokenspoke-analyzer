import pathlib

from brokenspoke_analyzer.core.database import (
    dbcore,
    models,
)


def test_create_tables():
    """"""
    database_url = "postgresql://postgres:postgres@localhost:5432/postgres"
    engine = dbcore.create_psycopg_engine(database_url)
    models.Base.metadata.drop_all(engine)
    models.Base.metadata.create_all(engine)
    dbcore.import_csv_file_with_header(
        engine,
        pathlib.Path("data/santa-rosa-new-mexico-usa/state_fips_speed.csv"),
        "state_speed",
    )
    dbcore.import_csv_file_with_header(
        engine,
        pathlib.Path("data/santa-rosa-new-mexico-usa/city_fips_speed.csv"),
        "city_speed",
    )
