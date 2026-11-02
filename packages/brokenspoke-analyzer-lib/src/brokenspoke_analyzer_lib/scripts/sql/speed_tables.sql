CREATE TABLE IF NOT EXISTS state_speed (
    state char(2),
    fips_code_state char(2),
    speed smallint
);

CREATE TABLE IF NOT EXISTS city_speed (
    city varchar,
    state char(2),
    fips_code_city char(7),
    speed smallint
);

CREATE TABLE IF NOT EXISTS residential_speed_limit (
    state_fips_code char(2),
    city_fips_code char(7),
    state_speed smallint,
    city_speed smallint
);
