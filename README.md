# 🔱 AETHER FLOW SYSTEM – Python Bot
### Converted from Pine Script (Fatich.id) → Python + CCXT + Delta Exchange

---

## 📁 File Structure

```
aether_flow_bot/
├── config.py       ← All settings (API keys, symbols, risk params)
├── indicators.py   ← All Pine Script indicators converted to Python
├── exchange.py     ← Delta Exchange connector (CCXT)
├── alerts.py       ← Telegram alerts
├── backtest.py     ← Historical backtester
├── main.py         ← Bot runner (live / dry / backtest)
└── requirements.txt
```

---

## ⚡ Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure your settings
Edit `config.py`:
```python
API_KEY    = "your_delta_api_key"
API_SECRET = "your_delta_api_secret"
SYMBOL     = "BTC/USDT"       # or ETH/USDT, SOL/USDT etc.
TIMEFRAME  = "15m"
TESTNET    = True             # start with testnet!
```

### 3. Set up Telegram bot
1. Message `@BotFather` → `/newbot` → copy token
2. Get your chat ID from `@userinfobot`
3. Paste both into `config.py`

### 4. Run backtest first
```bash
python main.py --mode backtest
```
Check `backtest_trades.csv` for results.

### 5. Paper trade (dry run)
```bash
python main.py --mode dry
```
Run for 2–3 weeks. Check Telegram for signals.

### 6. Go live (only when profitable in dry run)
```bash
python main.py --mode live
```

---

## 🧠 Strategy Logic

### Entry Signal (Long)
All of these must be true:
- ✅ UT Bot **BUY** signal (ATR trailing stop crossover)
- ✅ Hull Suite **bullish** (MHULL > SHULL)
- ✅ At least ONE of:
  - Three Bar Reversal bullish pattern detected
  - Price inside a Bull Order Block zone
  - Price inside a Bull Fair Value Gap

### Entry Signal (Short)
- ✅ UT Bot **SELL** signal
- ✅ Hull Suite **bearish**
- ✅ At least ONE of: TBR bear / Bear OB / Bear FVG

### Exit
- Stop Loss: `entry ± (ATR × STOP_LOSS_ATR_MULT)`
- Take Profit: `entry ± (SL distance × TAKE_PROFIT_RR)`
- Trailing stop updates every candle
- Opposite signal also exits position

---

## ⚙️ Indicators Converted

| Pine Script Component | Python Implementation |
|---|---|
| UT Bot ATR Trailing Stop | `compute_ut_bot()` in indicators.py |
| Hull Suite (HMA/EHMA/THMA) | `compute_hull_suite()` |
| LuxAlgo FVG Detection | `compute_fvg()` |
| LuxAlgo Order Blocks | `compute_order_blocks()` |
| Three Bar Reversal | `compute_three_bar_reversal()` |
| Reversal Signal (9-bar) | `compute_reversal_signal()` |

---

## ⚠️ Risk Warnings
- Always start with TESTNET and dry run
- Never risk more than 1–2% per trade (set in config.py)
- API keys must have **Trade** permission only — never Withdrawal
- Past backtest results do not guarantee future profits
- This is not financial advice
