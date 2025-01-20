FROM python:3.13.1-slim-bookworm AS base

FROM base AS builder
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  curl \
  gcc \
  g++ \
  gdal-bin \
  libgdal-dev \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
WORKDIR /usr/src/app
COPY . .
RUN pip install uv \
  && uv export --format requirements-txt --all-extras --no-group dev --no-hashes -o requirements.txt \
  && mkdir -p deps \
  && pip wheel -r requirements.txt -w deps \
  && uv build --wheel \
  && curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to .

FROM base AS main
LABEL author="PeopleForBikes" \
  maintainer="BNA Mechanics - https://peopleforbikes.github.io" \
  org.opencontainers.image.description="Run a BNA analysis locally." \
  org.opencontainers.image.source="https://github.com/PeopleForBikes/brokenspoke-analyzer"
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  gdal-bin \
  osm2pgrouting \
  osm2pgsql \
  osmctools \
  osmium-tool \
  postgresql-client-15 \
  postgis \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
ENV BNA_OSMNX_CACHE=0
WORKDIR /usr/src/app
COPY --from=builder /usr/src/app/deps ./pkg/deps
COPY --from=builder /usr/src/app/dist ./pkg/dist
RUN  pip install pkg/deps/* \
  && pip install pkg/dist/brokenspoke_analyzer-*-py3-none-any.whl \
  && rm -fr /usr/src/app/pkg \
  && addgroup --system --gid 1001 bna \
  && adduser --system --uid 1001 bna \
  && chown -R bna:bna /usr/src/app
ENTRYPOINT [ "bna" ]

FROM main AS devcontainer
COPY --from=builder /usr/src/app/just /usr/local/bin/
RUN pip install uv \
  && usermod --home /home/bna --move-home --shell /bin/bash bna
USER bna

FROM main
USER bna
