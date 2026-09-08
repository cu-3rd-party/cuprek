FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies from the pinned lock. Two reasons this comes first and on its own:
# builds are reproducible (a fresh VPS gets the versions we tested), and editing
# src/ no longer invalidates the layer -- which is what makes redeploys quick on a
# small box. Regenerate with the uv command documented in the README.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application code: this is the only layer a normal deploy rebuilds.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-deps .

# Runtime files.
COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Stamped at build time, reported by /status so you can tell which build is live.
ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

# Drop privileges. The heartbeat file lives in /tmp, so nothing else needs to be writable.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "-m", "circlebot"]
