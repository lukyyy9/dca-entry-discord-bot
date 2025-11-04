#!/usr/bin/env python3
# bot_daily_score_v2.py
# Bot DCA V2 - Utilise les modules core/ et la configuration DB

import os
import sys
import time
import logging
import signal
from datetime import datetime, timezone

import requests
import pandas as pd

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import ConfigManager
from core.scoring import ScoringEngine

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

# ---------- DISCORD MESSAGE ----------

def get_score_emoji(score: float) -> str:
    """Retourne l'emoji correspondant au score."""
    if score < 45:
        return "❌"
    elif score < 55:
        return "⚠️"
    else:
        return "✅"


def build_discord_message(results: list):
    """Construit le message Discord formaté."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = f"# 📊 Score DCA quotidien — {date}\n\n"
    
    lines = []
    for r in results:
        ticker = r['ticker']
        product_name = r.get('product_name', ticker)
        score = r['score']
        rsi = r['rsi14']
        close = r['close']
        ma50 = r['ma50'] or 0
        ma200 = r['ma200'] or 0
        emoji = get_score_emoji(score)
        
        lines.append(f"## {ticker} — {product_name}")
        lines.append(f"**Score:** `{score}` {emoji}")
        lines.append(f"**Prix:** `{close:.2f}`")
        lines.append(f"**RSI (Relative Strength Index):** `{rsi}`")
        lines.append(f"**MA50 (50 days Mobile Average):**  `{ma50:.2f}`")
        lines.append(f"**MA200 (200 days Mobile Average):** `{ma200:.2f}`")
        lines.append(f"")

    body = "\n".join(lines)
    footer = "\n_Ceci n'est pas un conseil financier._\n"
    return header + body + footer


def send_webhook(webhook_url: str, content: str):
    """Envoie un message via webhook Discord."""
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
    """Sauvegarde l'historique dans un fichier CSV."""
    try:
        df = pd.DataFrame(rows)
        header = not os.path.exists(csv_path)
        df.to_csv(csv_path, mode="a", header=header, index=False)
    except Exception:
        logging.exception("Erreur en sauvegardant l'historique")

# ---------- DAILY JOB ----------

def daily_job(config_manager: ConfigManager):
    """Job quotidien de calcul et envoi des scores."""
    logging.info("Démarrage du job quotidien")
    
    # Charger la configuration depuis la DB
    config = config_manager.get_config()
    
    # Initialiser le moteur de scoring
    scoring_engine = ScoringEngine(config)
    
    tickers = config.get("tickers", [])
    if not tickers:
        logging.warning("Aucun ticker configuré")
        return
    
    results = []
    history = []
    
    for t in tickers:
        try:
            r = scoring_engine.compute_scores_for_ticker(
                t, 
                period=config.get("data_period", "365d")
            )
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

    # Trier par score décroissant
    results.sort(key=lambda x: x["score"], reverse=True)
    
    if results:
        msg = build_discord_message(results)
        webhook_url = config.get("webhook_url")
        if webhook_url:
            send_webhook(webhook_url, msg)
        else:
            logging.warning("Aucun webhook_url configuré")
        
        # Sauvegarder l'historique
        csv_path = config.get("output_csv", "/data/scores_history.csv")
        append_history(csv_path, history)
    else:
        logging.warning("Aucun résultat calculé aujourd'hui")

# ---------- SCHEDULER SETUP ----------

scheduler = None

def start_scheduler(config_manager: ConfigManager):
    """Démarre le scheduler."""
    global scheduler
    
    config = config_manager.get_config()
    timezone_str = config.get("timezone", "UTC")
    
    scheduler = BlockingScheduler(timezone=timezone_str)

    # Mode dev ou production
    dev_mode = config.get("dev_mode", False) or os.getenv("DEV", "false").lower() in ("true", "1", "yes")
    
    if dev_mode:
        # Mode DEV: exécution toutes les minutes
        trigger = CronTrigger(minute='*', timezone=timezone_str)
        logging.info("🔧 MODE DEV ACTIVÉ: Scheduler programmé toutes les minutes")
    else:
        # Mode production: 22:10 UTC du lundi au vendredi
        trigger = CronTrigger(hour=22, minute=10, day_of_week='mon-fri', timezone=timezone_str)
        logging.info("Scheduler programmé: tous les jours ouvrés 22:10 %s", timezone_str)
    
    scheduler.add_job(lambda: daily_job(config_manager), trigger, name="daily_score_job")

    # Démarrer le scheduler (bloquant)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler arrêté par signal")

# ---------- GRACEFUL SHUTDOWN ----------

def shutdown(signum, frame):
    """Arrêt gracieux."""
    logging.info("Signal %s reçu. Arrêt...", signum)
    if scheduler and scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
    sys.exit(0)

# ---------- MAIN ----------

def main():
    # Créer le répertoire data si manquant
    os.makedirs("/data", exist_ok=True)

    # Initialiser le gestionnaire de configuration
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    # Configurer le logging
    setup_logging(config.get("log_file", "/data/bot_daily_score.log"))

    # Vérifier la configuration
    webhook = config.get("webhook_url", "")
    if not webhook or "discord.com/api/webhooks" not in str(webhook):
        logging.error("webhook_url invalide ou absente. Halte.")
        sys.exit(2)

    # Enregistrer les signaux
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logging.info("Bot DCA V2 démarré. Mode scheduler interne.")
    start_scheduler(config_manager)


if __name__ == "__main__":
    main()
