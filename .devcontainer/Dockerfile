FROM python:3.12

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USER=pfb

RUN apt-get update && \
    apt-get install -y osmium-tool && \
    apt-get install -y osm2pgrouting

RUN useradd --create-home --shell /bin/bash $USER && \
    mkdir /home/$USER/.brokenspoke-analyzer && \
    chown -R $USER /home/$USER

USER $USER
ENV PATH "$PATH:/home/$USER/.local/bin"
WORKDIR /home/$USER/app

RUN python -m pip install --upgrade pip && \
pip install poetry

COPY brokenspoke_analyzer brokenspoke_analyzer
COPY pyproject.toml pyproject.toml
RUN poetry install

CMD ["sleep", "infinity"]
