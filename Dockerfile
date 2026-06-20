FROM ghcr.io/astral-sh/uv:0.11.23 AS uv

FROM python:3.14-slim

WORKDIR /usr/src/app

ENV UV_SYSTEM_PYTHON=1

COPY --from=uv /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./

ARG CACHE_BUSTER=1
RUN echo "Building fresh version: ${CACHE_BUSTER}"

RUN apt-get update && apt-get install -y --no-install-recommends \
  gnupg curl gcc libpq-dev \
  && uv sync --locked --no-dev --no-cache --no-install-project \
  && apt-get purge -y --auto-remove gcc \
  && rm -rf /var/lib/apt/lists/*

COPY spkrepo ./spkrepo
COPY migrations ./migrations
COPY wsgi.py ./
COPY celery_app.py ./

RUN uv sync --locked --no-dev --no-cache --no-editable

HEALTHCHECK --interval=1m --timeout=5s \
  CMD curl -f http://localhost:8000/ || exit 1

VOLUME [ "/data" ]
EXPOSE 8000
CMD [ "gunicorn", "-b", "0.0.0.0:8000", "-w", "5", "wsgi:app" ]
