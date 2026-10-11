FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATABASE_PATH=/app/data/gct_report_parser.db

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    useradd --system --uid 10001 --create-home --home-dir /home/reportparser reportparser
COPY --chown=10001:10001 app.py parser.py history.py report_builder.py gunicorn.conf.py ./
COPY --chown=10001:10001 templates/ ./templates/
COPY --chown=10001:10001 static/ ./static/
COPY tests/ ./tests/
# Run regression tests with the same installed dependencies used by production.
# Test artifacts are removed in this layer and are not shipped in the final image.
RUN DATABASE_PATH=/tmp/gct-report-parser-tests.db python -m unittest discover -s tests -v && \
    rm -rf tests /tmp/gct-report-parser-tests.db /tmp/gct-report-parser-tests.db-shm /tmp/gct-report-parser-tests.db-wal && \
    mkdir -p /app/data && chown 10001:10001 /app/data
USER 10001:10001
EXPOSE 8080
STOPSIGNAL SIGTERM
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
