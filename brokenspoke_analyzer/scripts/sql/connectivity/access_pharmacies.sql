----------------------------------------
-- Input variables:
--      :max_score - Maximum score value
--      :first - Value of first available destination (if 0 then ignore--a basic ratio is used for the score)
--      :second - Value of second available destination (if 0 then ignore--a basic ratio is used after 1)
--      :third - Value of third available destination (if 0 then ignore--a basic ratio is used after 2)
----------------------------------------
-- set block-based raw numbers
UPDATE neighborhood_census_blocks
SET
    pharmacies_low_stress = (
        SELECT COUNT(id)
        FROM neighborhood_pharmacies
        WHERE EXISTS (
            SELECT 1
            FROM neighborhood_connected_census_blocks
            WHERE
                neighborhood_connected_census_blocks.source_blockid10
                = neighborhood_census_blocks.blockid10
                AND neighborhood_connected_census_blocks.target_blockid10
                = ANY(neighborhood_pharmacies.blockid10)
                AND neighborhood_connected_census_blocks.low_stress
        )
    ),
    pharmacies_high_stress = (
        SELECT COUNT(id)
        FROM neighborhood_pharmacies
        WHERE EXISTS (
            SELECT 1
            FROM neighborhood_connected_census_blocks
            WHERE
                neighborhood_connected_census_blocks.source_blockid10
                = neighborhood_census_blocks.blockid10
                AND neighborhood_connected_census_blocks.target_blockid10
                = ANY(neighborhood_pharmacies.blockid10)
        )
    )
WHERE EXISTS (
    SELECT 1
    FROM neighborhood_boundary AS b
    WHERE ST_Intersects(neighborhood_census_blocks.geom, b.geom)
);

-- set block-based score
UPDATE neighborhood_census_blocks
SET pharmacies_score = CASE
    WHEN pharmacies_high_stress IS NULL THEN NULL
    WHEN pharmacies_high_stress = 0 THEN NULL
    WHEN pharmacies_low_stress = 0 THEN 0
    WHEN pharmacies_high_stress = pharmacies_low_stress THEN :max_score
    WHEN :first = 0 THEN pharmacies_low_stress::FLOAT / pharmacies_high_stress
    WHEN :second = 0
        THEN
            :first
            + ((:max_score - :first) * (pharmacies_low_stress::FLOAT - 1))
            / (pharmacies_high_stress - 1)
    WHEN :third = 0
        THEN CASE
            WHEN pharmacies_low_stress = 1 THEN :first
            WHEN pharmacies_low_stress = 2 THEN :first + :second
            ELSE
                :first + :second
                + (
                    (:max_score - :first - :second)
                    * (pharmacies_low_stress::FLOAT - 2)
                )
                / (pharmacies_high_stress - 2)
        END
    ELSE CASE
        WHEN pharmacies_low_stress = 1 THEN :first
        WHEN pharmacies_low_stress = 2 THEN :first + :second
        WHEN pharmacies_low_stress = 3 THEN :first + :second + :third
        ELSE
            :first + :second + :third
            + (
                (:max_score - :first - :second - :third)
                * (pharmacies_low_stress::FLOAT - 3)
            )
            / (pharmacies_high_stress - 3)
    END
END;

-- set population shed for each pharmacies destination in the neighborhood
UPDATE neighborhood_pharmacies
SET
    pop_high_stress = (
        SELECT SUM(shed.pop)
        FROM (
            SELECT
                cb.blockid10,
                MAX(cb.pop10) AS pop
            FROM neighborhood_census_blocks AS cb,
                neighborhood_connected_census_blocks AS cbs
            WHERE
                cbs.source_blockid10 = cb.blockid10
                AND cbs.target_blockid10
                = ANY(neighborhood_pharmacies.blockid10)
            GROUP BY cb.blockid10
        ) AS shed
    ),
    pop_low_stress = (
        SELECT SUM(shed.pop)
        FROM (
            SELECT
                cb.blockid10,
                MAX(cb.pop10) AS pop
            FROM neighborhood_census_blocks AS cb,
                neighborhood_connected_census_blocks AS cbs
            WHERE
                cbs.source_blockid10 = cb.blockid10
                AND cbs.target_blockid10
                = ANY(neighborhood_pharmacies.blockid10)
                AND cbs.low_stress
            GROUP BY cb.blockid10
        ) AS shed
    )
WHERE EXISTS (
    SELECT 1
    FROM neighborhood_boundary AS b
    WHERE ST_Intersects(neighborhood_pharmacies.geom_pt, b.geom)
);

UPDATE neighborhood_pharmacies
SET pop_score = CASE
    WHEN pop_high_stress IS NULL THEN NULL
    WHEN pop_high_stress = 0 THEN 0
    ELSE pop_low_stress::FLOAT / pop_high_stress
END;
