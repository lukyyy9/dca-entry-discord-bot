#!/usr/bin/env python3
# web_app.py
# Interface web d'administration

import os
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from werkzeug.security import check_password_hash
import pandas as pd

from core.config import ConfigManager
from core.scoring import ScoringEngine
from core.backtest import BacktestEngine


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

# Configuration
config_manager = ConfigManager()


def check_admin_token(token: str) -> bool:
    """Vérifie si le token d'admin est valide."""
    config = config_manager.get_config()
    admin_tokens = config.get("admin", {}).get("admin_tokens", [])
    return token in admin_tokens


# Middleware d'authentification
@app.before_request
def require_admin():
    """Vérifie l'authentification pour toutes les routes sauf login."""
    if request.endpoint and request.endpoint != 'login' and not request.endpoint.startswith('static'):
        token = request.cookies.get('admin_token')
        if not token or not check_admin_token(token):
            return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Page de connexion."""
    if request.method == 'POST':
        token = request.form.get('token')
        if check_admin_token(token):
            response = redirect(url_for('index'))
            response.set_cookie('admin_token', token, max_age=7*24*60*60)  # 7 jours
            return response
        else:
            flash('Token invalide', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Déconnexion."""
    response = redirect(url_for('login'))
    response.delete_cookie('admin_token')
    return response


@app.route('/')
def index():
    """Page d'accueil - Dashboard."""
    config = config_manager.get_config()
    
    # Lire l'historique récent
    history = []
    csv_path = config.get("output_csv", "/data/scores_history.csv")
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            # Prendre les 50 dernières entrées
            history = df.tail(50).to_dict('records')
            history.reverse()
        except Exception as e:
            logging.error(f"Erreur lors de la lecture de l'historique: {e}")
    
    return render_template('index.html', config=config, history=history)


@app.route('/config', methods=['GET', 'POST'])
def config_page():
    """Page de configuration."""
    if request.method == 'POST':
        # Mise à jour de la configuration
        try:
            # Webhook
            webhook_url = request.form.get('webhook_url')
            if webhook_url:
                config_manager.set_config_value('webhook_url', webhook_url, "Discord Webhook URL")
            
            # Mode dev
            dev_mode = request.form.get('dev_mode') == 'on'
            config_manager.set_config_value('dev_mode', dev_mode, "Mode développement")
            
            # Data period
            data_period = request.form.get('data_period')
            if data_period:
                config_manager.set_config_value('data_period', data_period, "Période historique")
            
            # Caps
            drawdown_cap = float(request.form.get('drawdown_cap', 0.25))
            config_manager.set_config_value('drawdown_cap', drawdown_cap, "Cap drawdown")
            
            volatility_cap = float(request.form.get('volatility_cap', 0.10))
            config_manager.set_config_value('volatility_cap', volatility_cap, "Cap volatilité")
            
            flash('Configuration mise à jour avec succès', 'success')
        except Exception as e:
            flash(f'Erreur lors de la mise à jour: {str(e)}', 'error')
        
        return redirect(url_for('config_page'))
    
    config = config_manager.get_config()
    return render_template('config.html', config=config)


@app.route('/weights', methods=['GET', 'POST'])
def weights_page():
    """Page de gestion des poids."""
    if request.method == 'POST':
        try:
            weights = {
                'drawdown90': float(request.form.get('drawdown90', 0.25)),
                'rsi14': float(request.form.get('rsi14', 0.25)),
                'dist_ma50': float(request.form.get('dist_ma50', 0.20)),
                'momentum30': float(request.form.get('momentum30', 0.15)),
                'trend_ma200': float(request.form.get('trend_ma200', 0.10)),
                'volatility20': float(request.form.get('volatility20', 0.05))
            }
            
            # Vérifier que la somme fait 1.0
            total = sum(weights.values())
            if abs(total - 1.0) > 0.01:
                flash(f'La somme des poids doit être égale à 1.0 (actuellement: {total:.2f})', 'error')
            else:
                for key, value in weights.items():
                    config_manager.set_config_value(f'weights.{key}', value, f"Poids {key}")
                flash('Poids mis à jour avec succès', 'success')
        except Exception as e:
            flash(f'Erreur lors de la mise à jour: {str(e)}', 'error')
        
        return redirect(url_for('weights_page'))
    
    config = config_manager.get_config()
    weights = config.get('weights', {})
    total = sum(weights.values())
    
    return render_template('weights.html', weights=weights, total=total)


@app.route('/formulas', methods=['GET', 'POST'])
def formulas_page():
    """Page de gestion des formules."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            try:
                name = request.form.get('name')
                formula = request.form.get('formula')
                description = request.form.get('description', '')
                
                config_manager.set_formula(name, formula, description)
                flash(f'Formule "{name}" ajoutée avec succès', 'success')
            except Exception as e:
                flash(f'Erreur lors de l\'ajout de la formule: {str(e)}', 'error')
        
        elif action == 'delete':
            try:
                name = request.form.get('name')
                config_manager.delete_formula(name)
                flash(f'Formule "{name}" supprimée', 'success')
            except Exception as e:
                flash(f'Erreur lors de la suppression: {str(e)}', 'error')
        
        return redirect(url_for('formulas_page'))
    
    formulas = config_manager.get_formulas()
    
    # Formules par défaut (documentation)
    default_formulas = {
        'drawdown': 'min(drawdown / cap, 1.0)',
        'rsi': 'np.clip((70.0 - rsi) / 40.0, 0.0, 1.0)',
        'dist_ma50': 'np.clip(1.0 - (close / ma50), 0.0, 1.0)',
        'momentum': 'np.clip(1.0 / (1.0 + exp(6.0 * momentum)), 0.0, 1.0)',
        'trend_ma200': '1.0 if close > ma200 else 0.3',
        'volatility': 'np.clip(1.0 - (vol20 / cap), 0.0, 1.0)'
    }
    
    return render_template('formulas.html', formulas=formulas, default_formulas=default_formulas)


@app.route('/tickers', methods=['GET', 'POST'])
def tickers_page():
    """Page de gestion des tickers."""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            try:
                symbol = request.form.get('symbol', '').upper()
                if symbol:
                    config_manager.add_ticker(symbol)
                    flash(f'Ticker {symbol} ajouté', 'success')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'error')
        
        elif action == 'remove':
            try:
                symbol = request.form.get('symbol')
                config_manager.remove_ticker(symbol)
                flash(f'Ticker {symbol} supprimé', 'success')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'error')
        
        return redirect(url_for('tickers_page'))
    
    tickers = config_manager.get_tickers(enabled_only=False)
    return render_template('tickers.html', tickers=tickers)


@app.route('/backtest', methods=['GET', 'POST'])
def backtest_page():
    """Page de backtesting."""
    if request.method == 'POST':
        try:
            # Récupérer les paramètres
            tickers = request.form.getlist('tickers')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            
            if not tickers:
                flash('Veuillez sélectionner au moins un ticker', 'error')
                return redirect(url_for('backtest_page'))
            
            # Exécuter le backtest
            config = config_manager.get_config()
            backtest_engine = BacktestEngine(config)
            
            results_df, analyses = backtest_engine.run_multi_ticker_backtest(
                tickers, start_date, end_date
            )
            
            if results_df is not None and not results_df.empty:
                # Sauvegarder les résultats
                results_df.to_csv('/data/backtest_results.csv', index=False)
                
                # Convertir en format lisible pour le template
                results = results_df.to_dict('records')
                
                return render_template('backtest_results.html', 
                                     results=results, 
                                     analyses=analyses,
                                     tickers=tickers,
                                     start_date=start_date,
                                     end_date=end_date)
            else:
                flash('Aucun résultat de backtest', 'warning')
        
        except Exception as e:
            logging.exception("Erreur lors du backtest")
            flash(f'Erreur lors du backtest: {str(e)}', 'error')
    
    # GET: afficher le formulaire
    config = config_manager.get_config()
    tickers = config.get('tickers', [])
    
    # Dates par défaut: 2 ans
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    
    return render_template('backtest.html', 
                         tickers=tickers, 
                         start_date=start_date, 
                         end_date=end_date)


@app.route('/api/config', methods=['GET'])
def api_get_config():
    """API: Récupérer la configuration actuelle."""
    config = config_manager.get_config()
    return jsonify(config)


@app.route('/api/test-scoring', methods=['POST'])
def api_test_scoring():
    """API: Tester le scoring sur un ticker."""
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        
        if not ticker:
            return jsonify({'error': 'Ticker requis'}), 400
        
        config = config_manager.get_config()
        scoring_engine = ScoringEngine(config)
        
        result = scoring_engine.compute_scores_for_ticker(ticker)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({'error': 'Impossible de calculer le score'}), 500
    
    except Exception as e:
        logging.exception("Erreur lors du test de scoring")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Mode développement
    logging.basicConfig(level=logging.INFO)
    app.run(host='0.0.0.0', port=5001, debug=True)
