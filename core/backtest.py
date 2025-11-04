#!/usr/bin/env python3
# core/backtest.py
# Module de backtesting utilisant le moteur de scoring unifié

import pandas as pd
import numpy as np
import yfinance as yf
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .scoring import ScoringEngine


class BacktestEngine:
    """Moteur de backtesting unifié."""
    
    def __init__(self, config: Dict):
        """
        Initialise le moteur de backtesting.
        
        Args:
            config: Configuration complète du bot
        """
        self.config = config
        self.scoring_engine = ScoringEngine(config)
    
    def run_backtest(self, ticker: str, start_date: str, end_date: str, 
                     interval_days: int = 7) -> Optional[pd.DataFrame]:
        """
        Exécute un backtest sur un ticker donné.
        
        Args:
            ticker: Symbole du ticker
            start_date: Date de début (format YYYY-MM-DD)
            end_date: Date de fin (format YYYY-MM-DD)
            interval_days: Intervalle entre les signaux (défaut: 7 jours)
            
        Returns:
            DataFrame avec les résultats ou None en cas d'erreur
        """
        logging.info(f"📊 Backtesting {ticker} du {start_date} au {end_date}")
        
        # Récupérer plus de données pour avoir l'historique nécessaire
        extended_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=400)).strftime("%Y-%m-%d")
        
        try:
            df = yf.download(ticker, start=extended_start, end=end_date, interval="1d", progress=False)
        except Exception as e:
            logging.error(f"❌ Erreur lors du téléchargement des données pour {ticker}: {e}")
            return None
        
        if df.empty:
            logging.warning(f"❌ Pas de données pour {ticker}")
            return None
        
        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df.dropna()
        
        results = []
        test_start_idx = df.index.searchsorted(pd.Timestamp(start_date))
        
        # Simuler un signal à intervalle régulier
        for i in range(test_start_idx, len(df), interval_days):
            score_data = self.scoring_engine.compute_score_at_date(df, i)
            if score_data:
                # Calculer le rendement sur 30 jours suivants
                if i + 30 < len(df):
                    future_price = df.iloc[i + 30]["Close"]
                    current_price = df.iloc[i]["Close"]
                    return_30d = ((future_price - current_price) / current_price) * 100
                    score_data["return_30d"] = round(return_30d, 2)
                    results.append(score_data)
        
        return pd.DataFrame(results)
    
    def analyze_results(self, results_df: pd.DataFrame) -> Dict:
        """
        Analyse les résultats du backtest.
        
        Args:
            results_df: DataFrame avec les résultats du backtest
            
        Returns:
            Dictionnaire avec les statistiques d'analyse
        """
        if results_df is None or results_df.empty:
            return {}
        
        analysis = {}
        
        # Grouper par catégories de score
        results_df["score_category"] = pd.cut(
            results_df["score"],
            bins=[0, 45, 55, 100],
            labels=["Défavorable (<45)", "Neutre (45-55)", "Favorable (>55)"]
        )
        
        grouped = results_df.groupby("score_category")["return_30d"].agg(["mean", "median", "count", "std"])
        analysis["by_category"] = grouped.to_dict()
        
        # Analyse des signaux favorables
        favorable = results_df[results_df["score"] > 55]
        if not favorable.empty:
            analysis["favorable"] = {
                "count": len(favorable),
                "mean_return": round(favorable["return_30d"].mean(), 2),
                "median_return": round(favorable["return_30d"].median(), 2),
                "success_rate": round((favorable["return_30d"] > 0).sum() / len(favorable) * 100, 1),
                "max_return": round(favorable["return_30d"].max(), 2),
                "min_return": round(favorable["return_30d"].min(), 2)
            }
        
        # Analyse des signaux défavorables
        unfavorable = results_df[results_df["score"] < 45]
        if not unfavorable.empty:
            analysis["unfavorable"] = {
                "count": len(unfavorable),
                "mean_return": round(unfavorable["return_30d"].mean(), 2),
                "median_return": round(unfavorable["return_30d"].median(), 2)
            }
        
        # Corrélation score vs rendement
        correlation = results_df["score"].corr(results_df["return_30d"])
        analysis["correlation"] = round(correlation, 3)
        
        # Statistiques globales
        analysis["global"] = {
            "total_signals": len(results_df),
            "mean_return": round(results_df["return_30d"].mean(), 2),
            "median_return": round(results_df["return_30d"].median(), 2),
            "std_return": round(results_df["return_30d"].std(), 2),
            "success_rate": round((results_df["return_30d"] > 0).sum() / len(results_df) * 100, 1)
        }
        
        return analysis
    
    def run_multi_ticker_backtest(self, tickers: List[str], start_date: str, 
                                   end_date: str) -> tuple:
        """
        Exécute un backtest sur plusieurs tickers.
        
        Args:
            tickers: Liste des tickers à backtester
            start_date: Date de début
            end_date: Date de fin
            
        Returns:
            Tuple (DataFrame combiné, Dict d'analyses)
        """
        all_results = []
        all_analyses = {}
        
        for ticker in tickers:
            results = self.run_backtest(ticker, start_date, end_date)
            if results is not None and not results.empty:
                results["ticker"] = ticker
                all_results.append(results)
                
                analysis = self.analyze_results(results)
                all_analyses[ticker] = analysis
        
        if all_results:
            combined = pd.concat(all_results, ignore_index=True)
            
            # Analyse globale
            global_analysis = self.analyze_results(combined)
            all_analyses["_global"] = global_analysis
            
            return combined, all_analyses
        
        return None, {}
