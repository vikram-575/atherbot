# =============================================================================
# AETHER FLOW SYSTEM – Backtester
# =============================================================================
# Simulates the Aether Flow strategy on historical OHLCV data.
# Reports: win rate, PnL, max drawdown, Sharpe ratio, trade log.
# =============================================================================

import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import Optional
from indicators import run_all_indicators, generate_signals

logger = logging.getLogger("aether.backtest")


# ─────────────────────────────────────────────────────────────────────────────
# TRADE RECORD
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    entry_bar:   int
    entry_time:  pd.Timestamp
    entry_price: float
    direction:   str           # "long" or "short"
    size:        float
    stop_loss:   float
    take_profit: float
    exit_bar:    Optional[int]         = None
    exit_time:   Optional[pd.Timestamp] = None
    exit_price:  Optional[float]       = None
    exit_reason: str                   = ""
    pnl:         float                 = 0.0
    pnl_pct:     float                 = 0.0
    open:        bool                  = True


# ─────────────────────────────────────────────────────────────────────────────
# BACKTESTER
# ─────────────────────────────────────────────────────────────────────────────

class AetherBacktester:

    def __init__(self, cfg, initial_balance: float = 10_000.0):
        self.cfg             = cfg
        self.initial_balance = initial_balance
        self.trades: list[Trade] = []
        self.equity: list[float] = []

    # ─────────────────────────────────────────────────────────────────────────

    def run(self, df: pd.DataFrame) -> dict:
        """
        Main backtest loop.
        df must have: open, high, low, close, volume columns.
        Returns a results summary dict.
        """
        logger.info(f"🔄 Running backtest on {len(df)} candles...")

        # Run indicators
        df = run_all_indicators(df, self.cfg)
        signals = generate_signals(df)

        balance       = self.initial_balance
        open_trade: Optional[Trade] = None

        highs  = df["high"].values
        lows   = df["low"].values
        closes = df["close"].values
        atrs   = df["ut_atr"].values
        times  = df.index.tolist()

        self.equity = [balance]

        for i, sig in enumerate(signals):
            if i < 10:     # warm-up
                continue

            c = closes[i]
            h = highs[i]
            l = lows[i]
            atr = atrs[i]

            # ── Manage open trade ──────────────────────────────────────────
            if open_trade and open_trade.open:
                # Trailing stop update (ATR trailing)
                if self.cfg.TRAILING_STOP and open_trade.direction == "long":
                    new_sl = c - self.cfg.STOP_LOSS_ATR_MULT * atr
                    open_trade.stop_loss = max(open_trade.stop_loss, new_sl)
                elif self.cfg.TRAILING_STOP and open_trade.direction == "short":
                    new_sl = c + self.cfg.STOP_LOSS_ATR_MULT * atr
                    open_trade.stop_loss = min(open_trade.stop_loss, new_sl)

                # Check SL hit (intra-bar wick)
                if open_trade.direction == "long" and l <= open_trade.stop_loss:
                    exit_price = open_trade.stop_loss
                    pnl = (exit_price - open_trade.entry_price) * open_trade.size
                    self._close_trade(open_trade, i, times[i], exit_price, "stop_loss", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

                elif open_trade.direction == "short" and h >= open_trade.stop_loss:
                    exit_price = open_trade.stop_loss
                    pnl = (open_trade.entry_price - exit_price) * open_trade.size
                    self._close_trade(open_trade, i, times[i], exit_price, "stop_loss", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

                # Check TP hit
                elif open_trade.direction == "long" and h >= open_trade.take_profit:
                    exit_price = open_trade.take_profit
                    pnl = (exit_price - open_trade.entry_price) * open_trade.size
                    self._close_trade(open_trade, i, times[i], exit_price, "take_profit", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

                elif open_trade.direction == "short" and l <= open_trade.take_profit:
                    exit_price = open_trade.take_profit
                    pnl = (open_trade.entry_price - exit_price) * open_trade.size
                    self._close_trade(open_trade, i, times[i], exit_price, "take_profit", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

                # Opposite signal → exit
                elif open_trade.direction == "long" and sig.final_short:
                    pnl = (c - open_trade.entry_price) * open_trade.size
                    self._close_trade(open_trade, i, times[i], c, "signal_flip", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

                elif open_trade.direction == "short" and sig.final_long:
                    pnl = (open_trade.entry_price - c) * open_trade.size
                    self._close_trade(open_trade, i, times[i], c, "signal_flip", pnl, balance)
                    balance += pnl
                    self.equity.append(balance)
                    open_trade = None

            # ── New trade entry ────────────────────────────────────────────
            if open_trade is None:
                if sig.final_long:
                    sl = c - self.cfg.STOP_LOSS_ATR_MULT * atr
                    tp = c + self.cfg.STOP_LOSS_ATR_MULT * atr * self.cfg.TAKE_PROFIT_RR
                    size = self._calc_size(balance, c, sl)
                    if size > 0:
                        open_trade = Trade(
                            entry_bar=i, entry_time=times[i], entry_price=c,
                            direction="long", size=size, stop_loss=sl, take_profit=tp,
                        )
                        self.trades.append(open_trade)

                elif sig.final_short:
                    sl = c + self.cfg.STOP_LOSS_ATR_MULT * atr
                    tp = c - self.cfg.STOP_LOSS_ATR_MULT * atr * self.cfg.TAKE_PROFIT_RR
                    size = self._calc_size(balance, c, sl)
                    if size > 0:
                        open_trade = Trade(
                            entry_bar=i, entry_time=times[i], entry_price=c,
                            direction="short", size=size, stop_loss=sl, take_profit=tp,
                        )
                        self.trades.append(open_trade)

        # Force-close last open trade at final close
        if open_trade and open_trade.open:
            c = closes[-1]
            if open_trade.direction == "long":
                pnl = (c - open_trade.entry_price) * open_trade.size
            else:
                pnl = (open_trade.entry_price - c) * open_trade.size
            self._close_trade(open_trade, len(signals)-1, times[-1], c, "end_of_data", pnl, balance)
            balance += pnl

        self.equity.append(balance)
        return self._build_report(balance)

    # ─────────────────────────────────────────────────────────────────────────

    def _calc_size(self, balance: float, entry: float, sl: float) -> float:
        risk   = balance * self.cfg.RISK_PER_TRADE
        dist   = abs(entry - sl)
        return (risk / dist) if dist > 0 else 0.0

    def _close_trade(self, trade: Trade, bar: int, ts, price: float,
                     reason: str, pnl: float, balance: float):
        trade.exit_bar    = bar
        trade.exit_time   = ts
        trade.exit_price  = price
        trade.exit_reason = reason
        trade.pnl         = pnl
        trade.pnl_pct     = pnl / balance * 100 if balance else 0
        trade.open        = False

    def _build_report(self, final_balance: float) -> dict:
        closed = [t for t in self.trades if not t.open]
        if not closed:
            return {"error": "No completed trades"}

        pnls      = [t.pnl for t in closed]
        wins      = [p for p in pnls if p > 0]
        losses    = [p for p in pnls if p <= 0]
        win_rate  = len(wins) / len(closed) * 100
        avg_win   = np.mean(wins)   if wins   else 0
        avg_loss  = np.mean(losses) if losses else 0
        pf        = abs(avg_win / avg_loss) if avg_loss else float("inf")

        # Max drawdown
        eq      = np.array(self.equity)
        peak    = np.maximum.accumulate(eq)
        dd      = (eq - peak) / peak * 100
        max_dd  = dd.min()

        # Sharpe (daily if equity > 1 point)
        ret     = np.diff(eq) / eq[:-1]
        sharpe  = (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0

        total_return = (final_balance - self.initial_balance) / self.initial_balance * 100

        report = {
            "total_trades":      len(closed),
            "win_rate":          f"{win_rate:.1f}%",
            "profit_factor":     f"{pf:.2f}",
            "total_pnl":         f"{sum(pnls):.2f} USDT",
            "total_return":      f"{total_return:.2f}%",
            "avg_win":           f"{avg_win:.2f} USDT",
            "avg_loss":          f"{avg_loss:.2f} USDT",
            "max_drawdown":      f"{max_dd:.2f}%",
            "sharpe_ratio":      f"{sharpe:.2f}",
            "final_balance":     f"{final_balance:.2f} USDT",
            "initial_balance":   f"{self.initial_balance:.2f} USDT",
            "stop_loss_exits":   sum(1 for t in closed if t.exit_reason == "stop_loss"),
            "take_profit_exits": sum(1 for t in closed if t.exit_reason == "take_profit"),
            "signal_flip_exits": sum(1 for t in closed if t.exit_reason == "signal_flip"),
        }

        self._print_report(report)
        return report

    def _print_report(self, r: dict):
        print("\n" + "=" * 50)
        print("  🔱 AETHER FLOW – BACKTEST RESULTS")
        print("=" * 50)
        for k, v in r.items():
            print(f"  {k.replace('_', ' ').title():<25} {v}")
        print("=" * 50 + "\n")

    def get_trade_log(self) -> pd.DataFrame:
        """Returns closed trades as a DataFrame."""
        closed = [t for t in self.trades if not t.open]
        if not closed:
            return pd.DataFrame()
        return pd.DataFrame([{
            "entry_time":   t.entry_time,
            "exit_time":    t.exit_time,
            "direction":    t.direction,
            "entry_price":  t.entry_price,
            "exit_price":   t.exit_price,
            "stop_loss":    t.stop_loss,
            "take_profit":  t.take_profit,
            "size":         t.size,
            "pnl":          t.pnl,
            "pnl_pct":      t.pnl_pct,
            "exit_reason":  t.exit_reason,
        } for t in closed])


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run_backtest(cfg, df: pd.DataFrame = None, save_csv: bool = True):
    """
    Convenience wrapper. Pass df or it fetches from exchange.
    """
    if df is None:
        from exchange import DeltaExchangeConnector
        conn = DeltaExchangeConnector(cfg)
        df   = conn.fetch_ohlcv(limit=1000)

    bt     = AetherBacktester(cfg)
    result = bt.run(df)

    if save_csv:
        log = bt.get_trade_log()
        if not log.empty:
            fname = "backtest_trades.csv"
            log.to_csv(fname, index=False)
            logger.info(f"📁 Trade log saved to {fname}")

    return result, bt.get_trade_log(), bt.equity
