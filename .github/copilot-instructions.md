# Brokenspoke‑Analyzer – Copilot Custom Instructions

## Project overview

- This repository runs Bicycle Network Analysis and relies on Python, PostgreSQL
  and PostGIS.
- **Project Management**: `uv` is the primary tool for environment and package
  management, and running commands.
- **Language**: Python 3.13 (or latest supported)
- **Data layer**: PostgreSQL with PostGIS extensions
- **SQL assets**: `.sql` files contain GIS queries that are executed via
  `psycopg2`
- **Requirements language**: EARS (Event‑Action‑Response‑Specification) – see
  [https://alistairmavin.com/ears/](https://alistairmavin.com/ears/)

## Coding style & conventions

- The conventions must be codified in the `pyproject.toml` file or the
  configuration files of the dedicated tool.
- Tasks must be created in the `Justfile`.

- **Python**
  - Follow the default _ruff_ formatter and linting rules.
  - Use type hints everywhere (`def foo(bar: int) -> List[str]: …`).
  - All functions/classes must have a doctring with **Parameters**, **Returns**,
    and **Raises** sections.
  - All functions must use doctests when applicable. Ideally at the the happy
    path should be represented using a doctest.
  - Doctests must use the **xdoctest** syntax.
  - Sort imports using _isort_.
    - Use `profile = "black"` and `force_grid_wrap = 2` settings.
- **SQL**
  - Use `sqlfluff` for linting and fixing the SQL files.
- **EARS**
  - Every functional requirement is expressed as an EARS sentence in
    `docs/requirements/`.
  - Patterns to Enforce:
    - Ubiquitous: The `<system>` SHALL `<response>`.
    - Event-Driven: WHEN `<trigger>`, the `<system>` SHALL `<response>`.
    - State-Driven: WHILE `<precondition>`, the `<system>` SHALL `<response>`.
    - Unwanted Behavior: IF `<event>`, THEN the `<system>` SHALL `<response>`.
    - Optional Feature: WHERE `<feature>`, the `<system>` SHALL `<response>`.

  - Review Rule: Flag any requirement using "must", "should", or "will". Insist
    on the keyword SHALL.

- Example:

  ```ears
  WHEN a new bike‑trip record is inserted,
  THE system SHALL compute the nearest road segment and store the result.
  ```

- Copilot should surface the corresponding SQL snippet when a developer asks for
  “the EARS clause for X”.

## Common tasks we want Copilot to help with

- Generate boiler‑plate Python modules (CLI entry point, DB connection wrapper,
  logging config).
- Write parameterised GIS SQL from an EARS description (e.g., “find all trips
  intersecting a buffer around a station”).
- Create unit‑test scaffolding using `pytest`.
- Suggest doc‑string templates that map an EARS clause to the implementation
  function.
- Detect missing/unused SQL parameters\*\* and propose fixes.
- Review GitHub workflows and propose improvements.

## Code review goals (what to check and how to write feedback)

For every PR, prioritize (in order):

1. Security and secrets safety
2. Correctness of analysis results and edge cases
3. SQL safety (parameterization, dynamic SQL hygiene, transactional correctness)
4. Performance risks (especially spatial joins / large scans)
5. Test coverage and reproducibility
6. Documentation

### Required review behaviors

- Always identify which files are Python vs SQL vs CI/config and tailor feedback
  accordingly.
- If SQL changes exist, explicitly discuss:
  - schema/objects touched (tables, views, functions)
  - correctness risks (SRID, geometry vs geography, joins, aggregations)
  - performance risks and whether EXPLAIN or indexes are needed
- If Python code constructs SQL dynamically, require safe parameterization and
  reject unsafe string interpolation.

### Security & quality guards

- Never embed plaintext credentials.
- Never suggest committing secrets or real credentials.
- Always reference environment variables (e.g. `POSTGRES_URL`,
  `POSTGRES_PASSWORD`, `DATABASE_URL`).
  - Treat these values as sensitive unless clearly placeholders.

## Output format

Provide review feedback using:

- Scope
- Risk assessment
- Must-fix
- Should-fix
- Questions
- Suggested verification commands\*\* (must be realistic for this repo)

## Guidance boundaries

- Prefer small, reviewable diffs.
- Ask questions, do not guess.

## How to invoke Copilot effectively

- Include the **EARS phrase** in your prompt.
  > _“Implement the EARS requirement: ‘When a bike‑trip is created, calculate
  > the distance to the nearest bike‑lane.’”_
- Mention the target file type if you need a specific artifact:
  > _“Give me a `.sql` snippet for the above requirement.”_
- Ask for a **doc‑string** after the function is scaffolded:
  > _“Add a doc‑string that references the EARS sentence.”_

---

_These instructions are automatically injected into every Copilot chat request
for this repository._
