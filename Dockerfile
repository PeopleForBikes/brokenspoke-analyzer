FROM python:3.11.5-slim-bookworm AS builder
LABEL author="PeopleForBikes"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  gcc \
  g++ \
  gdal-bin \
  libgdal-dev \
  python3-dev \
  python3-poetry \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /usr/src/app
COPY . .
RUN poetry self update \
  && poetry export -f requirements.txt --only main --output requirements.txt \
  && mkdir -p deps \
  && pip wheel -r requirements.txt -w deps \
  && poetry build -f wheel

FROM python:3.11.5-slim-bookworm
LABEL author="PeopleForBikes"

RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  osm2pgrouting \
  osm2pgsql \
  osmctools \
  osmium-tool \
  postgresql-client-15 \
  postgis \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ENV BNA_OSMNX_CACHE 0
WORKDIR /usr/src/app
COPY --from=builder /usr/src/app/deps ./pkg/deps
COPY --from=builder /usr/src/app/dist ./pkg/dist
RUN pip install pkg/deps/Fiona-1.9.4.post1-*.whl \
  && pip install pkg/deps/* \
  && pip install pkg/dist/brokenspoke_analyzer-*-py3-none-any.whl \
  && rm -fr /usr/src/app/pkg \
  && addgroup --system --gid 1001 bna \
  && adduser --system --uid 1001 bna \
  && chown -R bna:bna /usr/src/app
USER bna
ENTRYPOINT [ "bna" ]
