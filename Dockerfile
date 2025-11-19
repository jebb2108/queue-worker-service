FROM python:3.13

ARG DEBUG
ARG LOG_LEVEL

ARG REDIS_URL
ARG GATEWAY_REDIS_URL
ARG DATABASE_URL
ARG RABBITMQ_URL
ARG MATCH_RECEIVE_URL

ENV DEBUG=TRUE
ENV LOG_LEVEL=INFO
ENV REDIS_URL=redis://redis:6379/0
ENV GATEWAY_REDIS_URL=redis://redis:6379/1
ENV DATABASE_URL=postgresql+asyncpg://onlynone:random123@postgres:5432/mydb
ENV RABBITMQ_URL=amqp://guest:guest@rabbit:5672/
ENV MATCH_RECEIVE_URL=http://host.docker.internal:8101/api/match_found

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


RUN echo "DEBUG=$DEBUG"
RUN echo "LOG_LEVEL=$LOG_LEVEL"
RUN echo "REDIS_URL=$REDIS_URL"
RUN echo "GATEWAY_REDIS_URL=$GATEWAY_REDIS_URL"
RUN echo "DATABASE_URL=$DATABASE_URL"
RUN echo "RABBITMQ_URL=$RABBITMQ_URL"
RUN echo "MATCH_RECEIVE_URL=$MATCH_RECEIVE_URL"

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]