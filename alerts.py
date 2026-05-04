# =============================================================================
# AETHER FLOW SYSTEM – Telegram Alerts
# =============================================================================

import requests
import logging
from datetime import datetime

logger = logging.getLogger("aether.telegram")


class TelegramAlerter:
    """Sends trade alerts and system messages to Telegram."""

    def __init__(self, cfg):
        self.enabled   = cfg.TELEGRAM_ENABLED
        self.token     = cfg.TELEGRAM_BOT_TOKEN
        self.chat_id   = cfg.TELEGRAM_CHAT_ID
        self.base_url  = f"https://api.telegram.org/bot{self.token}"
        self.symbol    = cfg.SYMBOL
        self.timeframe = cfg.TIMEFRAME

    # ─────────────────────────────────────────────────────────────────────────

    def _send(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return True
        try:
            r = requests.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id":    self.chat_id,
                    "text":       text,
                    "parse_mode": parse_mode,
                },
                timeout=10,
            )
            if not r.ok:
                logger.warning(f"Telegram send failed: {r.text}")
                return False
            return True
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # SIGNAL ALERTS
    # ─────────────────────────────────────────────────────────────────────────

    def send_long_signal(
        self,
        price: float,
        stop_loss: float,
        take_profit: float,
        confirmations: list[str],
        atr: float = 0.0,
    ):
        rr = abs(take_profit - price) / abs(price - stop_loss) if price != stop_loss else 0
        msg = (
            f"🟢 <b>LONG SIGNAL – Aether Flow</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Pair: <b>{self.symbol}</b>  [{self.timeframe}]\n"
            f"⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Entry:       <b>{price:.4f}</b>\n"
            f"🛡️  Stop Loss:  <code>{stop_loss:.4f}</code>\n"
            f"💰 Take Profit: <code>{take_profit:.4f}</code>\n"
            f"📐 R:R Ratio:   <b>1:{rr:.1f}</b>\n"
            f"📉 ATR:         {atr:.4f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Confirmations:\n"
            + "\n".join(f"  • {c}" for c in confirmations) +
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ System: 🔱 SMC Flow | Delta Exchange"
        )
        self._send(msg)

    def send_short_signal(
        self,
        price: float,
        stop_loss: float,
        take_profit: float,
        confirmations: list[str],
        atr: float = 0.0,
    ):
        rr = abs(price - take_profit) / abs(stop_loss - price) if stop_loss != price else 0
        msg = (
            f"🔴 <b>SHORT SIGNAL – Aether Flow</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Pair: <b>{self.symbol}</b>  [{self.timeframe}]\n"
            f"⏰ Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Entry:       <b>{price:.4f}</b>\n"
            f"🛡️  Stop Loss:  <code>{stop_loss:.4f}</code>\n"
            f"💰 Take Profit: <code>{take_profit:.4f}</code>\n"
            f"📐 R:R Ratio:   <b>1:{rr:.1f}</b>\n"
            f"📉 ATR:         {atr:.4f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Confirmations:\n"
            + "\n".join(f"  • {c}" for c in confirmations) +
            f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚡ System: 🔱 SMC Flow | Delta Exchange"
        )
        self._send(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # TRADE EXECUTION ALERTS
    # ─────────────────────────────────────────────────────────────────────────

    def send_order_placed(self, side: str, price: float, amount: float, order_id: str):
        emoji = "🟢" if side == "buy" else "🔴"
        msg = (
            f"{emoji} <b>Order Placed</b>\n"
            f"Side: {side.upper()} | Amount: {amount}\n"
            f"Price: {price:.4f} | ID: <code>{order_id}</code>"
        )
        self._send(msg)

    def send_position_closed(self, side: str, pnl: float):
        emoji = "✅" if pnl >= 0 else "❌"
        msg = (
            f"{emoji} <b>Position Closed</b>\n"
            f"Side: {side.upper()} | PnL: <b>{pnl:+.4f} USDT</b>"
        )
        self._send(msg)

    def send_stop_loss_hit(self, price: float, loss: float):
        msg = (
            f"🛑 <b>Stop Loss Hit</b>\n"
            f"Price: {price:.4f} | Loss: <code>{loss:.4f} USDT</code>"
        )
        self._send(msg)

    def send_take_profit_hit(self, price: float, profit: float):
        msg = (
            f"🎯 <b>Take Profit Hit</b>\n"
            f"Price: {price:.4f} | Profit: <code>+{profit:.4f} USDT</code>"
        )
        self._send(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # INDICATOR ALERTS
    # ─────────────────────────────────────────────────────────────────────────

    def send_fvg_alert(self, fvg_type: str, top: float, bottom: float):
        emoji = "🔼" if fvg_type == "bull" else "🔽"
        msg = (
            f"{emoji} <b>FVG Detected</b> ({fvg_type.upper()})\n"
            f"Zone: {bottom:.4f} – {top:.4f}"
        )
        self._send(msg)

    def send_ob_alert(self, ob_type: str, top: float, bottom: float):
        emoji = "🟩" if ob_type == "bull" else "🟥"
        msg = (
            f"{emoji} <b>Order Block Formed</b> ({ob_type.upper()})\n"
            f"Zone: {bottom:.4f} – {top:.4f}"
        )
        self._send(msg)

    def send_hull_trend_change(self, direction: str):
        emoji = "📈" if direction == "up" else "📉"
        msg = f"{emoji} <b>Hull Trend Changed:</b> {direction.upper()}"
        self._send(msg)

    def send_ut_signal(self, signal_type: str, price: float):
        emoji = "🟢" if signal_type == "buy" else "🔴"
        msg = (
            f"{emoji} <b>UT Bot Signal: {signal_type.upper()}</b>\n"
            f"Price: {price:.4f}"
        )
        self._send(msg)

    # ─────────────────────────────────────────────────────────────────────────
    # SYSTEM ALERTS
    # ─────────────────────────────────────────────────────────────────────────

    def send_bot_started(self):
        msg = (
            f"🔱 <b>Aether Flow Bot Started</b>\n"
            f"Symbol: {self.symbol} | TF: {self.timeframe}\n"
            f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"Mode: {'TESTNET ⚠️' if True else 'LIVE 🔴'}"
        )
        self._send(msg)

    def send_error(self, message: str):
        msg = f"⚠️ <b>Bot Error</b>\n<code>{message}</code>"
        self._send(msg)

    def send_heartbeat(self, balance: float, open_trades: int):
        msg = (
            f"💓 <b>Heartbeat</b>\n"
            f"Balance: {balance:.2f} USDT\n"
            f"Open Trades: {open_trades}\n"
            f"Time: {datetime.utcnow().strftime('%H:%M')} UTC"
        )
        self._send(msg)

    def send_candle_status(self, price: float, atr: float, sig) -> None:
        """
        Sends a brief indicator status after every candle close.
        Helps the user confirm the bot is alive and see what indicators are saying.
        """
        def yn(v): return "YES" if v else "no"

        position = "LONG" if getattr(sig, "_open_long", False) else (
                   "SHORT" if getattr(sig, "_open_short", False) else "None")

        msg = (
            f"📊 <b>Candle Update – {self.symbol} [{self.timeframe}]</b>\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💲 Price : <b>{price:.2f}</b>   ATR: {atr:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 UT Bot  BUY  : <b>{yn(sig.ut_buy)}</b>\n"
            f"🤖 UT Bot  SELL : <b>{yn(sig.ut_sell)}</b>\n"
            f"🌊 Hull   BULL  : <b>{yn(sig.hull_bull)}</b>\n"
            f"🌊 Hull   BEAR  : <b>{yn(sig.hull_bear)}</b>\n"
            f"📦 Bull OB hit  : {yn(sig.price_in_bull_ob)}\n"
            f"📦 Bear OB hit  : {yn(sig.price_in_bear_ob)}\n"
            f"🕳️  Bull FVG hit : {yn(sig.in_bull_fvg)}\n"
            f"🕳️  Bear FVG hit : {yn(sig.in_bear_fvg)}\n"
            f"🔁 3BR  Bull    : {yn(sig.tbr_bull)}\n"
            f"🔁 3BR  Bear    : {yn(sig.tbr_bear)}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ LONG  signal : <b>{yn(sig.final_long)}</b>\n"
            f"✅ SHORT signal : <b>{yn(sig.final_short)}</b>\n"
            f"📌 Position: {position}"
        )
        self._send(msg)

    def send_partial_signal(self, direction: str, price: float, reason: str) -> None:
        """
        Fires when UT Bot + Hull align but the confluence condition (OB/FVG/TBR) is missing.
        Gives the user a heads-up that the market is setting up.
        """
        emoji = "🟡" if direction == "long" else "🟠"
        msg = (
            f"{emoji} <b>SETUP FORMING – {direction.upper()}</b>\n"
            f"Pair: <b>{self.symbol}</b> [{self.timeframe}]\n"
            f"⏰ {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💲 Price: <b>{price:.2f}</b>\n"
            f"📋 Status: {reason}\n"
            f"⚠️ Waiting for OB / FVG / 3BR confluence...\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"This is NOT a full signal – watch for entry!"
        )
        self._send(msg)

