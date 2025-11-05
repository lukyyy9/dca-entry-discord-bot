# DCA Entry Discord Bot

A sophisticated Discord bot that calculates daily Dollar Cost Averaging (DCA) entry signals for ETFs and stocks based on technical analysis metrics. The bot includes a web interface for configuration management and backtesting capabilities.

## 🚀 Features

- **Automated Daily Scoring**: Calculates entry signals for multiple tickers based on your custom formulas
- **Discord Notifications**: Sends daily score updates to Discord via webhooks with formatted messages and alerts
- **Web Administration Interface**: Full-featured web UI for managing everything - tickers, weights, formulas, and configuration (no need to edit config files!)
- **Backtesting Engine**: Historical performance analysis with visual results and detailed metrics
- **Fully Customizable Scoring**:
  - Define your own Python-based scoring formulas
  - Adjust component weights dynamically
  - Access to technical indicators (RSI, MA, momentum, volatility, etc.)
  - Real-time formula validation and preview
- **Minimal Configuration**: Only admin token required in `config.yaml` - everything else (including webhook) via web UI
- **Docker Support**: Fully containerized deployment with Docker Compose
- **Historical Data Tracking**: Persistent storage of daily scores in CSV format and SQLite database

## 📋 Prerequisites

- Docker and Docker Compose
- Discord webhook URL (for notifications)

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/lukyyy9/DEDBot.git
cd DEDBot
```

### 2. Configure the Bot

Create a minimal `config.yaml` with only the admin token:

```yaml
# Admin token for web interface access
admin:
  admin_tokens:
    - "your-secure-admin-token-here"
```

### 3. Create Data Directory

```bash
mkdir -p data
```

### 4. Start the Services

Using the provided script:

```bash
chmod +x start-v2.sh
./start-v2.sh
```

Or manually with Docker Compose:

```bash
docker-compose up -d
```

## 🏗️ Architecture

The project consists of two main services:

### 1. DCA Bot (`dca-bot`)

- Runs scheduled daily scoring calculations
- Fetches market data from Yahoo Finance
- Calculates technical indicators using your custom formulas
- Sends notifications to Discord
- Logs results to CSV and SQLite database

### 2. Web Interface (`dca-web`)

- Admin authentication system
- **Database-driven configuration management** (no file editing required)
- Real-time configuration updates (tickers, weights, formulas, caps)
- Live scoring preview
- Backtesting interface with visual results
- Runs on port 5001

### Configuration Storage

- **config.yaml**: Minimal bootstrap settings (admin tokens only - webhook optional)
- **SQLite Database** (`/data/bot_config.db`): All runtime configuration
  - Discord webhook URL
  - Tickers list
  - Custom formulas
  - Component weights
  - System settings (caps, periods, etc.)

## 📊 Scoring System

The bot calculates a composite score (0-100) based on **fully customizable formulas and weights**. All scoring components are user-managed through the web interface.

### User-Configurable Components

The scoring system is entirely flexible - you define:

1. **Custom Formulas**: Create scoring formulas using Python expressions
2. **Component Weights**: Adjust the importance of each component
3. **Available Variables**: 
   - `drawdown` - Distance from all-time high
   - `rsi` - Relative Strength Index
   - `close`, `ma50`, `ma200` - Price and moving averages
   - `momentum` - Price momentum
   - `vol20` - 20-day volatility
   - `np` - NumPy functions (clip, exp, etc.)

### Example Formulas

```python
# RSI-based scoring (oversold = opportunity)
np.clip((70.0 - rsi) / 40.0, 0.0, 1.0)

# Drawdown scoring
min(drawdown / cap, 1.0)

# Distance from MA50
np.clip((ma50 - close) / ma50 / 0.15, 0.0, 1.0)
```

### Score Interpretation

- ✅ **55-100**: Strong entry signal (triggers @everyone alert)
- ⚠️ **45-54**: Neutral zone
- ❌ **0-44**: Weak entry signal

## 🌐 Web Interface

Access the web interface at `http://localhost:5001`

### Features

- **Dashboard**: Overview of current configuration and recent scores
- **Tickers Management**: Add/remove ETFs and stocks to monitor (no config.yaml editing needed)
- **Weights Configuration**: Adjust scoring component weights in real-time
  - **Weight Profiles**: Save and manage multiple weight configurations
  - Quickly switch between different testing profiles
  - Create, edit, and delete profiles with descriptions
  - One-click profile activation to load saved weights
- **Formulas Editor**: Create and manage custom Python scoring formulas with syntax validation
- **Configuration Editor**: Modify caps, periods, and other settings through the UI
- **Backtest**: Historical performance analysis with visual charts and metrics

All configuration changes are stored in a SQLite database (`/data/bot_config.db`) and take effect immediately.

### Authentication

Use one of the admin tokens defined in `config.yaml` to access the interface.

### 📁 Using Weight Profiles

Weight profiles allow you to save and manage multiple weight configurations, making it easy to test different strategies:

**Creating a Profile:**
1. Navigate to the **Weights** page
2. Click **➕ Nouveau Profil**
3. Enter a name and description for your profile
4. The current weights will be saved to the new profile

**Managing Profiles:**
- **✓ Activer**: Load the weights from this profile into the active configuration
- **💾 Sauv.**: Save the current weights to this profile (overwrite)
- **✏️**: Edit the profile name and description
- **🗑️**: Delete the profile (only for inactive profiles)

**Use Cases:**
- **Conservative Profile**: Higher weights on drawdown and volatility for safer entries
- **Aggressive Profile**: Focus on momentum and trend indicators
- **Testing Profile**: Experiment with new weight distributions without losing your proven configuration
- **Seasonal Profiles**: Different strategies for different market conditions

**Note:** Only one profile can be active at a time. The active profile's weights are automatically loaded into the formulas.

## 🐳 Docker Configuration

### Environment Variables

- `TZ`: Timezone (default: UTC)
- `DEV`: Development mode - "true" runs every minute, "false" runs daily
- `SECRET_KEY`: Flask secret key for web interface sessions

### Volumes

- `./config.yaml:/app/config.yaml:ro` - Configuration file (read-only)
- `./data:/data` - Persistent data storage

### Ports

- `5001`: Web interface port

## 📁 Project Structure

```
.
├── bot_daily_score_v2.py    # Main bot script with scheduler
├── web_app.py               # Flask web interface
├── backtest_v2.py           # Backtesting script
├── config.yaml              # Configuration file
├── requirements.txt         # Python dependencies
├── Dockerfile               # Docker image definition
├── docker-compose.yml       # Multi-service orchestration
├── start-v2.sh              # Quick start script
├── core/                    # Core modules
│   ├── __init__.py
│   ├── config.py           # Configuration manager
│   ├── scoring.py          # Scoring engine
│   └── backtest.py         # Backtest engine
├── templates/              # HTML templates for web interface
├── static/                 # Static assets (CSS, JS)
└── data/                   # Persistent data directory
    ├── scores_history.csv
    ├── backtest_results.csv
    └── bot_daily_score.log
```

## 🔧 Development

### Running Locally (without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the bot:
```bash
python bot_daily_score_v2.py
```

3. Run the web interface:
```bash
python web_app.py
```

### Development Mode

Set `DEV=true` in docker-compose.yml to run scoring every minute instead of daily (useful for testing).

## 📊 Data Sources

- **Market Data**: Yahoo Finance (via yfinance library)
- **Supported Assets**: Any ticker available on Yahoo Finance (stocks, ETFs, crypto, etc.)

## 🔐 Security Notes

- Change default admin tokens in production
- Set a secure `SECRET_KEY` for the web interface
- Keep `config.yaml` private (contains webhook URLs)
- Use HTTPS in production environments

## 📝 Logging

Logs are stored in:
- Bot logs: `data/bot_daily_score.log`
- Docker logs: Use `docker-compose logs -f` to follow logs

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- Built with [yfinance](https://github.com/ranaroussi/yfinance) for market data
- Uses [Flask](https://flask.palletsprojects.com/) for the web interface
- Scheduled with [APScheduler](https://apscheduler.readthedocs.io/)

## 📞 Support

For issues and questions, please open an issue on the [GitHub repository](https://github.com/lukyyy9/DEDBot).

---

**Note**: This bot is for educational and informational purposes only. Always do your own research before making investment decisions.
