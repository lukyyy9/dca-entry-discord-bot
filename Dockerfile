# Dockerfile V2 - Bot DCA avec interface web
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier les requirements et installer les dépendances
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copier l'application
COPY core/ /app/core/
COPY templates/ /app/templates/
COPY static/ /app/static/
COPY bot_daily_score_v2.py /app/
COPY backtest_v2.py /app/
COPY web_app.py /app/

# Créer le répertoire data
RUN mkdir -p /data

ENV PYTHONUNBUFFERED=1

# Par défaut, lancer le bot (peut être overridé par docker-compose)
CMD ["python", "bot_daily_score_v2.py"]
