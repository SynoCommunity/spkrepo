FROM python:3.8-alpine3.11

WORKDIR /usr/src/app

RUN apk update \
    && apk add --virtual build-deps gcc python3-dev musl-dev \
    && apk add postgresql-dev \
    && apk add zlib-dev \
    && apk add jpeg-dev \
    && apk add gnupg

RUN pip install --no-cache-dir gunicorn psycopg2 redis

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

VOLUME [ "/data" ]
EXPOSE 8000
CMD [ "gunicorn", "-b", "0.0.0.0:8000", "-w", "5", "wsgi:app" ]
