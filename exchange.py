# =============================================================================
# AETHER FLOW SYSTEM – Exchange Connector (Delta Exchange via CCXT)
# =============================================================================

import ccxt
import pandas as pd
import time
import logging
from typing import Optional

logger = logging.getLogger("aether.exchange")


class DeltaExchangeConnector:
    """
    Handles all communication with Delta Exchange via CCXT.
    Covers: OHLCV fetch, balance, order placement, position management.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self.exchange = self._init_exchange()
        # Auto-resolve the correct symbol for Delta Exchange
        self.symbol = self.resolve_symbol(cfg.SYMBOL)
        # Update the config symbol so alerts/orders use the resolved symbol
        cfg.SYMBOL = self.symbol

    # ─────────────────────────────────────────────────────────────────────────
    # INIT
    # ─────────────────────────────────────────────────────────────────────────

    def _init_exchange(self) -> ccxt.Exchange:
        exchange = ccxt.delta({
            "apiKey":           self.cfg.API_KEY,
            "secret":           self.cfg.API_SECRET,
            "enableRateLimit":  True,
            "options": {
                "defaultType": "future",   # Delta Exchange is futures-first
            },
        })

        if self.cfg.TESTNET:
            # Delta Exchange testnet
            exchange.set_sandbox_mode(True)
            logger.info("⚠️  Running in TESTNET mode")

        try:
            exchange.load_markets()
            logger.info(f"✅ Connected to Delta Exchange | {len(exchange.markets)} markets loaded")
        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            raise

        return exchange

    def resolve_symbol(self, preferred: str) -> str:
        """
        Auto-discovers the correct CCXT symbol for Delta Exchange.
        Delta Exchange uses perpetual notation e.g. BTC/USDT:USDT.
        Falls back through a list of candidates until one with OHLCV data is found.
        """
        candidates = [
            preferred,
            "BTC/USDT:USDT",
            "BTCUSDT",
            "BTC/USD:BTC",
            "BTC/USDT",
        ]
        # Try each candidate
        for sym in candidates:
            if sym in self.exchange.markets:
                # Quick data probe
                try:
                    raw = self.exchange.fetch_ohlcv(sym, "15m", limit=5)
                    if raw and len(raw) > 0:
                        logger.info(f"✅ Symbol resolved: {sym}")
                        return sym
                except Exception:
                    pass
        # Log all available perpetuals to help user pick
        perps = [s for s in self.exchange.markets if ":" in s and "BTC" in s]
        logger.warning(f"⚠️  Could not auto-resolve BTC symbol. Available: {perps[:10]}")
        return preferred

    # ─────────────────────────────────────────────────────────────────────────
    # OHLCV DATA
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_ohlcv(
        self,
        symbol: str = None,
        timeframe: str = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """
        Fetches OHLCV candles and returns a clean DataFrame.
        Columns: timestamp, open, high, low, close, volume
        """
        symbol    = symbol    or self.cfg.SYMBOL
        timeframe = timeframe or self.cfg.TIMEFRAME

        try:
            raw = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except ccxt.NetworkError as e:
            logger.error(f"Network error fetching OHLCV: {e}")
            raise
        except ccxt.ExchangeError as e:
            logger.error(f"Exchange error fetching OHLCV: {e}")
            raise

        if not raw or len(raw) == 0:
            raise ValueError(
                f"❌ No OHLCV data returned for {symbol} [{timeframe}]. "
                f"The symbol may be wrong or inactive on Delta Exchange. "
                f"Check config.py SYMBOL setting."
            )

        df = pd.DataFrame(raw, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
        df = df.drop(columns=["timestamp_ms"])
        df = df.set_index("timestamp")

        # Remove the last (incomplete) candle
        if len(df) > 1:
            df = df.iloc[:-1]

        logger.info(f"📊 Fetched {len(df)} candles for {symbol} [{timeframe}]")
        return df

    # ─────────────────────────────────────────────────────────────────────────
    # ACCOUNT
    # ─────────────────────────────────────────────────────────────────────────

    def get_balance(self, currency: str = "USDT") -> float:
        try:
            balance = self.exchange.fetch_balance()
            free = balance.get("free", {}).get(currency, 0.0)
            logger.info(f"💰 Balance: {free:.2f} {currency}")
            return float(free)
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            return 0.0

    def get_position(self, symbol: str = None) -> Optional[dict]:
        """Returns open position for symbol, or None."""
        symbol = symbol or self.cfg.SYMBOL
        try:
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                if pos.get("contracts", 0) != 0:
                    return pos
        except Exception as e:
            logger.error(f"Failed to fetch position: {e}")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # ORDER SIZING
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss_price: float,
        balance: float = None,
    ) -> float:
        """
        Risk-based position sizing:
            size = (balance * risk_pct) / |entry - stop|
        Returns quantity in base currency.
        """
        if balance is None:
            balance = self.get_balance()

        risk_amount    = balance * self.cfg.RISK_PER_TRADE
        price_distance = abs(entry_price - stop_loss_price)

        if price_distance == 0:
            logger.warning("Stop loss equals entry – defaulting to 0 size")
            return 0.0

        raw_size = risk_amount / price_distance

        # Apply leverage
        raw_size *= self.cfg.LEVERAGE

        # Round to exchange precision
        try:
            market   = self.exchange.market(self.cfg.SYMBOL)
            raw_size = self.exchange.amount_to_precision(self.cfg.SYMBOL, raw_size)
            raw_size = float(raw_size)
        except Exception:
            raw_size = round(raw_size, 4)

        logger.info(
            f"📐 Size calc: balance={balance:.2f}, risk={risk_amount:.2f}, "
            f"distance={price_distance:.4f}, size={raw_size}"
        )
        return raw_size

    # ─────────────────────────────────────────────────────────────────────────
    # ORDER PLACEMENT
    # ─────────────────────────────────────────────────────────────────────────

    def place_market_order(
        self,
        side: str,          # "buy" or "sell"
        amount: float,
        stop_loss: float,
        take_profit: float,
        symbol: str = None,
    ) -> Optional[dict]:
        """
        Places a market order with stop loss and take profit.
        Returns the order dict or None on failure.
        """
        symbol = symbol or self.cfg.SYMBOL

        try:
            logger.info(
                f"📤 Placing {side.upper()} order | symbol={symbol} "
                f"amount={amount} | SL={stop_loss:.4f} TP={take_profit:.4f}"
            )

            # Main market order
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount,
            )
            logger.info(f"✅ Order filled: {order.get('id')} @ {order.get('average', 'market')}")

            # Stop Loss (opposite side, reduce-only)
            sl_side = "sell" if side == "buy" else "buy"
            try:
                sl_order = self.exchange.create_order(
                    symbol=symbol,
                    type="stop_market",
                    side=sl_side,
                    amount=amount,
                    params={
                        "stopPrice":    stop_loss,
                        "reduceOnly":   True,
                        "timeInForce":  "GTC",
                    },
                )
                logger.info(f"🛡️  Stop Loss placed @ {stop_loss}")
            except Exception as e:
                logger.warning(f"SL order failed (may need manual): {e}")

            # Take Profit (opposite side, reduce-only)
            try:
                tp_order = self.exchange.create_order(
                    symbol=symbol,
                    type="take_profit_market",
                    side=sl_side,
                    amount=amount,
                    params={
                        "stopPrice":    take_profit,
                        "reduceOnly":   True,
                        "timeInForce":  "GTC",
                    },
                )
                logger.info(f"🎯 Take Profit placed @ {take_profit}")
            except Exception as e:
                logger.warning(f"TP order failed (may need manual): {e}")

            return order

        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds: {e}")
        except ccxt.InvalidOrder as e:
            logger.error(f"❌ Invalid order: {e}")
        except Exception as e:
            logger.error(f"❌ Order failed: {e}")

        return None

    def cancel_all_orders(self, symbol: str = None):
        """Cancels all open orders for the symbol."""
        symbol = symbol or self.cfg.SYMBOL
        try:
            cancelled = self.exchange.cancel_all_orders(symbol)
            logger.info(f"🗑️  Cancelled {len(cancelled)} orders for {symbol}")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")

    def close_position(self, symbol: str = None):
        """Market-closes any open position."""
        symbol   = symbol or self.cfg.SYMBOL
        position = self.get_position(symbol)

        if position is None:
            logger.info("No open position to close.")
            return

        side   = position.get("side", "")          # "long" or "short"
        amount = abs(float(position.get("contracts", 0)))
        close_side = "sell" if side == "long" else "buy"

        try:
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=close_side,
                amount=amount,
                params={"reduceOnly": True},
            )
            logger.info(f"🔒 Position closed: {order.get('id')}")
        except Exception as e:
            logger.error(f"Failed to close position: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # UTILITY
    # ─────────────────────────────────────────────────────────────────────────

    def get_ticker(self, symbol: str = None) -> float:
        """Returns last traded price."""
        symbol = symbol or self.cfg.SYMBOL
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker["last"])
        except Exception as e:
            logger.error(f"Failed to fetch ticker: {e}")
            return 0.0

    def wait_for_candle_close(self, timeframe: str = None):
        """Sleeps until the next candle closes."""
        timeframe = timeframe or self.cfg.TIMEFRAME

        tf_seconds = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900,
            "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400,
        }
        seconds = tf_seconds.get(timeframe, 900)
        now     = time.time()
        sleep   = seconds - (now % seconds)
        logger.info(f"⏳ Waiting {sleep:.0f}s for next {timeframe} candle...")
        time.sleep(sleep + 2)   # +2s buffer for candle to publish
