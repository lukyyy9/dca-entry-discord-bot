#!/usr/bin/env python3
# backtest_v2.py
# Backtest V2 - Utilise le module core.backtest

import logging
from datetime import datetime, timedelta
from core.config import ConfigManager
from core.backtest import BacktestEngine


def main():
    """Lance le backtest depuis la ligne de commande."""
    logging.basicConfig(level=logging.INFO)
    
    # Charger la configuration
    config_manager = ConfigManager()
    config = config_manager.get_config()
    
    # Période de test (2 dernières années par défaut)
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    
    print(f"\n🔬 Lancement du backtest du {start_date} au {end_date}")
    print("=" * 60)
    
    # Créer le moteur de backtest
    backtest_engine = BacktestEngine(config)
    
    # Récupérer les tickers
    tickers = config.get("tickers", [])
    if not tickers:
        print("❌ Aucun ticker configuré")
        return
    
    print(f"📊 Tickers: {', '.join(tickers)}\n")
    
    # Exécuter le backtest
    results_df, analyses = backtest_engine.run_multi_ticker_backtest(
        tickers, start_date, end_date
    )
    
    if results_df is not None and not results_df.empty:
        # Sauvegarder les résultats
        results_df.to_csv("/data/backtest_results.csv", index=False)
        print(f"\n💾 Résultats sauvegardés dans /data/backtest_results.csv")
        
        # Afficher l'analyse globale
        if "_global" in analyses:
            global_analysis = analyses["_global"]
            
            print("\n" + "=" * 60)
            print("📊 ANALYSE GLOBALE")
            print("=" * 60)
            
            if "global" in global_analysis:
                g = global_analysis["global"]
                print(f"\n📈 Statistiques générales:")
                print(f"  - Signaux totaux: {g['total_signals']}")
                print(f"  - Rendement moyen à 30j: {g['mean_return']}%")
                print(f"  - Rendement médian à 30j: {g['median_return']}%")
                print(f"  - Écart-type: {g['std_return']}%")
                print(f"  - Taux de succès: {g['success_rate']}%")
            
            if "favorable" in global_analysis:
                f = global_analysis["favorable"]
                print(f"\n✅ Signaux favorables (score > 55):")
                print(f"  - Nombre: {f['count']}")
                print(f"  - Rendement moyen: {f['mean_return']}%")
                print(f"  - Rendement médian: {f['median_return']}%")
                print(f"  - Taux de succès: {f['success_rate']}%")
                print(f"  - Meilleur: {f['max_return']}%")
                print(f"  - Pire: {f['min_return']}%")
            
            if "unfavorable" in global_analysis:
                u = global_analysis["unfavorable"]
                print(f"\n❌ Signaux défavorables (score < 45):")
                print(f"  - Nombre: {u['count']}")
                print(f"  - Rendement moyen: {u['mean_return']}%")
                print(f"  - Rendement médian: {u['median_return']}%")
            
            if "correlation" in global_analysis:
                print(f"\n🔗 Corrélation score/rendement: {global_analysis['correlation']}")
        
        # Afficher les analyses par ticker
        for ticker in tickers:
            if ticker in analyses:
                print(f"\n" + "=" * 60)
                print(f"📊 {ticker}")
                print("=" * 60)
                
                analysis = analyses[ticker]
                if "global" in analysis:
                    g = analysis["global"]
                    print(f"Signaux: {g['total_signals']} | "
                          f"Rendement moyen: {g['mean_return']}% | "
                          f"Succès: {g['success_rate']}%")
    else:
        print("❌ Aucun résultat de backtest")


if __name__ == "__main__":
    main()
