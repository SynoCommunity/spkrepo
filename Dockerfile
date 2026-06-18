FROM python:3.12-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg curl gcc libpq-dev \
 && pip install --no-cache-dir uv \
 && uv pip install --system --no-cache gunicorn psycopg2 redis -r requirements.txt \
 && apt-get purge -y --auto-remove gcc \
 && rm -rf /var/lib/apt/lists/*

COPY spkrepo ./spkrepo
COPY migrations ./migrations
COPY wsgi.py ./
COPY celery_app.py ./

HEALTHCHECK --interval=1m --timeout=5s \
  CMD curl -f http://localhost:8000/ || exit 1

VOLUME [ "/data" ]
EXPOSE 8000
CMD [ "gunicorn", "-b", "0.0.0.0:8000", "-w", "5", "wsgi:app" ]
