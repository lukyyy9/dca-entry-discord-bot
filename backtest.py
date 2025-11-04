#!/usr/bin/env python3
# filepath: backtest.py

import pandas as pd
import numpy as np
import yfinance as yf
import yaml
from datetime import datetime, timedelta
from bot_daily_score import (
    compute_rsi,
    score_drawdown,
    score_rsi,
    score_dist_ma50,
    score_momentum,
    score_trend_ma200,
    score_volatility
)

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def compute_score_at_date(df, date_idx, cfg):
    """Calcule le score à une date donnée avec les données disponibles jusqu'à cette date."""
    historical_data = df.iloc[:date_idx+1].copy()
    
    if len(historical_data) < 200:
        return None
    
    historical_data["MA50"] = historical_data["Close"].rolling(50, min_periods=1).mean()
    historical_data["MA200"] = historical_data["Close"].rolling(200, min_periods=1).mean()
    historical_data["RSI14"] = compute_rsi(historical_data["Close"], 14)
    historical_data["High90"] = historical_data["Close"].rolling(90, min_periods=1).max()
    historical_data["Drawdown90"] = (historical_data["High90"] - historical_data["Close"]) / historical_data["High90"]
    historical_data["Vol20"] = historical_data["Close"].pct_change().rolling(20, min_periods=1).std()
    historical_data["Momentum30"] = historical_data["Close"].pct_change(periods=30)
    
    latest = historical_data.iloc[-1]
    
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
        w["drawdown90"] * draw_sc +
        w["rsi14"] * rsi_sc +
        w["dist_ma50"] * ma50_sc +
        w["momentum30"] * mom_sc +
        w["trend_ma200"] * trend_sc +
        w["volatility20"] * vol_sc
    )
    
    return {
        "date": historical_data.index[-1],
        "score": round(100.0 * composite, 1),
        "close": close,
        "rsi14": round(rsi14, 2),
        "ma50": ma50,
        "ma200": ma200
    }

def backtest_ticker(ticker, cfg, start_date, end_date):
    """Backtest sur une période donnée."""
    print(f"\n📊 Backtesting {ticker} du {start_date} au {end_date}")
    
    # Récupérer plus de données pour avoir l'historique nécessaire
    extended_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
    
    df = yf.download(ticker, start=extended_start, end=end_date, interval="1d", progress=False)
    
    if df.empty:
        print(f"❌ Pas de données pour {ticker}")
        return None
    
    # Flatten multi-index columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.dropna()
    
    results = []
    test_start_idx = df.index.searchsorted(pd.Timestamp(start_date))
    
    # Simuler un signal tous les 7 jours (hebdomadaire)
    for i in range(test_start_idx, len(df), 7):
        score_data = compute_score_at_date(df, i, cfg)
        if score_data:
            # Calculer le rendement sur 30 jours suivants
            if i + 30 < len(df):
                future_price = df.iloc[i + 30]["Close"]
                current_price = df.iloc[i]["Close"]
                return_30d = ((future_price - current_price) / current_price) * 100
                score_data["return_30d"] = round(return_30d, 2)
                results.append(score_data)
    
    return pd.DataFrame(results)

def analyze_results(results_df):
    """Analyse les résultats du backtest."""
    if results_df is None or results_df.empty:
        return
    
    print("\n📈 ANALYSE DES RÉSULTATS")
    print("=" * 60)
    
    # Grouper par catégories de score
    results_df["score_category"] = pd.cut(
        results_df["score"],
        bins=[0, 45, 55, 100],
        labels=["Défavorable (<45)", "Neutre (45-55)", "Favorable (>55)"]
    )
    
    grouped = results_df.groupby("score_category")["return_30d"].agg(["mean", "median", "count", "std"])
    
    print("\nPerformance par catégorie de score:")
    print(grouped)
    
    print(f"\n✅ Signaux 'Favorable' (score > 55):")
    favorable = results_df[results_df["score"] > 55]
    if not favorable.empty:
        print(f"  - Nombre: {len(favorable)}")
        print(f"  - Rendement moyen à 30j: {favorable['return_30d'].mean():.2f}%")
        print(f"  - Rendement médian à 30j: {favorable['return_30d'].median():.2f}%")
        print(f"  - Taux de succès (rendement > 0): {(favorable['return_30d'] > 0).sum() / len(favorable) * 100:.1f}%")
    
    print(f"\n❌ Signaux 'Défavorable' (score < 45):")
    unfavorable = results_df[results_df["score"] < 45]
    if not unfavorable.empty:
        print(f"  - Nombre: {len(unfavorable)}")
        print(f"  - Rendement moyen à 30j: {unfavorable['return_30d'].mean():.2f}%")
        print(f"  - Rendement médian à 30j: {unfavorable['return_30d'].median():.2f}%")
    
    # Correlation score vs rendement
    correlation = results_df["score"].corr(results_df["return_30d"])
    print(f"\n🔗 Corrélation score vs rendement 30j: {correlation:.3f}")
    
    return results_df

if __name__ == "__main__":
    cfg = load_config("config.yaml")
    
    # Période de test (dernières 2 années)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    
    all_results = []
    
    for ticker in cfg["tickers"]:
        results = backtest_ticker(ticker, cfg, start_date, end_date)
        if results is not None and not results.empty:
            results["ticker"] = ticker
            all_results.append(results)
            analyze_results(results)
    
    # Sauvegarder les résultats
    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        combined.to_csv("backtest_results.csv", index=False)
        print(f"\n💾 Résultats sauvegardés dans backtest_results.csv")
        
        # Analyse globale
        print("\n" + "=" * 60)
        print("📊 ANALYSE GLOBALE (tous les tickers)")
        print("=" * 60)
        analyze_results(combined)