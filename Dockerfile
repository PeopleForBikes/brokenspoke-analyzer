FROM postgis/postgis:13-3.1
LABEL author="PeopleForBikes"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  postgresql-13-pgrouting \
  postgresql-plpython3-13 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
