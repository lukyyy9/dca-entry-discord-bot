# Dockerfile - CasaOS friendly, non-root
FROM python:3.11-slim

ARG BOT_UID=1000
ARG BOT_GID=1000

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# create group and user
RUN groupadd -g ${BOT_GID} botgroup \
 && useradd -m -u ${BOT_UID} -g botgroup -s /usr/sbin/nologin botuser

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy app
COPY . /app

# create data dir and set ownership
RUN mkdir -p /data && chown botuser:botgroup /data && chmod 700 /data

# switch to non-root
USER botuser

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "bot_daily_score.py"]
