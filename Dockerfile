FROM python:3.14-slim

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg curl gcc libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY spkrepo ./spkrepo
COPY migrations ./migrations
COPY wsgi.py ./
COPY celery_app.py ./

RUN pip install --no-cache-dir uv \
 && uv sync --locked --no-dev --no-cache \
 && apt-get purge -y --auto-remove gcc

HEALTHCHECK --interval=1m --timeout=5s \
  CMD curl -f http://localhost:8000/ || exit 1

VOLUME [ "/data" ]
EXPOSE 8000
CMD [ "gunicorn", "-b", "0.0.0.0:8000", "-w", "5", "wsgi:app" ]
