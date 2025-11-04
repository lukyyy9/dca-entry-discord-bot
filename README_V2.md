# Bot DCA - Version 2.0 🤖

Bot Discord pour calculer des scores d'opportunité DCA (Dollar Cost Averaging) avec interface web d'administration.

## 🆕 Nouveautés V2

### Interface Web d'Administration
- **Dashboard** : Vue d'ensemble de la configuration et de l'historique
- **Configuration** : Édition des paramètres du bot (webhook, mode dev, caps)
- **Poids** : Ajustement des poids des composants de scoring
- **Formules** : Personnalisation des formules de calcul
- **Tickers** : Gestion de la liste des actifs surveillés
- **Backtest** : Test de la stratégie sur données historiques

### Architecture Refactorisée
- Code modulaire dans `core/`
- Configuration unifiée (YAML + base de données SQLite)
- Moteur de scoring réutilisable
- Backtest utilisant le même code que le bot (pas de duplication)

## 🚀 Installation et Démarrage

### Option 1 : Docker Compose (Recommandé)

```bash
# Cloner le repo
git clone <repo-url>
cd dca-entry-discord-bot

# Créer le fichier config.yaml
cp config.yaml.example config.yaml
# Éditer config.yaml avec vos paramètres

# Lancer les services
docker-compose up -d

# Accéder à l'interface web
open http://localhost:5001
```

L'interface web sera accessible sur `http://localhost:5001`

### Option 2 : Développement local

```bash
# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Créer les répertoires
mkdir -p data

# Lancer le bot
python bot_daily_score_v2.py

# Dans un autre terminal, lancer l'interface web
python web_app.py
```

## 🔐 Authentification

L'interface web est protégée par token. Le token doit être configuré dans `config.yaml` :

```yaml
admin:
  admin_tokens:
    - "votre-token-secret-ici"
```

## 📊 Composants du Score

Le score DCA est calculé sur 6 composants :

1. **Drawdown 90j** (25%) : Baisse depuis le plus haut sur 90 jours
2. **RSI 14j** (25%) : Relative Strength Index (survente = opportunité)
3. **Distance MA50** (20%) : Écart par rapport à la moyenne mobile 50 jours
4. **Momentum 30j** (15%) : Momentum sur 30 jours
5. **Trend MA200** (10%) : Position par rapport à la MA200 (tendance)
6. **Volatilité 20j** (5%) : Volatilité sur 20 jours

Score final : **0-100**
- **> 55** : Signal favorable ✅
- **45-55** : Signal neutre ⚠️
- **< 45** : Signal défavorable ❌

## 🔧 Configuration

### Fichier config.yaml

```yaml
webhook_url: "https://discord.com/api/webhooks/..."
tickers:
  - "PSP5.PA"  # CAC 40 ESG
  - "SXRT.DE"  # STOXX Europe 600 Tech
  - "DCAM.PA"  # MSCI EMU

data_period: "365d"
drawdown_cap: 0.25
volatility_cap: 0.10
timezone: "UTC"

weights:
  drawdown90: 0.25
  rsi14: 0.25
  dist_ma50: 0.20
  momentum30: 0.15
  trend_ma200: 0.10
  volatility20: 0.05

admin:
  admin_tokens:
    - "votre-token-secret"
```

### Variables d'environnement

- `DEV=true` : Mode développement (exécution toutes les minutes)
- `SECRET_KEY` : Clé secrète pour Flask (production)
- `TZ=UTC` : Timezone

## 🧪 Backtesting

### Via l'interface web
1. Accéder à l'onglet "Backtest"
2. Sélectionner les tickers et la période
3. Lancer le backtest

### En ligne de commande
```bash
python backtest_v2.py
```

Les résultats sont sauvegardés dans `/data/backtest_results.csv`

## 🎨 Personnalisation des Formules

L'interface web permet de personnaliser les formules de scoring.

### Exemple : Modifier la formule RSI

Dans l'onglet "Formules", créer une formule personnalisée :
- **Nom** : `rsi`
- **Formule** : `np.clip((80.0 - rsi) / 50.0, 0.0, 1.0)`

Variables disponibles :
- `drawdown`, `cap` (pour drawdown)
- `rsi` (pour RSI)
- `close`, `ma50` (pour distance MA50)
- `momentum` (pour momentum)
- `close`, `ma200` (pour trend)
- `vol20`, `cap` (pour volatilité)

Fonctions disponibles : `np` (numpy), `min`, `max`, `exp`

## 📁 Structure du Projet

```
dca-entry-discord-bot/
├── core/                    # Modules core
│   ├── __init__.py
│   ├── config.py           # Gestion configuration (YAML + DB)
│   ├── scoring.py          # Moteur de scoring
│   └── backtest.py         # Moteur de backtesting
├── templates/              # Templates HTML
│   ├── base.html
│   ├── index.html
│   ├── config.html
│   ├── weights.html
│   ├── formulas.html
│   ├── tickers.html
│   ├── backtest.html
│   └── backtest_results.html
├── static/                 # Fichiers statiques (CSS, JS)
├── data/                   # Données persistantes
│   ├── bot_config.db      # Base de données SQLite
│   ├── scores_history.csv # Historique des scores
│   └── backtest_results.csv
├── bot_daily_score_v2.py  # Bot principal V2
├── backtest_v2.py         # Script de backtest V2
├── web_app.py             # Interface web Flask
├── config.yaml            # Configuration YAML
├── requirements.txt       # Dépendances Python
├── Dockerfile            # Image Docker
└── docker-compose.yml    # Orchestration Docker
```

## 🔄 Migration depuis V1

La V2 est compatible avec la V1. Les fichiers suivants sont conservés :
- `config.yaml` : Configuration initiale
- `data/scores_history.csv` : Historique des scores

Pour migrer :
1. Mettre à jour l'image Docker : `docker-compose pull`
2. Redémarrer les services : `docker-compose up -d`
3. La base de données sera créée automatiquement

## 📝 API Endpoints

L'interface web expose quelques endpoints API :

- `GET /api/config` : Configuration actuelle (JSON)
- `POST /api/test-scoring` : Tester le scoring sur un ticker
  ```json
  {
    "ticker": "PSP5.PA"
  }
  ```

## 🛠️ Développement

### Ajouter un nouveau composant de scoring

1. Modifier `core/scoring.py` :
   - Ajouter une méthode `score_nouveau_composant()`
   - Intégrer dans `compute_scores_for_ticker()`

2. Mettre à jour les poids dans `config.yaml`

3. Ajouter la documentation dans l'interface web

### Personnaliser l'interface

Les templates utilisent Jinja2 et un CSS custom (thème sombre GitHub-like).

Modifier les templates dans `templates/` pour personnaliser l'interface.

## 📊 Logs

- **Bot** : `/data/bot_daily_score.log`
- **Web** : Sortie standard Docker

Voir les logs :
```bash
docker-compose logs -f dca-bot
docker-compose logs -f dca-web
```

## 🐛 Dépannage

### Le bot ne démarre pas
- Vérifier que `config.yaml` existe et contient un `webhook_url` valide
- Vérifier les logs : `docker-compose logs dca-bot`

### L'interface web n'est pas accessible
- Vérifier que le port 5001 n'est pas déjà utilisé
- Vérifier les logs : `docker-compose logs dca-web`

### Les scores ne sont pas calculés
- Vérifier les tickers dans la configuration
- Vérifier la connexion internet (téléchargement données Yahoo Finance)

## 📜 Licence

MIT

## 👤 Auteur

[@lukyyy9](https://github.com/lukyyy9)

---

**⚠️ Avertissement** : Ce bot n'est pas un conseil financier. Les scores calculés sont indicatifs et ne garantissent pas de performance future.
