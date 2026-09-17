r"""
The diagnostic score table, `score_inputs.csv`.

Reproduce `score_inputs.sql`: 132 city-level summary rows, each a category,
a name, one number and two sentences of prose. Sixteen of them carry a
`use_*` flag and are what `overall_scores.sql` reads to build the headline
table (`scoring.OVERALL_SCORE_ROWS`); the other 116 are published for
diagnosis only and feed no score (findings.md §1.13).

The 132 rows follow one template per category -- three block percentiles, a
block ratio, the population-weighted score, and for categories with a
destination table a shed ratio and three shed percentiles -- so the *formula*
of every row is one of five kinds. The prose is not templated: it was written
by hand, category by category, and is carried here verbatim (the same text
`REGEXP_REPLACE('...', '\n\s+', ' ', 'g')` produced), because the file is a
published artifact whose row contents are part of the contract
(requirements.md FR-EXPORT-1).
"""

import dataclasses
import typing

import geopandas as gpd
import numpy as np
import pandas as pd

from brokenspoke_analyzer.core.pipeline.features import _column

# `score NUMERIC(16, 4)`.
SCORE_DECIMALS = 4

# The `use_*` columns, in table order. Each flagged row sets exactly one.
USE_FLAGS = (
    "use_pop",
    "use_emp",
    "use_k12",
    "use_tech",
    "use_univ",
    "use_doctor",
    "use_dentist",
    "use_hospital",
    "use_pharmacy",
    "use_retail",
    "use_grocery",
    "use_social_svcs",
    "use_parks",
    "use_trails",
    "use_comm_ctrs",
    "use_transit",
)


@dataclasses.dataclass(frozen=True)
class BlockPercentile:
    """`PERCENTILE_CONT(q)` of `<member>_low_stress / NULLIF(<member>_high_stress, 0)`.

    Over the blocks intersecting the boundary; a block whose ratio is NULL --
    nothing reachable at all -- is left out, and no blocks at all is NULL.
    """

    member: str
    quantile: float


@dataclasses.dataclass(frozen=True)
class BlockRatio:
    """`SUM(<member>_low_stress) / SUM(<member>_high_stress)` over the blocks.

    Zero when the high-stress total is zero, NULL when there is no total at
    all (every block NULL). Only the population and employment rows cast to
    FLOAT first; every destination row divides two integers, and PostgreSQL
    integer division truncates -- so "Average score of low stress access to
    schools" is 0 in every city where fewer than all schools are reachable
    comfortably, which is every city. Reproduced as written.
    """

    member: str
    float_division: bool


@dataclasses.dataclass(frozen=True)
class Weighted:
    """`SUM(pop20 * <member>_score / tmp_pop.<member>)` over the blocks.

    The population-weighted score `overall_scores.sql` reads back
    (`scoring.population_weighted_score`), with one difference: here a NULL
    stays NULL. `overall_scores.sql` wraps it in `COALESCE(..., 0)`; this
    table does not, so a city without employment data publishes an empty
    `Average score of access to jobs`.
    """

    member: str


@dataclasses.dataclass(frozen=True)
class ShedRatio:
    """`SUM(pop_low_stress)::FLOAT / SUM(pop_high_stress)` over the destinations.

    Over `neighborhood_<member>`'s rows inside the boundary. Zero when the
    total is zero, NULL when there are no destinations (or none with a shed).
    """

    member: str


@dataclasses.dataclass(frozen=True)
class ShedPercentile:
    """`PERCENTILE_CONT(q)` of `pop_low_stress / NULLIF(pop_high_stress, 0)`.

    Over `neighborhood_<member>`'s rows inside the boundary, NULLs left out.
    """

    member: str
    quantile: float


Formula = BlockPercentile | BlockRatio | Weighted | ShedRatio | ShedPercentile


@dataclasses.dataclass(frozen=True)
class ScoreInput:
    """One row of `score_inputs.sql`, in insertion order."""

    category: str
    score_name: str
    formula: Formula
    flag: str | None
    notes: str
    human_explanation: str


# Every `INSERT` of `score_inputs.sql`, in order; `id` is the 1-based position.
SCORE_INPUTS: tuple[ScoreInput, ...] = (
    ScoreInput(
        "People",
        "Median score of access to population",
        BlockPercentile("pop", 0.5),
        None,
        "Score of population accessible by low stress to population accessible overall, expressed as the median of all census blocks in the neighborhood",
        "Half of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, half have a lower ratio.",
    ),
    ScoreInput(
        "People",
        "70th percentile score of access to population",
        BlockPercentile("pop", 0.7),
        None,
        "Score of population accessible by low stress to population accessible overall, expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, 70% have a lower ratio.",
    ),
    ScoreInput(
        "People",
        "30th percentile score of access to population",
        BlockPercentile("pop", 0.3),
        None,
        "Score of population accessible by low stress to population accessible overall, expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, 30% have a lower ratio.",
    ),
    ScoreInput(
        "People",
        "Average score of access to population",
        BlockRatio("pop", float_division=True),
        None,
        "Score of population accessible by low stress to population accessible overall, expressed as the average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have this ratio of low stress to high stress access.",
    ),
    ScoreInput(
        "People",
        "Average score of access to population",
        Weighted("pop"),
        "use_pop",
        "Average population score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this population score.",
    ),
    ScoreInput(
        "Opportunity",
        "Median score of access to employment",
        BlockPercentile("emp", 0.5),
        None,
        "Score of employment accessible by low stress to employment accessible overall, expressed as the median of all census blocks in the neighborhood",
        "Half of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, half have a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile score of access to employment",
        BlockPercentile("emp", 0.7),
        None,
        "Score of employment accessible by low stress to employment accessible overall, expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, 70% have a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile score of access to employment",
        BlockPercentile("emp", 0.3),
        None,
        "Score of employment accessible by low stress to employment accessible overall, expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of all census blocks in the neighborhood have a ratio of low stress to high stress access above this number, 30% have a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of access to employment",
        BlockRatio("emp", float_division=True),
        None,
        "Score of employment accessible by low stress to employment accessible overall, expressed as the average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have this ratio of low stress to high stress access.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of access to jobs",
        Weighted("emp"),
        "use_emp",
        "Average employment score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this employment score.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of low stress access to schools",
        BlockRatio("schools", float_division=False),
        None,
        "Number of schools accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many schools.",
    ),
    ScoreInput(
        "Opportunity",
        "Median score of school access",
        BlockPercentile("schools", 0.5),
        None,
        "Score of schools accessible by low stress compared to schools accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of schools within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile score of school access",
        BlockPercentile("schools", 0.7),
        None,
        "Score of schools accessible by low stress compared to schools accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of schools within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile score of school access",
        BlockPercentile("schools", 0.3),
        None,
        "Score of schools accessible by low stress compared to schools accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of schools within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of access to K12 schools",
        Weighted("schools"),
        "use_k12",
        "Average K12 schools score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this K12 schools score.",
    ),
    ScoreInput(
        "Opportunity",
        "Average school bike shed access score",
        ShedRatio("schools"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of schools in the neighborhood expressed as an average of all schools in the neighborhood",
        "On average, schools in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Opportunity",
        "Median school population shed score",
        ShedPercentile("schools", 0.5),
        None,
        "Score of population with low stress access to schools in the neighborhood to total population within the bike shed of each school expressed as a median of all schools in the neighborhood",
        "Half of schools in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage.",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile school population shed score",
        ShedPercentile("schools", 0.7),
        None,
        "Score of population with low stress access to schools in the neighborhood to total population within the bike shed of each school expressed as the 70th percentile of all schools in the neighborhood",
        "30% of schools in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage.",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile school population shed score",
        ShedPercentile("schools", 0.3),
        None,
        "Score of population with low stress access to schools in the neighborhood to total population within the bike shed of each school expressed as the 30th percentile of all schools in the neighborhood",
        "70% of schools in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of low stress access to tech/vocational colleges",
        BlockRatio("colleges", float_division=False),
        None,
        "Number of tech/vocational colleges accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many tech/vocational colleges.",
    ),
    ScoreInput(
        "Opportunity",
        "Median score of tech/vocational college access",
        BlockPercentile("colleges", 0.5),
        None,
        "Score of tech/vocational colleges accessible by low stress compared to tech/vocational colleges accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of tech/vocational colleges within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile score of tech/vocational college access",
        BlockPercentile("colleges", 0.7),
        None,
        "Score of tech/vocational colleges accessible by low stress compared to tech/vocational colleges accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of tech/vocational colleges within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile score of tech/vocational college access",
        BlockPercentile("colleges", 0.3),
        None,
        "Score of tech/vocational colleges accessible by low stress compared to tech/vocational colleges accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of tech/vocational colleges within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of access to tech/vocational colleges",
        Weighted("colleges"),
        "use_tech",
        "Average tech/vocational colleges score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this tech/vocational colleges score.",
    ),
    ScoreInput(
        "Opportunity",
        "Average college bike shed access score",
        ShedRatio("colleges"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of tech/vocational colleges in the neighborhood expressed as an average of all colleges in the neighborhood",
        "On average, colleges in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Opportunity",
        "Median tech/vocational college population shed score",
        ShedPercentile("colleges", 0.5),
        None,
        "Score of population with low stress access to tech/vocational colleges in the neighborhood to total population within the bike shed of each college expressed as a median of all colleges in the neighborhood",
        "Half of tech/vocational colleges in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one tech/vocational college exists this is the score for  that one location)",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile tech/vocational college population shed score",
        ShedPercentile("colleges", 0.7),
        None,
        "Score of population with low stress access to tech/vocational colleges in the neighborhood to total population within the bike shed of each college expressed as the 70th percentile of all colleges in the neighborhood",
        "30% of tech/vocational colleges in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one tech/vocational college exists this is the score for  that one location)",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile tech/vocational college population shed score",
        ShedPercentile("colleges", 0.3),
        None,
        "Score of population with low stress access to tech/vocational colleges in the neighborhood to total population within the bike shed of each college expressed as the 30th percentile of all colleges in the neighborhood",
        "70% of tech/vocational colleges in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one tech/vocational college exists this is the score for  that one location)",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of low stress access to universities",
        BlockRatio("universities", float_division=False),
        None,
        "Number of universities accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many universities.",
    ),
    ScoreInput(
        "Opportunity",
        "Median score of university access",
        BlockPercentile("universities", 0.5),
        None,
        "Score of universities accessible by low stress compared to universities accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of universities within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile score of university access",
        BlockPercentile("universities", 0.7),
        None,
        "Score of universities accessible by low stress compared to universities accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of universities within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile score of university access",
        BlockPercentile("universities", 0.3),
        None,
        "Score of universities accessible by low stress compared to universities accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of universities within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Opportunity",
        "Average score of access to universities",
        Weighted("universities"),
        "use_univ",
        "Average universities score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this universities score.",
    ),
    ScoreInput(
        "Opportunity",
        "Average university bike shed access score",
        ShedRatio("universities"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of universities in the neighborhood expressed as an average of all universities in the neighborhood",
        "On average, universities in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Opportunity",
        "Median university population shed score",
        ShedPercentile("universities", 0.5),
        None,
        "Score of population with low stress access to universities in the neighborhood to total population within the bike shed of each university expressed as a median of all universities in the neighborhood",
        "Half of universities in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one university exists this is the score for that one location)",
    ),
    ScoreInput(
        "Opportunity",
        "70th percentile university population shed score",
        ShedPercentile("universities", 0.7),
        None,
        "Score of population with low stress access to universities in the neighborhood to total population within the bike shed of each university expressed as the 70th percentile of all universities in the neighborhood",
        "30% of universities in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one university exists this is the score for that one location)",
    ),
    ScoreInput(
        "Opportunity",
        "30th percentile university population shed score",
        ShedPercentile("universities", 0.3),
        None,
        "Score of population with low stress access to universities in the neighborhood to total population within the bike shed of each university expressed as the 30th percentile of all universities in the neighborhood",
        "70% of universities in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one university exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to doctors",
        BlockRatio("doctors", float_division=False),
        None,
        "Number of doctors accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many doctors.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of doctors access",
        BlockPercentile("doctors", 0.5),
        None,
        "Score of doctors accessible by low stress compared to doctors accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of doctors within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of doctors access",
        BlockPercentile("doctors", 0.7),
        None,
        "Score of doctors accessible by low stress compared to doctors accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of doctors within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of doctors access",
        BlockPercentile("doctors", 0.3),
        None,
        "Score of doctors accessible by low stress compared to doctors accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of doctors within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to doctors",
        Weighted("doctors"),
        "use_doctor",
        "Average doctors score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this doctors score.",
    ),
    ScoreInput(
        "Core Services",
        "Average doctors bike shed access score",
        ShedRatio("doctors"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of doctors in the neighborhood expressed as an average of all doctors in the neighborhood",
        "On average, doctors in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median doctors population shed score",
        ShedPercentile("doctors", 0.5),
        None,
        "Score of population with low stress access to doctors in the neighborhood to total population within the bike shed of each doctors office expressed as a median of all doctors in the neighborhood",
        "Half of doctors in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one doctors office exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile doctors population shed score",
        ShedPercentile("doctors", 0.7),
        None,
        "Score of population with low stress access to doctors in the neighborhood to total population within the bike shed of each doctors office expressed as the 70th percentile of all doctors in the neighborhood",
        "30% of doctors in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one doctors exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile doctors population shed score",
        ShedPercentile("doctors", 0.3),
        None,
        "Score of population with low stress access to doctors in the neighborhood to total population within the bike shed of each doctors office expressed as the 30th percentile of all doctors in the neighborhood",
        "70% of doctors in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one doctors exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to dentists",
        BlockRatio("dentists", float_division=False),
        None,
        "Number of dentists accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many dentists.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of dentists access",
        BlockPercentile("dentists", 0.5),
        None,
        "Score of dentists accessible by low stress compared to dentists accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of dentists within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of dentists access",
        BlockPercentile("dentists", 0.7),
        None,
        "Score of dentists accessible by low stress compared to dentists accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of dentists within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of dentists access",
        BlockPercentile("dentists", 0.3),
        None,
        "Score of dentists accessible by low stress compared to dentists accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of dentists within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to dentists",
        Weighted("dentists"),
        "use_dentist",
        "Average dentists score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this dentists score.",
    ),
    ScoreInput(
        "Core Services",
        "Average dentists bike shed access score",
        ShedRatio("dentists"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of dentists in the neighborhood expressed as an average of all dentists in the neighborhood",
        "On average, dentists in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median dentists population shed score",
        ShedPercentile("dentists", 0.5),
        None,
        "Score of population with low stress access to dentists in the neighborhood to total population within the bike shed of each dentists office expressed as a median of all dentists in the neighborhood",
        "Half of dentists in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one dentists office exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile dentists population shed score",
        ShedPercentile("dentists", 0.7),
        None,
        "Score of population with low stress access to dentists in the neighborhood to total population within the bike shed of each dentists office expressed as the 70th percentile of all dentists in the neighborhood",
        "30% of dentists in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one dentists office exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile dentists population shed score",
        ShedPercentile("dentists", 0.3),
        None,
        "Score of population with low stress access to dentists in the neighborhood to total population within the bike shed of each dentists office expressed as the 30th percentile of all dentists in the neighborhood",
        "70% of dentists in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one dentists office exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to hospitals",
        BlockRatio("hospitals", float_division=False),
        None,
        "Number of hospitals accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many hospitals.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of hospitals access",
        BlockPercentile("hospitals", 0.5),
        None,
        "Score of hospitals accessible by low stress compared to hospitals accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of hospitals within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of hospitals access",
        BlockPercentile("hospitals", 0.7),
        None,
        "Score of hospitals accessible by low stress compared to hospitals accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of hospitals within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of hospitals access",
        BlockPercentile("hospitals", 0.3),
        None,
        "Score of hospitals accessible by low stress compared to hospitals accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of hospitals within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to hospitals",
        Weighted("hospitals"),
        "use_hospital",
        "Average hospital score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this hospital score.",
    ),
    ScoreInput(
        "Core Services",
        "Average hospitals bike shed access score",
        ShedRatio("hospitals"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of hospitals in the neighborhood expressed as an average of all hospitals in the neighborhood",
        "On average, hospitals in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median hospitals population shed score",
        ShedPercentile("hospitals", 0.5),
        None,
        "Score of population with low stress access to hospitals in the neighborhood to total population within the bike shed of each hospital expressed as a median of all hospitals in the neighborhood",
        "Half of hospitals in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one hospital exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile hospitals population shed score",
        ShedPercentile("hospitals", 0.7),
        None,
        "Score of population with low stress access to hospitals in the neighborhood to total population within the bike shed of each hospital expressed as the 70th percentile of all hospitals in the neighborhood",
        "30% of hospitals in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one hospital exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile hospitals population shed score",
        ShedPercentile("hospitals", 0.3),
        None,
        "Score of population with low stress access to hospitals in the neighborhood to total population within the bike shed of each hospital expressed as the 30th percentile of all hospitals in the neighborhood",
        "70% of hospitals in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one hospital exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to pharmacies",
        BlockRatio("pharmacies", float_division=False),
        None,
        "Number of pharmacies accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many pharmacies.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of pharmacies access",
        BlockPercentile("pharmacies", 0.5),
        None,
        "Score of pharmacies accessible by low stress compared to pharmacies accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of pharmacies within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of pharmacies access",
        BlockPercentile("pharmacies", 0.7),
        None,
        "Score of pharmacies accessible by low stress compared to pharmacies accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of pharmacies within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of pharmacies access",
        BlockPercentile("pharmacies", 0.3),
        None,
        "Score of pharmacies accessible by low stress compared to pharmacies accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of pharmacies within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to pharmacies",
        Weighted("pharmacies"),
        "use_pharmacy",
        "Average pharmacies score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this pharmacies score.",
    ),
    ScoreInput(
        "Core Services",
        "Average pharmacies bike shed access score",
        ShedRatio("pharmacies"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of pharmacies in the neighborhood expressed as an average of all pharmacies in the neighborhood",
        "On average, pharmacies in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median pharmacies population shed score",
        ShedPercentile("pharmacies", 0.5),
        None,
        "Score of population with low stress access to pharmacies in the neighborhood to total population within the bike shed of each pharmacy expressed as a median of all pharmacies in the neighborhood",
        "Half of pharmacies in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one pharmacy exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile pharmacies population shed score",
        ShedPercentile("pharmacies", 0.7),
        None,
        "Score of population with low stress access to pharmacies in the neighborhood to total population within the bike shed of each pharmacy expressed as the 70th percentile of all pharmacies in the neighborhood",
        "30% of pharmacies in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one pharmacy exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile pharmacies population shed score",
        ShedPercentile("pharmacies", 0.3),
        None,
        "Score of population with low stress access to pharmacies in the neighborhood to total population within the bike shed of each pharmacy expressed as the 30th percentile of all pharmacies in the neighborhood",
        "70% of pharmacies in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one pharmacy exists this is the score for that one location)",
    ),
    ScoreInput(
        "Retail",
        "Average score of low stress access to retail",
        BlockRatio("retail", float_division=False),
        None,
        "Number of retail accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many retail.",
    ),
    ScoreInput(
        "Retail",
        "Median score of retail access",
        BlockPercentile("retail", 0.5),
        None,
        "Score of retail accessible by low stress compared to retail accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of retail within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Retail",
        "70th percentile score of retail access",
        BlockPercentile("retail", 0.7),
        None,
        "Score of retail accessible by low stress compared to retail accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of retail within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Retail",
        "30th percentile score of retail access",
        BlockPercentile("retail", 0.3),
        None,
        "Score of retail accessible by low stress compared to retail accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of retail within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Retail",
        "Average score of access to retail",
        Weighted("retail"),
        "use_retail",
        "Average retail score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this retail score.",
    ),
    ScoreInput(
        "Retail",
        "Average retail bike shed access score",
        ShedRatio("retail"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of retail clusters in the neighborhood expressed as an average of all retail clusters in the neighborhood",
        "On average, retail clusters in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Retail",
        "Median retail population shed score",
        ShedPercentile("retail", 0.5),
        None,
        "Score of population with low stress access to retail in the neighborhood to total population within the bike shed of each retail cluster expressed as a median of all retail clusters in the neighborhood",
        "Half of retail clusters in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one retail exists this is the score for that one location)",
    ),
    ScoreInput(
        "Retail",
        "70th percentile retail population shed score",
        ShedPercentile("retail", 0.7),
        None,
        "Score of population with low stress access to retail in the neighborhood to total population within the bike shed of each retail cluster expressed as the 70th percentile of all retail clusters in the neighborhood",
        "30% of retail clusters in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one retail exists this is the score for that one location)",
    ),
    ScoreInput(
        "Retail",
        "30th percentile retail population shed score",
        ShedPercentile("retail", 0.3),
        None,
        "Score of population with low stress access to retail in the neighborhood to total population within the bike shed of each retail cluster expressed as the 30th percentile of all retail clusters in the neighborhood",
        "70% of retail clusters in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one retail exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to supermarkets",
        BlockRatio("supermarkets", float_division=False),
        None,
        "Number of supermarkets accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many supermarkets.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of supermarkets access",
        BlockPercentile("supermarkets", 0.5),
        None,
        "Score of supermarkets accessible by low stress compared to supermarkets accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of supermarkets within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of supermarkets access",
        BlockPercentile("supermarkets", 0.7),
        None,
        "Score of supermarkets accessible by low stress compared to supermarkets accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of supermarkets within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of supermarkets access",
        BlockPercentile("supermarkets", 0.3),
        None,
        "Score of supermarkets accessible by low stress compared to supermarkets accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of supermarkets within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to grocery stores",
        Weighted("supermarkets"),
        "use_grocery",
        "Average grocery score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this grocery score.",
    ),
    ScoreInput(
        "Core Services",
        "Average supermarkets bike shed access score",
        ShedRatio("supermarkets"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of supermarkets in the neighborhood expressed as an average of all supermarkets in the neighborhood",
        "On average, supermarkets in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median supermarkets population shed score",
        ShedPercentile("supermarkets", 0.5),
        None,
        "Score of population with low stress access to supermarkets in the neighborhood to total population within the bike shed of each supermarket expressed as a median of all supermarkets in the neighborhood",
        "Half of supermarkets in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one supermarkets exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile supermarkets population shed score",
        ShedPercentile("supermarkets", 0.7),
        None,
        "Score of population with low stress access to supermarkets in the neighborhood to total population within the bike shed of each supermarket expressed as the 70th percentile of all supermarkets in the neighborhood",
        "30% of supermarkets in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one supermarkets exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile supermarkets population shed score",
        ShedPercentile("supermarkets", 0.3),
        None,
        "Score of population with low stress access to supermarkets in the neighborhood to total population within the bike shed of each supermarket expressed as the 30th percentile of all supermarkets in the neighborhood",
        "70% of supermarkets in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one supermarkets exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "Average score of low stress access to social services",
        BlockRatio("social_services", float_division=False),
        None,
        "Number of social services accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many social services.",
    ),
    ScoreInput(
        "Core Services",
        "Median score of social services access",
        BlockPercentile("social_services", 0.5),
        None,
        "Score of social services accessible by low stress compared to social services accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of social services within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile score of social services access",
        BlockPercentile("social_services", 0.7),
        None,
        "Score of social services accessible by low stress compared to social services accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of social services within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile score of social services access",
        BlockPercentile("social_services", 0.3),
        None,
        "Score of social services accessible by low stress compared to social services accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of social services within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Core Services",
        "Average score of access to social services",
        Weighted("social_services"),
        "use_social_svcs",
        "Average social services score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this social services score.",
    ),
    ScoreInput(
        "Core Services",
        "Average social_services bike shed access score",
        ShedRatio("social_services"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of social services in the neighborhood expressed as an average of all social services in the neighborhood",
        "On average, social_services in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Core Services",
        "Median social_services population shed score",
        ShedPercentile("social_services", 0.5),
        None,
        "Score of population with low stress access to social services in the neighborhood to total population within the bike shed of each social service location expressed as a median of all social services in the neighborhood",
        "Half of social services in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one social_services exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "70th percentile social_services population shed score",
        ShedPercentile("social_services", 0.7),
        None,
        "Score of population with low stress access to social services in the neighborhood to total population within the bike shed of each social service location expressed as the 70th percentile of all social services in the neighborhood",
        "30% of social services in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one social_services exists this is the score for that one location)",
    ),
    ScoreInput(
        "Core Services",
        "30th percentile social_services population shed score",
        ShedPercentile("social_services", 0.3),
        None,
        "Score of population with low stress access to social services in the neighborhood to total population within the bike shed of each social service location expressed as the 30th percentile of all social services in the neighborhood",
        "70% of social services in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one social_services exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "Average score of low stress access to parks",
        BlockRatio("parks", float_division=False),
        None,
        "Number of parks accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many parks.",
    ),
    ScoreInput(
        "Recreation",
        "Median score of parks access",
        BlockPercentile("parks", 0.5),
        None,
        "Score of parks accessible by low stress compared to parks accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of parks within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "70th percentile score of parks access",
        BlockPercentile("parks", 0.7),
        None,
        "Score of parks accessible by low stress compared to parks accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of parks within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "30th percentile score of parks access",
        BlockPercentile("parks", 0.3),
        None,
        "Score of parks accessible by low stress compared to parks accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of parks within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "Average score of access to parks",
        Weighted("parks"),
        "use_parks",
        "Average parks score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this parks score.",
    ),
    ScoreInput(
        "Recreation",
        "Average parks bike shed access score",
        ShedRatio("parks"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of parks in the neighborhood expressed as an average of all parks in the neighborhood",
        "On average, parks in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Recreation",
        "Median parks population shed score",
        ShedPercentile("parks", 0.5),
        None,
        "Score of population with low stress access to parks in the neighborhood to total population within the bike shed of each parks expressed as a median of all parks in the neighborhood",
        "Half of parks in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one parks exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "70th percentile parks population shed score",
        ShedPercentile("parks", 0.7),
        None,
        "Score of population with low stress access to parks in the neighborhood to total population within the bike shed of each parks expressed as the 70th percentile of all parks in the neighborhood",
        "30% of parks in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one parks exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "30th percentile parks population shed score",
        ShedPercentile("parks", 0.3),
        None,
        "Score of population with low stress access to parks in the neighborhood to total population within the bike shed of each parks expressed as the 30th percentile of all parks in the neighborhood",
        "70% of parks in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one parks exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "Average score of low stress access to trails",
        BlockRatio("trails", float_division=False),
        None,
        "Number of trails accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many trails.",
    ),
    ScoreInput(
        "Recreation",
        "Median score of trails access",
        BlockPercentile("trails", 0.5),
        None,
        "Score of trails accessible by low stress compared to trails accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of trails within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "70th percentile score of trails access",
        BlockPercentile("trails", 0.7),
        None,
        "Score of trails accessible by low stress compared to trails accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of trails within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "30th percentile score of trails access",
        BlockPercentile("trails", 0.3),
        None,
        "Score of trails accessible by low stress compared to trails accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of trails within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "Average score of access to trails",
        Weighted("trails"),
        "use_trails",
        "Average trails score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this trails score.",
    ),
    ScoreInput(
        "Recreation",
        "Average score of low stress access to community centers",
        BlockRatio("community_centers", float_division=False),
        None,
        "Number of community centers accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many community centers.",
    ),
    ScoreInput(
        "Recreation",
        "Median score of community centers access",
        BlockPercentile("community_centers", 0.5),
        None,
        "Score of community centers accessible by low stress compared to community centers accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of community centers within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "70th percentile score of community centers access",
        BlockPercentile("community_centers", 0.7),
        None,
        "Score of community centers accessible by low stress compared to community centers accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of community centers within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "30th percentile score of community centers access",
        BlockPercentile("community_centers", 0.3),
        None,
        "Score of community centers accessible by low stress compared to community centers accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of community centers within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Recreation",
        "Average score of access to community centers",
        Weighted("community_centers"),
        "use_comm_ctrs",
        "Average community centers score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this community centers score.",
    ),
    ScoreInput(
        "Recreation",
        "Average community centers bike shed access score",
        ShedRatio("community_centers"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of community centers in the neighborhood expressed as an average of all community centers in the neighborhood",
        "On average, community centers in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Recreation",
        "Median community centers population shed score",
        ShedPercentile("community_centers", 0.5),
        None,
        "Score of population with low stress access to community centers in the neighborhood to total population within the bike shed of each community centers expressed as a median of all community centers in the neighborhood",
        "Half of community centers in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one community centers exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "70th percentile community centers population shed score",
        ShedPercentile("community_centers", 0.7),
        None,
        "Score of population with low stress access to community centers in the neighborhood to total population within the bike shed of each community centers expressed as the 70th percentile of all community centers in the neighborhood",
        "30% of community centers in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one community centers exists this is the score for that one location)",
    ),
    ScoreInput(
        "Recreation",
        "30th percentile community centers population shed score",
        ShedPercentile("community_centers", 0.3),
        None,
        "Score of population with low stress access to community centers in the neighborhood to total population within the bike shed of each community centers expressed as the 30th percentile of all community centers in the neighborhood",
        "70% of community centers in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one community centers exists this is the score for that one location)",
    ),
    ScoreInput(
        "Transit",
        "Average score of low stress access to transit",
        BlockRatio("transit", float_division=False),
        None,
        "Number of transit stations accessible by low stress expressed as an average of all census blocks in the neighborhood",
        "On average, census blocks in the neighborhood have low stress access to this many transit stations.",
    ),
    ScoreInput(
        "Transit",
        "Median score of transit access",
        BlockPercentile("transit", 0.5),
        None,
        "Score of transit stations accessible by low stress compared to transit stations accessible by high stress expressed as the median of all census blocks in the neighborhood",
        "Half of census blocks in this neighborhood have low stress access to a higher ratio of transit stations within biking distance, half have access to a lower ratio.",
    ),
    ScoreInput(
        "Transit",
        "70th percentile score of transit access",
        BlockPercentile("transit", 0.7),
        None,
        "Score of transit stations accessible by low stress compared to transit stations accessible by high stress expressed as the 70th percentile of all census blocks in the neighborhood",
        "30% of census blocks in this neighborhood have low stress access to a higher ratio of transit stations within biking distance, 70% have access to a lower ratio.",
    ),
    ScoreInput(
        "Transit",
        "30th percentile score of transit access",
        BlockPercentile("transit", 0.3),
        None,
        "Score of transit stations accessible by low stress compared to transit stations accessible by high stress expressed as the 30th percentile of all census blocks in the neighborhood",
        "70% of census blocks in this neighborhood have low stress access to a higher ratio of transit stations within biking distance, 30% have access to a lower ratio.",
    ),
    ScoreInput(
        "Transit",
        "Average score of access to transit",
        Weighted("transit"),
        "use_transit",
        "Average transit score for census blocks weighted by population.",
        "On average, census blocks in the neighborhood received this transit score.",
    ),
    ScoreInput(
        "Transit",
        "Average transit bike shed access score",
        ShedRatio("transit"),
        None,
        "Score of population with low stress access compared to total population within the bike shed distance of transit stations in the neighborhood expressed as an average of all transit stations in the neighborhood",
        "On average, transit stations in the neighborhood are connected by the low stress access to this percentage people within biking distance.",
    ),
    ScoreInput(
        "Transit",
        "Median transit population shed score",
        ShedPercentile("transit", 0.5),
        None,
        "Score of population with low stress access to transit stations in the neighborhood to total population within the bike shed of each transit stations expressed as a median of all transit stations in the neighborhood",
        "Half of transit stations in the neighborhood have low stress connections to a higher percentage of people within biking distance, half are connected to a lower percentage. (if only one transit station exists this is the score for that one location)",
    ),
    ScoreInput(
        "Transit",
        "70th percentile transit population shed score",
        ShedPercentile("transit", 0.7),
        None,
        "Score of population with low stress access to transit stations in the neighborhood to total population within the bike shed of each transit stations expressed as the 70th percentile of all transit stations in the neighborhood",
        "30% of transit stations in the neighborhood have low stress connections to a higher percentage of people within biking distance, 70% are connected to a lower percentage. (if only one transit station exists this is the score for that one location)",
    ),
    ScoreInput(
        "Transit",
        "30th percentile transit population shed score",
        ShedPercentile("transit", 0.3),
        None,
        "Score of population with low stress access to transit stations in the neighborhood to total population within the bike shed of each transit stations expressed as the 30th percentile of all transit stations in the neighborhood",
        "70% of transit stations in the neighborhood have low stress connections to a higher percentage of people within biking distance, 30% are connected to a lower percentage. (if only one transit station exists this is the score for that one location)",
    ),
)


def flagged_explanation(member: str) -> str:
    """Return the `human_explanation` `overall_scores.sql` copies for a member.

    Parameters
    ----------
    member
        The score member, e.g. `schools`.

    Returns
    -------
    str
        The flagged row's explanation.

    Examples
    --------
    >>> flagged_explanation("pop")
    'On average, census blocks in the neighborhood received this population score.'
    """
    for row in SCORE_INPUTS:
        if (
            row.flag
            and isinstance(row.formula, Weighted)
            and row.formula.member == member
        ):
            return row.human_explanation
    raise KeyError(member)


def _percentile(values: pd.Series, quantile: float) -> float:
    """`PERCENTILE_CONT` -- linear interpolation, NULLs ignored, empty is NULL."""
    kept = values.dropna().to_numpy(dtype="float64")
    if not len(kept):
        return np.nan
    return float(np.percentile(kept, quantile * 100, method="linear"))


def _ratio(low: pd.Series, high: pd.Series, *, float_division: bool) -> float:
    """`CASE WHEN SUM(high) = 0 THEN 0 ELSE SUM(low) / SUM(high) END`."""
    if high.notna().sum() == 0:
        return np.nan
    total_high = float(high.sum())
    if total_high == 0:
        return 0.0
    total_low = float(low.sum()) if low.notna().any() else np.nan
    if np.isnan(total_low):
        return np.nan
    if float_division:
        return total_low / total_high
    # PostgreSQL integer division truncates toward zero.
    return float(int(total_low) // int(total_high))


def _weighted(census_blocks: gpd.GeoDataFrame, member: str) -> float:
    """`SUM(CASE WHEN tmp_pop.<m> = 0 THEN 0 ELSE pop20 * score / tmp_pop.<m> END)`."""
    from brokenspoke_analyzer.core.pipeline import scoring  # noqa: PLC0415

    score = pd.to_numeric(_column(census_blocks, f"{member}_score"), errors="coerce")
    if score.isna().all():
        # Every term is NULL, and `SUM()` of nothing but NULLs is NULL --
        # unless the divisor is zero, in which case every term is the
        # literal 0 instead.
        reachable = (
            None
            if member in scoring.WHOLE_POPULATION_MEMBERS
            else f"{member}_high_stress"
        )
        population = pd.to_numeric(
            _column(census_blocks, "pop20"), errors="coerce"
        ).fillna(0)
        if reachable is None:
            total = float(population.sum())
        else:
            counts = pd.to_numeric(
                _column(census_blocks, reachable), errors="coerce"
            ).fillna(0)
            total = float(population[counts != 0].sum())
        return 0.0 if total == 0 else np.nan
    reachable = (
        None if member in scoring.WHOLE_POPULATION_MEMBERS else f"{member}_high_stress"
    )
    return scoring.population_weighted_score(
        census_blocks, f"{member}_score", reachable
    )


def evaluate(
    formula: Formula,
    census_blocks: gpd.GeoDataFrame,
    destinations: dict[str, gpd.GeoDataFrame],
) -> float:
    """Compute one row's score.

    Parameters
    ----------
    formula
        The row's formula.
    census_blocks
        The scored blocks intersecting the boundary.
    destinations
        The destination tables by category, with their population sheds.

    Returns
    -------
    float
        The score, NaN for NULL.
    """
    if isinstance(formula, BlockPercentile):
        low = pd.to_numeric(
            _column(census_blocks, f"{formula.member}_low_stress"), errors="coerce"
        )
        high = pd.to_numeric(
            _column(census_blocks, f"{formula.member}_high_stress"), errors="coerce"
        )
        return _percentile(low / high.replace(0, np.nan), formula.quantile)
    if isinstance(formula, BlockRatio):
        low = pd.to_numeric(
            _column(census_blocks, f"{formula.member}_low_stress"), errors="coerce"
        )
        high = pd.to_numeric(
            _column(census_blocks, f"{formula.member}_high_stress"), errors="coerce"
        )
        return _ratio(low, high, float_division=formula.float_division)
    if isinstance(formula, Weighted):
        return _weighted(census_blocks, formula.member)
    # A destination outside the boundary has no shed at all (NULLs), so
    # "inside the boundary, NULLs ignored" is simply "has a shed".
    table = destinations.get(formula.member)
    if table is None or table.empty:
        return np.nan
    low = pd.to_numeric(table["pop_low_stress"], errors="coerce")
    high = pd.to_numeric(table["pop_high_stress"], errors="coerce")
    if isinstance(formula, ShedRatio):
        return _ratio(low, high, float_division=True)
    return _percentile(low / high.replace(0, np.nan), formula.quantile)


def derive_score_inputs(
    census_blocks: gpd.GeoDataFrame,
    boundary: gpd.GeoDataFrame,
    destinations: dict[str, gpd.GeoDataFrame],
) -> pd.DataFrame:
    """Build the `score_inputs` table.

    Parameters
    ----------
    census_blocks
        The retained blocks with every score column derived.
    boundary
        The city boundary; only blocks intersecting it count.
    destinations
        The destination tables by category, with their population sheds.

    Returns
    -------
    pandas.DataFrame
        The table as `score_inputs.sql` left it: `id`, `category`,
        `score_name`, `score` (rounded to 4 decimals, NaN for NULL), `notes`,
        `human_explanation`, then the sixteen `use_*` flags (True or NULL).
    """
    from brokenspoke_analyzer.core.pipeline import scoring  # noqa: PLC0415

    scored = census_blocks[
        census_blocks.geometry.intersects(boundary.geometry.union_all())
    ]
    records: list[dict[str, typing.Any]] = []
    for position, row in enumerate(SCORE_INPUTS, start=1):
        value = evaluate(row.formula, scored, destinations)
        record: dict[str, typing.Any] = {
            "id": position,
            "category": row.category,
            "score_name": row.score_name,
            "score": np.nan
            if np.isnan(value)
            else scoring._round_half_up(value, SCORE_DECIMALS),
            "notes": row.notes,
            "human_explanation": row.human_explanation,
        }
        for flag in USE_FLAGS:
            record[flag] = True if row.flag == flag else pd.NA
        records.append(record)
    table = pd.DataFrame.from_records(records)
    for flag in USE_FLAGS:
        table[flag] = table[flag].astype("boolean")
    return table
