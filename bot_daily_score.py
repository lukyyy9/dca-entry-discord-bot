#!/usr/bin/env python3
# bot_daily_score.py
# Python 3.11+
# Scheduler interne: APScheduler (cron trigger)

import os
import sys
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
CONFIG_PATH = "/app/config.yaml"

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
        logging.error("❌ ERREUR: Le fichier de configuration '%s' est introuvable.", path)
        logging.error("Veuillez créer un fichier config.yaml et le monter dans le container.")
        sys.exit(1)
    
    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logging.error("❌ ERREUR: Impossible de lire le fichier de configuration '%s': %s", path, e)
        sys.exit(1)
    
    if not cfg:
        logging.error("❌ ERREUR: Le fichier de configuration '%s' est vide.", path)
        sys.exit(1)
    
    # Set default values for optional fields if missing
    cfg.setdefault("data_period", "365d")
    cfg.setdefault("drawdown_cap", 0.25)
    cfg.setdefault("volatility_cap", 0.10)
    cfg.setdefault("output_csv", "/data/scores_history.csv")
    cfg.setdefault("log_file", "/data/bot_daily_score.log")
    cfg.setdefault("timezone", "UTC")
    cfg.setdefault("admin", {})
    cfg["admin"].setdefault("admin_tokens", [])
    
    # Set default weights if missing
    if "weights" not in cfg:
        cfg["weights"] = {}
    cfg["weights"].setdefault("drawdown90", 0.25)
    cfg["weights"].setdefault("rsi14", 0.25)
    cfg["weights"].setdefault("dist_ma50", 0.20)
    cfg["weights"].setdefault("momentum30", 0.15)
    cfg["weights"].setdefault("trend_ma200", 0.10)
    cfg["weights"].setdefault("volatility20", 0.05)
    
    return cfg

# ---------- CONFIG VALIDATION ----------

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

    # FIX: Flatten multi-index columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
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
    footer = "\n```\n💡 Plus le score est élevé, plus le point d'entrée DCA est intéressant (0–100).\n"
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
    logging.info("Démarrage du job quotidien")
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
        logging.warning("Aucun résultat calculé aujourd'hui")

# ---------- SCHEDULER SETUP ----------

scheduler = None

def start_scheduler(cfg):
    global scheduler
    scheduler = BlockingScheduler(timezone=cfg.get("timezone", "UTC"))

    # Check DEV environment variable
    dev_mode = os.getenv("DEV", "false").lower() in ("true", "1", "yes")
    
    if dev_mode:
        # DEV mode: trigger every minute
        trigger = CronTrigger(minute='*', timezone=cfg.get("timezone", "UTC"))
        logging.info("🔧 MODE DEV ACTIVÉ: Scheduler programmé toutes les minutes")
    else:
        # Production mode: 22:10 UTC every Monday-Friday
        trigger = CronTrigger(hour=22, minute=10, day_of_week='mon-fri', timezone=cfg.get("timezone", "UTC"))
        logging.info("Scheduler programmé: tous les jours ouvrés 22:10 %s", cfg.get("timezone", "UTC"))
    
    scheduler.add_job(lambda: daily_job(cfg), trigger, name="daily_score_job")

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

    validate_config(cfg)

    # register signals
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logging.info("Bot DCA démarré. Mode scheduler interne.")
    start_scheduler(cfg)

if __name__ == "__main__":
    main()
