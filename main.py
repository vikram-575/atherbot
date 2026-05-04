#!/usr/bin/env python3
# =============================================================================
# AETHER FLOW SYSTEM – Main Bot (Live Trading Loop)
# 🔱 SMC Flow System converted from Pine Script by Fatich.id
# =============================================================================
#
# USAGE:
#   python main.py --mode live       # Live trading (after profitable dry run)
#   python main.py --mode dry        # Dry run (paper trade, no real orders)
#   python main.py --mode backtest   # Backtest on historical data
#
# SETUP:
#   pip install ccxt pandas numpy requests
#   Edit config.py with your API keys and settings
# =============================================================================

import argparse
import logging
import time
import sys
import io
from datetime import datetime

import config as cfg
from indicators import run_all_indicators, generate_signals, SignalResult
from exchange   import DeltaExchangeConnector
from alerts     import TelegramAlerter
from backtest   import run_backtest


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING SETUP  (UTF-8 safe for Windows consoles)
# ─────────────────────────────────────────────────────────────────────────────

_fmt = logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")

# Console handler – write to stdout.buffer with explicit UTF-8 so emojis work
# on Windows regardless of the active code page.
_console_stream = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)
_console_handler = logging.StreamHandler(_console_stream)
_console_handler.setFormatter(_fmt)

# File handler – always UTF-8
_file_handler = logging.FileHandler(cfg.LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(_fmt)

logging.basicConfig(
    level    = getattr(logging, cfg.LOG_LEVEL, logging.INFO),
    handlers = [_console_handler, _file_handler],
)
logger = logging.getLogger("aether.main")


# ─────────────────────────────────────────────────────────────────────────────
# BOT STATE
# ─────────────────────────────────────────────────────────────────────────────

class BotState:
    def __init__(self):
        self.open_long   = False
        self.open_short  = False
        self.entry_price = 0.0
        self.stop_loss   = 0.0
        self.take_profit = 0.0
        self.position_size = 0.0
        self.trade_count  = 0
        self.win_count    = 0
        self.last_heartbeat = datetime.utcnow()

state = BotState()


# ─────────────────────────────────────────────────────────────────────────────
# CONFLUENCE CHECKER
# ─────────────────────────────────────────────────────────────────────────────

def get_confirmations(sig: SignalResult, direction: str) -> list[str]:
    """Returns list of confirmed signals for the alert message."""
    conf = []
    if direction == "long":
        if sig.ut_buy:        conf.append("UT Bot BUY signal")
        if sig.hull_bull:     conf.append("Hull Suite bullish trend")
        if sig.tbr_bull:      conf.append("3-Bar Reversal pattern")
        if sig.in_bull_fvg:   conf.append("Price inside Bull FVG")
        if sig.price_in_bull_ob: conf.append("Price inside Bull Order Block")
        if sig.rs_bull_momentum: conf.append("Reversal Signal (9-bar bull)")
    else:
        if sig.ut_sell:       conf.append("UT Bot SELL signal")
        if sig.hull_bear:     conf.append("Hull Suite bearish trend")
        if sig.tbr_bear:      conf.append("3-Bar Reversal pattern")
        if sig.in_bear_fvg:   conf.append("Price inside Bear FVG")
        if sig.price_in_bear_ob: conf.append("Price inside Bear Order Block")
        if sig.rs_bear_momentum: conf.append("Reversal Signal (9-bar bear)")
    return conf


# ─────────────────────────────────────────────────────────────────────────────
# DRY RUN MODE
# ─────────────────────────────────────────────────────────────────────────────

def run_dry(conn: DeltaExchangeConnector, tg: TelegramAlerter):
    """
    Paper trading: signals fire, Telegram alerts send, no real orders placed.
    Sends a candle update every 15m and a partial-signal alert when setup is forming.
    """
    logger.info("DRY RUN mode - No real orders will be placed")
    tg._send(
        "🔱 <b>Aether Flow – DRY RUN started</b>\n"
        f"Symbol: <b>{cfg.SYMBOL}</b> | TF: {cfg.TIMEFRAME}\n"
        f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
        "No real orders will be placed.\n"
        "You will receive a candle update every 15 minutes."
    )

    while True:
        try:
            df   = conn.fetch_ohlcv(limit=300)
            df   = run_all_indicators(df, cfg)
            sigs = generate_signals(df)

            if not sigs or len(df) < 10:
                logger.warning("Not enough candle data yet - waiting for next candle...")
                conn.wait_for_candle_close(cfg.TIMEFRAME)
                continue

            last  = sigs[-1]       # most recent completed candle
            price = df["close"].values[-1]
            atr   = float(df["ut_atr"].values[-1])

            # ── Full Long Signal ───────────────────────────────────────────
            if last.final_long and not state.open_long:
                sl   = price - cfg.STOP_LOSS_ATR_MULT * atr
                tp   = price + cfg.STOP_LOSS_ATR_MULT * atr * cfg.TAKE_PROFIT_RR
                conf = get_confirmations(last, "long")
                logger.info(f"LONG @ {price:.4f} | SL={sl:.4f} | TP={tp:.4f}")
                tg.send_long_signal(price, sl, tp, conf, atr)
                state.open_long   = True
                state.open_short  = False
                state.entry_price = price
                state.stop_loss   = sl
                state.take_profit = tp

            # ── Full Short Signal ──────────────────────────────────────────
            elif last.final_short and not state.open_short:
                sl   = price + cfg.STOP_LOSS_ATR_MULT * atr
                tp   = price - cfg.STOP_LOSS_ATR_MULT * atr * cfg.TAKE_PROFIT_RR
                conf = get_confirmations(last, "short")
                logger.info(f"SHORT @ {price:.4f} | SL={sl:.4f} | TP={tp:.4f}")
                tg.send_short_signal(price, sl, tp, conf, atr)
                state.open_short  = True
                state.open_long   = False
                state.entry_price = price
                state.stop_loss   = sl
                state.take_profit = tp

            # ── Partial Signal: UT Bot + Hull aligned, confluence missing ──
            else:
                if last.ut_buy and last.hull_bull and not state.open_long:
                    reason = "UT Bot BUY + Hull Bullish confirmed"
                    logger.info(f"SETUP FORMING (LONG) @ {price:.4f} – waiting confluence")
                    tg.send_partial_signal("long", price, reason)
                elif last.ut_sell and last.hull_bear and not state.open_short:
                    reason = "UT Bot SELL + Hull Bearish confirmed"
                    logger.info(f"SETUP FORMING (SHORT) @ {price:.4f} – waiting confluence")
                    tg.send_partial_signal("short", price, reason)

            # ── Check SL / TP in dry run ───────────────────────────────────
            if state.open_long:
                if price <= state.stop_loss:
                    loss = abs(price - state.entry_price)
                    logger.info(f"Long SL hit @ {price:.4f} | Loss={loss:.4f}")
                    tg.send_stop_loss_hit(price, loss)
                    state.open_long = False
                elif price >= state.take_profit:
                    profit = abs(price - state.entry_price)
                    logger.info(f"Long TP hit @ {price:.4f} | Profit={profit:.4f}")
                    tg.send_take_profit_hit(price, profit)
                    state.open_long = False
                    state.win_count += 1

            if state.open_short:
                if price >= state.stop_loss:
                    loss = abs(state.entry_price - price)
                    logger.info(f"Short SL hit @ {price:.4f} | Loss={loss:.4f}")
                    tg.send_stop_loss_hit(price, loss)
                    state.open_short = False
                elif price <= state.take_profit:
                    profit = abs(state.entry_price - price)
                    logger.info(f"Short TP hit @ {price:.4f} | Profit={profit:.4f}")
                    tg.send_take_profit_hit(price, profit)
                    state.open_short = False
                    state.win_count += 1

            # ── Per-candle status update to Telegram ──────────────────────
            tg.send_candle_status(price, atr, last)
            logger.info(
                f"Candle check done | Price={price:.2f} | "
                f"UT_buy={last.ut_buy} | UT_sell={last.ut_sell} | "
                f"Hull_bull={last.hull_bull} | Hull_bear={last.hull_bear} | "
                f"LONG={last.final_long} | SHORT={last.final_short}"
            )

            # ── Hourly heartbeat (fixed: use total_seconds()) ─────────────
            now = datetime.utcnow()
            if (now - state.last_heartbeat).total_seconds() > 3600:
                tg.send_heartbeat(0.0, 1 if (state.open_long or state.open_short) else 0)
                state.last_heartbeat = now

            conn.wait_for_candle_close(cfg.TIMEFRAME)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            tg._send("⛔ <b>Aether Flow DRY RUN stopped.</b>")
            break
        except Exception as e:
            logger.error(f"Loop error: {e}")
            tg.send_error(str(e))
            time.sleep(60)




# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING MODE
# ─────────────────────────────────────────────────────────────────────────────

def run_live(conn: DeltaExchangeConnector, tg: TelegramAlerter):
    """
    Live trading: real orders placed on Delta Exchange.
    Only enable after validating in dry run!
    """
    logger.warning("🔴 LIVE MODE – Real orders will be placed!")
    tg.send_bot_started()

    while True:
        try:
            df   = conn.fetch_ohlcv(limit=300)
            df   = run_all_indicators(df, cfg)
            sigs = generate_signals(df)

            if not sigs or len(df) < 10:
                logger.warning("⚠️  Not enough candle data yet – waiting for next candle...")
                conn.wait_for_candle_close(cfg.TIMEFRAME)
                continue

            last  = sigs[-1]
            price = conn.get_ticker()
            atr   = float(df["ut_atr"].values[-1])
            bal   = conn.get_balance()

            # ── Check existing position ────────────────────────────────────
            existing = conn.get_position()

            # ── Long entry ────────────────────────────────────────────────
            if last.final_long and existing is None:
                sl   = price - cfg.STOP_LOSS_ATR_MULT * atr
                tp   = price + cfg.STOP_LOSS_ATR_MULT * atr * cfg.TAKE_PROFIT_RR
                size = conn.calculate_position_size(price, sl, bal)

                if size > 0:
                    order = conn.place_market_order("buy", size, sl, tp)
                    if order:
                        conf = get_confirmations(last, "long")
                        tg.send_long_signal(price, sl, tp, conf, atr)
                        tg.send_order_placed("buy", price, size, str(order.get("id", "")))
                        state.open_long = True
                        state.trade_count += 1

            # ── Short entry ───────────────────────────────────────────────
            elif last.final_short and existing is None:
                sl   = price + cfg.STOP_LOSS_ATR_MULT * atr
                tp   = price - cfg.STOP_LOSS_ATR_MULT * atr * cfg.TAKE_PROFIT_RR
                size = conn.calculate_position_size(price, sl, bal)

                if size > 0:
                    order = conn.place_market_order("sell", size, sl, tp)
                    if order:
                        conf = get_confirmations(last, "short")
                        tg.send_short_signal(price, sl, tp, conf, atr)
                        tg.send_order_placed("sell", price, size, str(order.get("id", "")))
                        state.open_short = True
                        state.trade_count += 1

            # ── Opposite signal → close ───────────────────────────────────
            if existing:
                pos_side = existing.get("side", "")
                if pos_side == "long" and last.final_short:
                    conn.cancel_all_orders()
                    conn.close_position()
                    tg._send("🔄 <b>Long closed by opposite short signal</b>")
                elif pos_side == "short" and last.final_long:
                    conn.cancel_all_orders()
                    conn.close_position()
                    tg._send("🔄 <b>Short closed by opposite long signal</b>")

            # Hourly heartbeat
            now = datetime.utcnow()
            if (now - state.last_heartbeat).seconds > 3600:
                tg.send_heartbeat(bal, 1 if existing else 0)
                state.last_heartbeat = now

            conn.wait_for_candle_close(cfg.TIMEFRAME)

        except KeyboardInterrupt:
            logger.info("⛔ Bot stopped by user")
            tg._send("⛔ <b>Aether Flow LIVE BOT stopped.</b>")
            break
        except Exception as e:
            logger.error(f"Live loop error: {e}")
            tg.send_error(str(e))
            time.sleep(60)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="🔱 Aether Flow Trading Bot")
    parser.add_argument(
        "--mode",
        choices=["live", "dry", "backtest"],
        default="dry",
        help="Trading mode (default: dry)",
    )
    args = parser.parse_args()

    logger.info(f"🔱 Aether Flow System starting in [{args.mode.upper()}] mode")

    conn = DeltaExchangeConnector(cfg)
    tg   = TelegramAlerter(cfg)

    if args.mode == "backtest":
        logger.info("📊 Fetching historical data for backtest...")
        df = conn.fetch_ohlcv(limit=1000)
        result, trade_log, equity = run_backtest(cfg, df)
        logger.info("✅ Backtest complete. See backtest_trades.csv")

    elif args.mode == "dry":
        run_dry(conn, tg)

    elif args.mode == "live":
        # Safety guard
        confirm = input(
            "\n⚠️  You are about to start LIVE trading with real money.\n"
            "Type 'YES I UNDERSTAND' to proceed: "
        )
        if confirm != "YES I UNDERSTAND":
            print("Aborted.")
            return
        run_live(conn, tg)


if __name__ == "__main__":
    main()
