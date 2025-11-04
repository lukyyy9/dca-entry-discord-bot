# DCA Discord Bot — Pack CasaOS (Option A)

Ce document contient tous les fichiers prêts à coller dans un dossier et déployer dans CasaOS. Le bot :

* tourne en **UTC** et s'exécute chaque **jour ouvré à 22:10 UTC**,
* utilise **yfinance** pour les prix EOD,
* contient un **scheduler interne** (APScheduler) — pas de cron externe,
* conçu pour **CasaOS** avec Docker Compose,
* sécurité : tourne non-root, filesystem read-only, `no-new-privileges`, `cap_drop: ALL`, `/data` comme unique volume RW,
* configuration **strictement via `config.yaml`** (monté en `:ro`).

---

## Fichiers inclus

1. `bot_daily_score.py`  (script principal)
2. `Dockerfile`
3. `docker-compose.yml`
4. `config.yaml` (exemple)
5. `requirements.txt`
6. `README_INSTALL.md` (instructions rapide)

---

## 1) bot_daily_score.py

````python
#!/usr/bin/env python3
# bot_daily_score.py
# Python 3.11+
# Scheduler interne: APScheduler (cron trigger)

import os
import sys
import stat
import time
import logging
import signal
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import yaml

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# ---------- CONFIG ----------
CONFIG_PATH = "/app/config.yaml"  # mounted read-only from host
DEFAULT_CONFIG = {
    "webhook_url": "https://discord.com/api/webhooks/REPLACE_ME",
    "tickers": ["SPY", "QQQ", "VTI", "IEFA"],
    "data_period": "365d",
    "weights": {
        "drawdown90": 0.25,
        "rsi14": 0.25,
        "dist_ma50": 0.20,
        "momentum30": 0.15,
        "trend_ma200": 0.10,
        "volatility20": 0.05
    },
    "drawdown_cap": 0.25,
    "volatility_cap": 0.10,
    "output_csv": "/data/scores_history.csv",
    "log_file": "/data/bot_daily_score.log",
    "timezone": "UTC",
    "admin": {"admin_tokens": []}
}

# ---------- LOGGING ----------

def setup_logging(log_file: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

# ---------- CONFIG HELPERS ----------

def load_config(path=CONFIG_PATH):
    if not os.path.exists(path):
        # create default sample (not ideal for production) and exit so user creates proper config
        with open(path, "w") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f)
        print(f"Un fichier config par d\u00e9faut a \u00e9t\u00e9 cr\u00e9\u00e9 : {path}. Edite-le et relance le container.")
        sys.exit(1)
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    # merge defaults for missing keys
    def merge(d, default):
        for k, v in default.items():
            if k not in d:
                d[k] = v
            elif isinstance(v, dict):
                merge(d[k], v)
    merge(cfg, DEFAULT_CONFIG)
    return cfg

# ---------- SECURITY CHECKS ----------

def check_running_user():
    try:
        euid = os.geteuid()
    except AttributeError:
        # Windows (not relevant here) - skip
        return
    if euid == 0:
        logging.error("Refus d'exécution : le processus ne doit PAS tourner en root.")
        sys.exit(2)


def check_config_permissions(path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        logging.error("Fichier de configuration introuvable: %s", path)
        sys.exit(2)
    mode = stat.S_IMODE(st.st_mode)
    if (mode & (stat.S_IRWXG | stat.S_IRWXO)) != 0:
        logging.error(
            "Permissions trop permissives pour %s (mode %o).\n" \
            "Sur l'hote: chown 1000:1000 %s && chmod 600 %s",
            path, mode, path, path
        )
        sys.exit(2)


def validate_config(cfg):
    webhook = cfg.get("webhook_url", "")
    if not webhook or "discord.com/api/webhooks" not in str(webhook):
        logging.error("webhook_url invalide ou absente dans config.yaml. Halte.")
        sys.exit(2)
    admin = cfg.get("admin", {})
    tokens = admin.get("admin_tokens", [])
    if not isinstance(tokens, list) or len(tokens) == 0:
        logging.warning("Aucun token d'administration trouvé dans config.yaml (admin.admin_tokens).")

# ---------- INDICATORS ----------

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi

# ---------- NORMALIZATIONS ----------

def score_drawdown(drawdown: float, cap: float) -> float:
    if drawdown <= 0:
        return 0.0
    return min(drawdown / cap, 1.0)


def score_rsi(rsi: float) -> float:
    val = (70.0 - rsi) / 40.0
    return float(np.clip(val, 0.0, 1.0))


def score_dist_ma50(close: float, ma50: float) -> float:
    if np.isnan(ma50) or ma50 == 0:
        return 0.0
    dist = 1.0 - (close / ma50)
    return float(np.clip(dist, 0.0, 1.0))


def score_momentum(momentum: float) -> float:
    k = 6.0
    s = 1.0 / (1.0 + np.exp(k * momentum))
    return float(np.clip(s, 0.0, 1.0))


def score_trend_ma200(close: float, ma200: float) -> float:
    if np.isnan(ma200) or ma200 == 0:
        return 0.5
    return 1.0 if close > ma200 else 0.3


def score_volatility(vol20: float, cap: float) -> float:
    if vol20 <= 0:
        return 1.0
    return float(np.clip(1.0 - (vol20 / cap), 0.0, 1.0))

# ---------- CORE SCORING ----------

def compute_scores_for_ticker(ticker: str, cfg: dict):
    period = cfg.get("data_period", "365d")
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False)
    except Exception as e:
        logging.exception("Erreur yfinance pour %s: %s", ticker, e)
        return None

    if df is None or df.empty:
        logging.warning("Pas de données pour %s", ticker)
        return None

    df = df.dropna().copy()
    df["MA50"] = df["Close"].rolling(50, min_periods=1).mean()
    df["MA200"] = df["Close"].rolling(200, min_periods=1).mean()
    df["RSI14"] = compute_rsi(df["Close"], 14)
    df["High90"] = df["Close"].rolling(90, min_periods=1).max()
    df["Drawdown90"] = (df["High90"] - df["Close"]) / df["High90"]
    df["Vol20"] = df["Close"].pct_change().rolling(20, min_periods=1).std()
    df["Momentum30"] = df["Close"].pct_change(periods=30)

    latest = df.iloc[-1]

    close = float(latest["Close"])
    ma50 = float(latest["MA50"]) if not np.isnan(latest["MA50"]) else np.nan
    ma200 = float(latest["MA200"]) if not np.isnan(latest["MA200"]) else np.nan
    rsi14 = float(latest["RSI14"]) if not np.isnan(latest["RSI14"]) else 50.0
    drawdown90 = float(latest["Drawdown90"]) if not np.isnan(latest["Drawdown90"]) else 0.0
    vol20 = float(latest["Vol20"]) if not np.isnan(latest["Vol20"]) else 0.0
    momentum30 = float(latest["Momentum30"]) if not np.isnan(latest["Momentum30"]) else 0.0

    draw_sc = score_drawdown(drawdown90, cfg["drawdown_cap"])
    rsi_sc = score_rsi(rsi14)
    ma50_sc = score_dist_ma50(close, ma50)
    mom_sc = score_momentum(momentum30)
    trend_sc = score_trend_ma200(close, ma200)
    vol_sc = score_volatility(vol20, cfg["volatility_cap"])

    w = cfg["weights"]

    composite = (
        w["drawdown90"] * draw_sc
        + w["rsi14"] * rsi_sc
        + w["dist_ma50"] * ma50_sc
        + w["momentum30"] * mom_sc
        + w["trend_ma200"] * trend_sc
        + w["volatility20"] * vol_sc
    )

    score_100 = round(100.0 * composite, 1)

    return {
        "ticker": ticker,
        "score": score_100,
        "close": close,
        "ma50": ma50,
        "ma200": ma200,
        "rsi14": round(rsi14, 2),
        "drawdown90_pct": round(drawdown90 * 100.0, 2),
        "vol20_pct": round(vol20 * 100.0, 2),
        "momentum30_pct": round(momentum30 * 100.0, 2),
        "components": {
            "drawdown": round(draw_sc, 3),
            "rsi": round(rsi_sc, 3),
            "ma50": round(ma50_sc, 3),
            "momentum": round(mom_sc, 3),
            "trend": round(trend_sc, 3),
            "volatility": round(vol_sc, 3)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# ---------- DISCORD MESSAGE ----------

def build_discord_message(results: list):
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = f"📊 **Score DCA quotidien — {date} (après clôture)**\n"
    header += "```\n"
    header += f"{'Ticker':<8}{'Score':<8}{'RSI':<8}{'Prix':<10}{'MA50':<10}{'MA200':<10}\n"
    header += "-" * 64 + "\n"
    lines = []
    for r in results:
        lines.append(
            f"{r['ticker']:<8}{r['score']:<8}{r['rsi14']:<8}{r['close']:<10.2f}{(r['ma50'] or 0):<10.2f}{(r['ma200'] or 0):<10.2f}"
        )
    body = "\n".join(lines)
    footer = "\n```\n💡 Plus le score est élevé, plus le point d’entrée DCA est intéressant (0–100).\n"
    footer += "_Ceci n'est pas un conseil financier. Faites vos propres vérifications._"
    return header + body + footer


def send_webhook(webhook_url: str, content: str):
    payload = {"content": content}
    try:
        r = requests.post(webhook_url, json=payload, timeout=15)
        if r.status_code >= 400:
            logging.error("Webhook erreur %s: %s", r.status_code, r.text)
        else:
            logging.info("Message envoyé sur Discord (webhook).")
    except Exception as e:
        logging.exception("Erreur en envoyant webhook: %s", e)

# ---------- HISTORY SAVE ----------

def append_history(csv_path: str, rows: list):
    try:
        df = pd.DataFrame(rows)
        header = not os.path.exists(csv_path)
        df.to_csv(csv_path, mode="a", header=header, index=False)
    except Exception:
        logging.exception("Erreur en sauvegardant l'historique")

# ---------- DAILY JOB ----------

def daily_job(cfg):
    logging.info("D\u00e9marrage du job quotidien")
    tickers = cfg.get("tickers", [])
    results = []
    history = []
    for t in tickers:
        try:
            r = compute_scores_for_ticker(t, cfg)
            if r:
                results.append(r)
                history.append({
                    "timestamp": r["timestamp"],
                    "ticker": r["ticker"],
                    "score": r["score"],
                    "close": r["close"],
                    "rsi14": r["rsi14"],
                    "ma50": r["ma50"],
                    "ma200": r["ma200"],
                    "drawdown90_pct": r["drawdown90_pct"],
                    "vol20_pct": r["vol20_pct"],
                    "momentum30_pct": r["momentum30_pct"]
                })
            time.sleep(1.0)
        except Exception:
            logging.exception("Erreur lors du calcul pour %s", t)

    results.sort(key=lambda x: x["score"], reverse=True)
    if results:
        msg = build_discord_message(results)
        send_webhook(cfg["webhook_url"], msg)
        append_history(cfg["output_csv"], history)
    else:
        logging.warning("Aucun r\u00e9sultat calcul\u00e9 aujourd'hui")

# ---------- SCHEDULER SETUP ----------

scheduler = None

def start_scheduler(cfg):
    global scheduler
    scheduler = BlockingScheduler(timezone=cfg.get("timezone", "UTC"))

    # CronTrigger: 22:10 UTC every Monday-Friday
    trigger = CronTrigger(hour=22, minute=10, day_of_week='mon-fri', timezone=cfg.get("timezone", "UTC"))
    scheduler.add_job(lambda: daily_job(cfg), trigger, name="daily_score_job")

    logging.info("Scheduler programmé: tous les jours ouvrés 22:10 %s", cfg.get("timezone", "UTC"))

    # start blocking scheduler (this will block until stopped)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler arrêté par signal")

# Graceful shutdown

def shutdown(signum, frame):
    logging.info("Signal %s reçu. Arrêt...", signum)
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
    sys.exit(0)

# ---------- MAIN ----------

def main():
    # create data directory if missing
    os.makedirs("/data", exist_ok=True)

    cfg = load_config(CONFIG_PATH)
    setup_logging(cfg.get("log_file", "/data/bot_daily_score.log"))

    check_running_user()
    check_config_permissions(CONFIG_PATH)
    validate_config(cfg)

    # register signals
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logging.info("Bot DCA démarré. Mode scheduler interne.")
    start_scheduler(cfg)

if __name__ == "__main__":
    main()
````

---

## 2) Dockerfile

```dockerfile
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
```

---

## 3) docker-compose.yml

```yaml
version: '3.8'
services:
  dca-bot:
    build: .
    container_name: casa_dca_bot
    restart: unless-stopped
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/data
    environment:
      - TZ=UTC
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    read_only: true
    tmpfs:
      - /tmp:rw,size=64m
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    build:
      context: .
      args:
        BOT_UID: 1000
        BOT_GID: 1000
    user: "1000:1000"
```

---

## 4) config.yaml (exemple)

```yaml
webhook_url: "https://discord.com/api/webhooks/TON_WEBHOOK"
# liste d'ETF / tickers à surveiller
tickers:
  - "SPY"
  - "QQQ"
  - "VTI"
  - "IEFA"

# période historique à récupérer
data_period: "365d"

# normalisation / caps
drawdown_cap: 0.25
volatility_cap: 0.10

# fichiers de sortie (doit pointer sur /data)
output_csv: "/data/scores_history.csv"
log_file: "/data/bot_daily_score.log"

# poids des composants
weights:
  drawdown90: 0.25
  rsi14: 0.25
  dist_ma50: 0.20
  momentum30: 0.15
  trend_ma200: 0.10
  volatility20: 0.05

# section admin : liste de tokens
admin:
  admin_tokens:
    - "remplace_par_un_token_admin_très_long_et_secret"

# timezone used by scheduler
timezone: "UTC"
```

---

## 5) requirements.txt

```
yfinance
pandas
numpy
requests
pyyaml
apscheduler
```

---

## 6) README_INSTALL.md (instructions rapides)

```
1) Place tous les fichiers dans un dossier sur ton NAS/serveur (ex: /home/user/casa-dca-bot)
2) Edite config.yaml et renseigne webhook_url et admin.admin_tokens.
3) Sur l'hote, règle permissions :
   chown 1000:1000 config.yaml
   chmod 600 config.yaml
   mkdir -p data
   chown 1000:1000 data
   chmod 700 data
4) Build & run via CasaOS custom app (ou terminal) :
   docker compose up -d --build
5) Logs : docker logs -f casa_dca_bot
6) Tests : attends 22:10 UTC un jour ouvré ou modifie temporairement la cron dans le code pour exécuter immédiatement.

Notes de sécurité:
- Ne commit pas config.yaml dans un repo public.
- Rotate webhook si compromis.
```

---

## Remarques finales

* L'image est intentionnellement simple (yfinance, pas de clef). Pour production à échelle ou haute fréquence, remplace yfinance par une API payante (Polygon/IEX) et ajoute gestion des quotas.
* Si tu veux, j'ajoute une petite route HTTP d'administration (auth par token via `admin.admin_tokens`) pour déclencher manuellement un run — mais cela implique exposer un port et sécuriser davantage.

---

Si tu veux, j'assemble aussi un `tar.gz` prêt à télécharger ou je te fournis les fichiers séparés. Dis si tu veux des ajustements (changement d'UID, log rotate via logrotate, ou ajout d'embeds Discord au lieu du simple texte).
