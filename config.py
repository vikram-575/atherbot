# =============================================================================
# AETHER FLOW SYSTEM – Config (Delta Exchange)
# Converted from Pine Script by Fatich.id
# =============================================================================

# ── Exchange ──────────────────────────────────────────────────────────────────
EXCHANGE_ID       = "delta"          # CCXT exchange id for Delta Exchange
API_KEY           = "At3ltaha906wG6dCTmsciQW41EX6er"   # Replace with your Delta API key
API_SECRET        = "ONDlDkVRhMBfZGkdr9kciKsL3YqkdVFa0AVl0wJGDt2Hi7xBIgNI1GMAFHpM"    # Replace with your Delta API secret
TESTNET           = False            # Testnet has no market data; dry mode keeps you safe

# ── Trading Pair ─────────────────────────────────────────────────────────────
# Delta Exchange CCXT uses perpetual futures notation: BTC/USDT:USDT
SYMBOL            = "BTC/USDT:USDT" # Perpetual futures on Delta Exchange
TIMEFRAME         = "1m"            # Candle timeframe: 1m, 5m, 15m, 1h, 4h

# ── Position Sizing ───────────────────────────────────────────────────────────
RISK_PER_TRADE    = 0.01             # 1% of account balance per trade
MAX_OPEN_TRADES   = 1                # Max concurrent positions
LEVERAGE          = 1                # 1 = spot-like, increase for futures

# ── UT Bot Settings ───────────────────────────────────────────────────────────
UT_KEY_VALUE      = 2                # Sensitivity multiplier (Pine: a = 2)
UT_ATR_PERIOD     = 6                # ATR period (Pine: c = 6)

# ── Hull Suite Settings ───────────────────────────────────────────────────────
HULL_LENGTH       = 55               # Hull MA period
HULL_MODE         = "HMA"            # Options: HMA, EHMA, THMA
HULL_MULT         = 1.0              # Length multiplier

# ── FVG Settings ─────────────────────────────────────────────────────────────
FVG_THRESHOLD_PCT = 0.0              # Min gap size % (0 = all gaps)
FVG_EXTEND_BARS   = 20               # How many bars FVG zone extends

# ── Order Block Settings ──────────────────────────────────────────────────────
OB_PIVOT_LENGTH   = 5                # Volume pivot lookback (Pine: lengthOB)
OB_BULL_COUNT     = 3                # Max bullish OBs to track
OB_BEAR_COUNT     = 3                # Max bearish OBs to track

# ── Three Bar Reversal ────────────────────────────────────────────────────────
TBR_PATTERN_TYPE  = "All"            # "Normal", "Enhanced", "All"

# ── Reversal Signal (9-bar momentum counter) ──────────────────────────────────
RS_COUNT_TARGET   = 9                # Bars for momentum signal (Pine: 9)

# ── Risk Management ───────────────────────────────────────────────────────────
STOP_LOSS_ATR_MULT  = 1.5            # Stop loss = 1.5x ATR from entry
TAKE_PROFIT_RR      = 2.0            # Take profit = 2:1 reward:risk ratio
TRAILING_STOP       = True           # Enable ATR trailing stop

# ── Telegram Alerts ───────────────────────────────────────────────────────────
TELEGRAM_ENABLED  = True
TELEGRAM_BOT_TOKEN = "8496261616:AAFkY3uY56zVMwZtw0RU3WEyBBGPA6pX8Ng"   # From @BotFather
TELEGRAM_CHAT_ID   = "2016943459"     # Your chat/group ID

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL         = "INFO"           # DEBUG, INFO, WARNING, ERROR
LOG_FILE          = "aether_flow.log"
