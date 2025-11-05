FROM python:3.12

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y \
    gnupg \
 && rm -rf /var/lib/apt/lists/*


RUN pip install --no-cache-dir gunicorn psycopg2 redis

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY spkrepo ./spkrepo
COPY migrations ./migrations
COPY wsgi.py ./

HEALTHCHECK --interval=1m --timeout=5s \
  CMD curl -f http://localhost:8000/ || exit 1
VOLUME [ "/data" ]
EXPOSE 8000
CMD [ "gunicorn", "-b", "0.0.0.0:8000", "-w", "5", "wsgi:app" ]
