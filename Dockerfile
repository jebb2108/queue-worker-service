FROM python:3.13.3
LABEL authors="Gabriel Bouchard"

WORKDIR /app

# Установка poetry
RUN pip install poetry

ENV PYTHONPATH=/app

COPY poetry.lock pyproject.toml ./

RUN poetry install --no-root --no-ansi --without dev

# Copy only necessary source files
COPY src/ ./src/
COPY prometheus.yml .
COPY promtail-config.yaml .
COPY loki-config.yaml .
COPY grafana/datasources.yaml ./grafana/datasources.yaml

CMD ["poetry", "run", "python", "src/main.py"]