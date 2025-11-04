#!/usr/bin/env python3
# core/config.py
# Gestion de la configuration (base de données + YAML)

import os
import yaml
import sqlite3
import json
import logging
from typing import Dict, Optional, List


DATABASE_PATH = "/data/bot_config.db"


def init_database():
    """Initialise la base de données SQLite pour stocker la configuration."""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Table de configuration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des formules personnalisées
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formulas (
            name TEXT PRIMARY KEY,
            formula TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Table des tickers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickers (
            symbol TEXT PRIMARY KEY,
            enabled BOOLEAN DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


class ConfigManager:
    """Gestionnaire de configuration unifié (DB + YAML)."""
    
    def __init__(self, yaml_path: str = "/app/config.yaml"):
        self.yaml_path = yaml_path
        self.db_path = DATABASE_PATH
        
        # Initialiser la DB si nécessaire
        if not os.path.exists(self.db_path):
            init_database()
    
    def _get_db_connection(self):
        """Obtient une connexion à la base de données."""
        return sqlite3.connect(self.db_path)
    
    def load_yaml_config(self) -> Dict:
        """Charge la configuration depuis le fichier YAML."""
        if not os.path.exists(self.yaml_path):
            logging.error(f"❌ Fichier de configuration '{self.yaml_path}' introuvable.")
            return {}
        
        try:
            with open(self.yaml_path, "r") as f:
                cfg = yaml.safe_load(f)
            return cfg or {}
        except Exception as e:
            logging.error(f"❌ Erreur lors de la lecture du fichier YAML: {e}")
            return {}
    
    def get_config(self) -> Dict:
        """
        Obtient la configuration complète (YAML + DB overrides).
        La DB a priorité sur le YAML pour les valeurs modifiables.
        """
        # Charger la base YAML
        config = self.load_yaml_config()
        
        # Valeurs par défaut
        config.setdefault("data_period", "365d")
        config.setdefault("drawdown_cap", 0.25)
        config.setdefault("volatility_cap", 0.10)
        config.setdefault("output_csv", "/data/scores_history.csv")
        config.setdefault("log_file", "/data/bot_daily_score.log")
        config.setdefault("timezone", "UTC")
        config.setdefault("dev_mode", False)
        
        if "weights" not in config:
            config["weights"] = {}
        config["weights"].setdefault("drawdown90", 0.25)
        config["weights"].setdefault("rsi14", 0.25)
        config["weights"].setdefault("dist_ma50", 0.20)
        config["weights"].setdefault("momentum30", 0.15)
        config["weights"].setdefault("trend_ma200", 0.10)
        config["weights"].setdefault("volatility20", 0.05)
        
        # Overrides depuis la DB
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            
            # Récupérer les valeurs de config DB
            cursor.execute("SELECT key, value FROM config")
            for key, value in cursor.fetchall():
                try:
                    # Essayer de parser en JSON
                    parsed_value = json.loads(value)
                    
                    # Gérer les clés imbriquées (ex: weights.drawdown90)
                    if "." in key:
                        parts = key.split(".")
                        current = config
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = parsed_value
                    else:
                        config[key] = parsed_value
                except json.JSONDecodeError:
                    # Si ce n'est pas du JSON, garder comme string
                    config[key] = value
            
            # Récupérer les formules personnalisées
            cursor.execute("SELECT name, formula FROM formulas")
            formulas = {}
            for name, formula in cursor.fetchall():
                formulas[name] = formula
            if formulas:
                config["formulas"] = formulas
            
            # Récupérer les tickers actifs
            cursor.execute("SELECT symbol FROM tickers WHERE enabled = 1")
            db_tickers = [row[0] for row in cursor.fetchall()]
            if db_tickers:
                config["tickers"] = db_tickers
            
            conn.close()
        except Exception as e:
            logging.error(f"Erreur lors de la lecture de la DB: {e}")
        
        return config
    
    def set_config_value(self, key: str, value, description: str = ""):
        """Définit une valeur de configuration dans la DB."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        # Convertir en JSON si nécessaire
        if not isinstance(value, str):
            value = json.dumps(value)
        
        cursor.execute("""
            INSERT OR REPLACE INTO config (key, value, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (key, value, description))
        
        conn.commit()
        conn.close()
    
    def get_config_value(self, key: str, default=None):
        """Récupère une valeur de configuration."""
        config = self.get_config()
        
        # Gérer les clés imbriquées
        if "." in key:
            parts = key.split(".")
            current = config
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return default
            return current
        
        return config.get(key, default)
    
    def set_formula(self, name: str, formula: str, description: str = ""):
        """Définit une formule personnalisée."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO formulas (name, formula, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (name, formula, description))
        
        conn.commit()
        conn.close()
    
    def get_formulas(self) -> Dict[str, str]:
        """Récupère toutes les formules personnalisées."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, formula FROM formulas")
        formulas = {name: formula for name, formula in cursor.fetchall()}
        
        conn.close()
        return formulas
    
    def delete_formula(self, name: str):
        """Supprime une formule personnalisée."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM formulas WHERE name = ?", (name,))
        
        conn.commit()
        conn.close()
    
    def add_ticker(self, symbol: str):
        """Ajoute un ticker à surveiller."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO tickers (symbol, enabled, added_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
        """, (symbol,))
        
        conn.commit()
        conn.close()
    
    def remove_ticker(self, symbol: str):
        """Supprime un ticker."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM tickers WHERE symbol = ?", (symbol,))
        
        conn.commit()
        conn.close()
    
    def toggle_ticker(self, symbol: str, enabled: bool):
        """Active ou désactive un ticker."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE tickers SET enabled = ? WHERE symbol = ?
        """, (1 if enabled else 0, symbol))
        
        conn.commit()
        conn.close()
    
    def get_tickers(self, enabled_only: bool = True) -> List[str]:
        """Récupère la liste des tickers."""
        conn = self._get_db_connection()
        cursor = conn.cursor()
        
        if enabled_only:
            cursor.execute("SELECT symbol FROM tickers WHERE enabled = 1")
        else:
            cursor.execute("SELECT symbol FROM tickers")
        
        tickers = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # Si pas de tickers en DB, utiliser ceux du YAML
        if not tickers:
            config = self.load_yaml_config()
            tickers = config.get("tickers", [])
        
        return tickers
