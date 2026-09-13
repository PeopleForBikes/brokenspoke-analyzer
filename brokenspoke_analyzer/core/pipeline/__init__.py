"""
Define the pure-Python BNA pipeline.

Replace the SQL/PostGIS stages of the analysis with typed, independently
testable Python. Each stage module exposes pure functions shaped as
`GeoDataFrame(s)/DataFrame(s) in -> GeoDataFrame(s)/DataFrame(s) out`, so a
scoring rule can be exercised without a database or a full pipeline run:

- `ingest`: parse the OSM extract into ways/nodes and build routing topology.
- `features`: derive the per-way attributes (bike infra, lanes, speed, ...).
- `stress`: classify segment and intersection traffic stress.
- `network`: build the turn-expanded graph and compute per-block reachability.
- `scoring`: turn reachability into access, category, and overall scores.

See `specs/0003-sql-to-python-migration/` for the requirements, design, and
task breakdown this package implements.
"""
