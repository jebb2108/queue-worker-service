FROM python:3.13

ARG DEBUG
ARG LOG_LEVEL

ARG REDIS_URL
ARG GATEWAY_REDIS_URL
ARG DATABASE_URL
ARG RABBITMQ_URL
ARG MATCH_RECEIVE_URL

ENV DEBUG=$DEBUG
ENV LOG_LEVEL=$LOG_LEVEL

ENV REDIS_URL=$REDIS_URL
ENV GATEWAY_REDIS_URL=$GATEWAY_REDIS_URL
ENV DATABASE_URL=$DATABASE_URL
ENV RABBITMQ_URL=$RABBITMQ_URL
ENV MATCH_RECEIVE_URL=$MATCH_RECEIVE_URL

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1

# запустить poetry directly сразу после установки
ENV PATH="$POETRY_HOME/bin:$PATH"

# Установка poetry
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && curl -sSL https://install.python-poetry.org | python3 -


WORKDIR /app

ENV PYTHONPATH=/app

COPY poetry.lock pyproject.toml ./

# Это создаст директорию /app/.venv
RUN poetry install --no-root --no-ansi --without dev

RUN poetry env use python

RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

# Copy only necessary source files
COPY src/ ./src/
COPY prometheus.yml .
COPY promtail-config.yaml .
COPY loki-config.yaml .
COPY grafana/datasources.yaml ./grafana/datasources.yaml
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]