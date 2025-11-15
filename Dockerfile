FROM python:3.13.9-slim-trixie AS base

FROM base AS osm2pgrouting3
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  build-essential \
  cmake \
  expat \
  git \
  libboost-dev \
  libboost-program-options-dev \
  libexpat1-dev \
  libpqxx-dev
WORKDIR /usr/src/
RUN git clone https://github.com/pgRouting/osm2pgrouting.git \
  && cd osm2pgrouting \
  && cmake -H. -Bbuild \
  && cd build/ \
  && make

FROM base AS builder
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  curl \
  g++ \
  gcc \
  gdal-bin \
  libgdal-dev \
  proj-bin \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
WORKDIR /usr/src/app
COPY . .
RUN pip install uv \
  && uv export --format requirements-txt --all-extras --no-group dev --no-hashes -o requirements.txt \
  && mkdir -p deps \
  && pip wheel -r requirements.txt -w deps \
  && uv build --wheel

FROM base AS main
LABEL author="PeopleForBikes" \
  maintainer="BNA Mechanics - https://peopleforbikes.github.io" \
  org.opencontainers.image.description="Run a BNA analysis locally." \
  org.opencontainers.image.source="https://github.com/PeopleForBikes/brokenspoke-analyzer"
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  gdal-bin \
  libpqxx-7.10 \
  osm2pgsql \
  osmctools \
  osmium-tool \
  postgis \
  postgresql-client-17 \
  proj-bin \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
ENV BNA_OSMNX_CACHE=0
ENV BNA_PYGRIS_CACHE=0
WORKDIR /usr/src/app
COPY --from=builder /usr/src/app/deps ./pkg/deps
COPY --from=builder /usr/src/app/dist ./pkg/dist
COPY --from=osm2pgrouting3 /usr/src/osm2pgrouting/build/osm2pgrouting /usr/bin/osm2pgrouting
RUN  pip install pkg/deps/* \
  && pip install pkg/dist/brokenspoke_analyzer-*-py3-none-any.whl \
  && rm -fr /usr/src/app/pkg \
  && addgroup --system --gid 1001 bna \
  && adduser --system --uid 1001 bna \
  && chown -R bna:bna /usr/src/app
ENTRYPOINT [ "bna" ]

FROM main AS dev
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  curl \
  gcc \
  git \
  graphviz \
  just \
  locales \
  npm \
  openssh-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
RUN deluser --remove-home bna \
  && delgroup --only-if-empty bna \
  && chown -R root:root /usr/src/app \
  && pip install uv \
  && useradd --create-home --shell /bin/bash bna
RUN curl -o /etc/bash_completion.d/git-completion.bash \
  https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash
USER bna

FROM main
USER bna
