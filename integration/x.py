# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "isort>=7.0.0",
#     "minijinja>=2.13.0",
#     "ruff>=0.14.8",
#     "xdoctest>=1.3.0",
# ]
# ///
"""
Render the Markdown file from the CSV file.

Run with:
    uv run x.py e2e-cities.csv README.j2

Format with:
    uv tool run isort x.py --profile black --fgw 2
    uv tool run ruff format x.py

Test with:
    uv tool run xdoctest x.py
"""

import csv
import pathlib
import sys

from minijinja import Environment

ANALYZER_REPO = "https://github.com/PeopleForBikes/brokenspoke-analyzer"
ANALYZER_PULL = f"{ANALYZER_REPO}/pull"
ANALYZER_ISSUE = f"{ANALYZER_REPO}/issue"


def main() -> None:
    """Render the template from the e2e CSV file."""
    data = {}

    # Read and process the e2e test case file.
    csv_file = argument = sys.argv[1]
    e2e_cities = pathlib.Path(csv_file)
    with e2e_cities.open(mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            # Process the replacements
            row["test_size"] = test_size(row["test_size"])
            row["country_flag"] = country(row["country"])
            issues = row["issues"]
            if issues:
                issue_links = [
                    f"[#{issue}]({ANALYZER_ISSUE}/{issue})"
                    for issue in issues.split(",")
                ]
                row["issues"] = ", ".join(issue_links)
            prs = row["prs"]
            if prs:
                pr_links = [f"[#{pr}]({ANALYZER_PULL}/{pr})" for pr in prs.split(",")]
                row["prs"] = ", ".join(pr_links)
            data[row["city"]] = row

    # Load the template.
    j2_file = sys.argv[2]
    j2_template = pathlib.Path(j2_file)
    template_string = j2_template.read_text()

    # Render it.
    env = Environment()
    rendered = env.render_str(template_string, data=data)

    # Save it.
    readme = j2_template.with_suffix(".md")
    readme.write_text(rendered)


def test_size(value: str) -> str:
    """
    Convert the t-shirt size to a colored circle.

    Example:
        >>> test_size("S")
        '🟢'
        >>> test_size("unknown")
        'unknown'
    """
    match value:
        case "XS":
            return "🔵"
        case "S":
            return "🟢"
        case "M":
            return "🟡"
        case "L":
            return "🟠"
        case "XL":
            return "🔴"
        case "XXL":
            return "🟣"
        case _:
            return value


def country(value: str) -> str:
    """
    Convert the country name to its flag.

    Example:
        >>>country("canada")
        '🇨🇦'
        >>>country("unknown")
        'unknown'
    """
    match value:
        case "australia":
            return "🇦🇺"
        case "canada":
            return "🇨🇦"
        case "france":
            return "🇫🇷"
        case "spain":
            return "🇪🇸"
        case "united states":
            return "🇺🇸"
        case _:
            return value


if __name__ == "__main__":
    main()
