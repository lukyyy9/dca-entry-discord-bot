#!/usr/bin/env python3
# core/scoring.py
# Logique de scoring centralisée et configurable

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone
from typing import Dict, Optional


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calcule le RSI (Relative Strength Index)."""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    rsi = 100 - (100 / (1 + rs))
    return rsi


class ScoringEngine:
    """Moteur de scoring configurable via base de données."""
    
    def __init__(self, config: Dict):
        """
        Initialise le moteur de scoring avec la configuration.
        
        Args:
            config: Dictionnaire contenant:
                - weights: poids des composants
                - drawdown_cap: cap pour le drawdown
                - volatility_cap: cap pour la volatilité
                - formulas: formules personnalisées (optionnel)
        """
        self.config = config
        self.weights = config.get("weights", {})
        self.drawdown_cap = config.get("drawdown_cap", 0.25)
        self.volatility_cap = config.get("volatility_cap", 0.10)
        
        # Support des formules personnalisées (V2)
        self.formulas = config.get("formulas", {})
    
    def score_drawdown(self, drawdown: float) -> float:
        """Score basé sur le drawdown (baisse depuis le plus haut)."""
        if "drawdown" in self.formulas:
            # Utiliser la formule personnalisée
            try:
                return eval(self.formulas["drawdown"], {
                    "drawdown": drawdown,
                    "cap": self.drawdown_cap,
                    "np": np,
                    "min": min,
                    "max": max
                })
            except Exception as e:
                logging.error(f"Erreur dans formule drawdown: {e}")
        
        # Formule par défaut
        if drawdown <= 0:
            return 0.0
        return min(drawdown / self.drawdown_cap, 1.0)
    
    def score_rsi(self, rsi: float) -> float:
        """Score basé sur le RSI (survente = opportunité)."""
        if "rsi" in self.formulas:
            try:
                return eval(self.formulas["rsi"], {
                    "rsi": rsi,
                    "np": np,
                    "min": min,
                    "max": max
                })
            except Exception as e:
                logging.error(f"Erreur dans formule RSI: {e}")
        
        # Formule par défaut
        val = (70.0 - rsi) / 40.0
        return float(np.clip(val, 0.0, 1.0))
    
    def score_dist_ma50(self, close: float, ma50: float) -> float:
        """Score basé sur la distance à la MA50."""
        if "dist_ma50" in self.formulas:
            try:
                return eval(self.formulas["dist_ma50"], {
                    "close": close,
                    "ma50": ma50,
                    "np": np,
                    "min": min,
                    "max": max
                })
            except Exception as e:
                logging.error(f"Erreur dans formule dist_ma50: {e}")
        
        # Formule par défaut
        if np.isnan(ma50) or ma50 == 0:
            return 0.0
        dist = 1.0 - (close / ma50)
        return float(np.clip(dist, 0.0, 1.0))
    
    def score_momentum(self, momentum: float) -> float:
        """Score basé sur le momentum (négatif = opportunité)."""
        if "momentum" in self.formulas:
            try:
                return eval(self.formulas["momentum"], {
                    "momentum": momentum,
                    "np": np,
                    "min": min,
                    "max": max,
                    "exp": np.exp
                })
            except Exception as e:
                logging.error(f"Erreur dans formule momentum: {e}")
        
        # Formule par défaut
        k = 6.0
        s = 1.0 / (1.0 + np.exp(k * momentum))
        return float(np.clip(s, 0.0, 1.0))
    
    def score_trend_ma200(self, close: float, ma200: float) -> float:
        """Score basé sur la tendance MA200."""
        if "trend_ma200" in self.formulas:
            try:
                return eval(self.formulas["trend_ma200"], {
                    "close": close,
                    "ma200": ma200,
                    "np": np,
                    "min": min,
                    "max": max
                })
            except Exception as e:
                logging.error(f"Erreur dans formule trend_ma200: {e}")
        
        # Formule par défaut
        if np.isnan(ma200) or ma200 == 0:
            return 0.5
        return 1.0 if close > ma200 else 0.3
    
    def score_volatility(self, vol20: float) -> float:
        """Score basé sur la volatilité (faible = opportunité)."""
        if "volatility" in self.formulas:
            try:
                return eval(self.formulas["volatility"], {
                    "vol20": vol20,
                    "cap": self.volatility_cap,
                    "np": np,
                    "min": min,
                    "max": max
                })
            except Exception as e:
                logging.error(f"Erreur dans formule volatility: {e}")
        
        # Formule par défaut
        if vol20 <= 0:
            return 1.0
        return float(np.clip(1.0 - (vol20 / self.volatility_cap), 0.0, 1.0))
    
    def compute_scores_for_ticker(self, ticker: str, period: str = "365d") -> Optional[Dict]:
        """
        Calcule les scores pour un ticker donné.
        
        Args:
            ticker: Symbole du ticker
            period: Période historique à récupérer
            
        Returns:
            Dictionnaire avec les scores et métriques, ou None en cas d'erreur
        """
        # Récupérer le nom du produit
        product_name = ticker
        try:
            ticker_info = yf.Ticker(ticker)
            info = ticker_info.info
            product_name = info.get("longName") or info.get("shortName") or ticker
        except Exception as e:
            logging.warning(f"Impossible de récupérer le nom du produit pour {ticker}: {e}")
        
        try:
            df = yf.download(ticker, period=period, interval="1d", progress=False)
        except Exception as e:
            logging.exception(f"Erreur yfinance pour {ticker}: {e}")
            return None

        if df is None or df.empty:
            logging.warning(f"Pas de données pour {ticker}")
            return None

        # Flatten multi-index columns if present
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

        # Calcul des scores avec le moteur
        draw_sc = self.score_drawdown(drawdown90)
        rsi_sc = self.score_rsi(rsi14)
        ma50_sc = self.score_dist_ma50(close, ma50)
        mom_sc = self.score_momentum(momentum30)
        trend_sc = self.score_trend_ma200(close, ma200)
        vol_sc = self.score_volatility(vol20)

        # Score composite
        composite = (
            self.weights.get("drawdown90", 0.25) * draw_sc
            + self.weights.get("rsi14", 0.25) * rsi_sc
            + self.weights.get("dist_ma50", 0.20) * ma50_sc
            + self.weights.get("momentum30", 0.15) * mom_sc
            + self.weights.get("trend_ma200", 0.10) * trend_sc
            + self.weights.get("volatility20", 0.05) * vol_sc
        )

        score_100 = round(100.0 * composite, 1)

        return {
            "ticker": ticker,
            "product_name": product_name,
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
    
    def compute_score_at_date(self, df: pd.DataFrame, date_idx: int) -> Optional[Dict]:
        """
        Calcule le score à une date donnée (pour le backtesting).
        
        Args:
            df: DataFrame avec les données historiques
            date_idx: Index de la date pour laquelle calculer le score
            
        Returns:
            Dictionnaire avec le score et les métriques, ou None si pas assez de données
        """
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
        
        draw_sc = self.score_drawdown(drawdown90)
        rsi_sc = self.score_rsi(rsi14)
        ma50_sc = self.score_dist_ma50(close, ma50)
        mom_sc = self.score_momentum(momentum30)
        trend_sc = self.score_trend_ma200(close, ma200)
        vol_sc = self.score_volatility(vol20)
        
        composite = (
            self.weights.get("drawdown90", 0.25) * draw_sc
            + self.weights.get("rsi14", 0.25) * rsi_sc
            + self.weights.get("dist_ma50", 0.20) * ma50_sc
            + self.weights.get("momentum30", 0.15) * mom_sc
            + self.weights.get("trend_ma200", 0.10) * trend_sc
            + self.weights.get("volatility20", 0.05) * vol_sc
        )
        
        return {
            "date": historical_data.index[-1],
            "score": round(100.0 * composite, 1),
            "close": close,
            "rsi14": round(rsi14, 2),
            "ma50": ma50,
            "ma200": ma200
        }
