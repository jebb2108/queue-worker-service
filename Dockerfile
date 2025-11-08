FROM python:3.13-slim

WORKDIR /app

ENV PYTHONPATH=/app

COPY pyproject.toml .
COPY poetry.lock .

RUN apt-get update && apt-get install -y supervisor && rm -rf /var/lib/apt/lists/*

RUN poetry install
RUN poetry env start

ENV DEBUG=FALSE
ENV LOG_LEVEL=INFO

# Copy only necessary source files
COPY src/ ./src/
COPY prometheus.yml .
COPY promtail-config.yaml .
COPY loki-config.yaml .
COPY grafana/datasources.yaml ./grafana/datasources.yaml
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]