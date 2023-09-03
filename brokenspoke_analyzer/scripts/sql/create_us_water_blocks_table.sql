CREATE TABLE IF NOT EXISTS water_blocks (
    statefp10 integer,
    countyfp10 integer,
    tractce10 integer,
    blockce10 integer,
    geoid varchar(15),
    name10 char(10),
    mtfcc10 char(5),
    ur10 char(1),
    uace10 integer,
    uatyp10 char(1),
    funcstat10 char(1),
    aland10 integer,
    awater10 bigint,
    intptlat10 decimal,
    intptlon10 decimal
);
