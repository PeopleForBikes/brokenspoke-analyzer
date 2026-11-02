ALTER TABLE neighborhood_census_blocks
ADD COLUMN IF NOT EXISTS opportunity_score FLOAT;
ALTER TABLE neighborhood_census_blocks
ADD COLUMN IF NOT EXISTS core_services_score FLOAT;
ALTER TABLE neighborhood_census_blocks
ADD COLUMN IF NOT EXISTS recreation_score FLOAT;

UPDATE neighborhood_census_blocks
SET
    opportunity_score
    = (
        COALESCE(emp_score, 0) * 0.35
        + COALESCE(schools_score, 0) * 0.35
        + COALESCE(colleges_score, 0) * 0.1
        + COALESCE(universities_score, 0) * 0.2
    )
    /
    NULLIF(
        (CASE WHEN emp_score IS NOT NULL THEN 0.35 ELSE 0 END)
        + (CASE WHEN schools_score IS NOT NULL THEN 0.35 ELSE 0 END)
        + (CASE WHEN colleges_score IS NOT NULL THEN 0.1 ELSE 0 END)
        + (CASE WHEN universities_score IS NOT NULL THEN 0.2 ELSE 0 END),
        0
    ),

    core_services_score
    = (
        COALESCE(doctors_score, 0) * 0.2
        + COALESCE(dentists_score, 0) * 0.1
        + COALESCE(hospitals_score, 0) * 0.2
        + COALESCE(pharmacies_score, 0) * 0.1
        + COALESCE(supermarkets_score, 0) * 0.25
        + COALESCE(social_services_score, 0) * 0.15
    )
    /
    NULLIF(
        (CASE WHEN doctors_score IS NOT NULL THEN 0.2 ELSE 0 END)
        + (CASE WHEN dentists_score IS NOT NULL THEN 0.1 ELSE 0 END)
        + (CASE WHEN hospitals_score IS NOT NULL THEN 0.2 ELSE 0 END)
        + (CASE WHEN pharmacies_score IS NOT NULL THEN 0.1 ELSE 0 END)
        + (CASE WHEN supermarkets_score IS NOT NULL THEN 0.25 ELSE 0 END)
        + (CASE WHEN social_services_score IS NOT NULL THEN 0.15 ELSE 0 END),
        0
    ),

    recreation_score
    = (
        COALESCE(parks_score, 0) * 0.4
        + COALESCE(trails_score, 0) * 0.35
        + COALESCE(community_centers_score, 0) * 0.25
    )
    /
    NULLIF(
        (CASE WHEN parks_score IS NOT NULL THEN 0.4 ELSE 0 END)
        + (CASE WHEN trails_score IS NOT NULL THEN 0.35 ELSE 0 END)
        + (CASE WHEN community_centers_score IS NOT NULL THEN 0.25 ELSE 0 END),
        0
    );
