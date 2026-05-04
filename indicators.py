# =============================================================================
# AETHER FLOW SYSTEM – Indicators Engine
# Converts Pine Script indicators to Python/pandas
# =============================================================================
# Covers:
#   1. UT Bot  (ATR Trailing Stop → Buy/Sell)
#   2. Hull Suite (HMA / EHMA / THMA trend filter)
#   3. Fair Value Gap (FVG) detection
#   4. Order Block (OB) detection via volume pivot
#   5. Three Bar Reversal (3BR) pattern
#   6. Reversal Signals (9-bar momentum counter)
# =============================================================================

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FVGZone:
    top: float
    bottom: float
    is_bull: bool
    bar_index: int
    mitigated: bool = False


@dataclass
class OrderBlock:
    top: float
    bottom: float
    avg: float
    is_bull: bool
    bar_index: int
    mitigated: bool = False


@dataclass
class SignalResult:
    """Final combined signal output for one candle."""
    bar_index: int
    timestamp: pd.Timestamp

    # UT Bot
    ut_buy: bool = False
    ut_sell: bool = False
    ut_trailing_stop: float = 0.0
    ut_trend: int = 0                   # 1=bull, -1=bear

    # Hull
    hull_bull: bool = False             # MHULL > SHULL
    hull_bear: bool = False

    # Three Bar Reversal
    tbr_bull: bool = False
    tbr_bear: bool = False

    # FVG
    in_bull_fvg: bool = False
    in_bear_fvg: bool = False
    nearest_bull_fvg: Optional[FVGZone] = None
    nearest_bear_fvg: Optional[FVGZone] = None

    # Order Blocks
    bull_ob_formed: bool = False
    bear_ob_formed: bool = False
    price_in_bull_ob: bool = False
    price_in_bear_ob: bool = False

    # Reversal Signal (9-bar counter)
    rs_bull_momentum: bool = False      # bull count hit 9
    rs_bear_momentum: bool = False

    # Combined final signal (all confirmations)
    final_long: bool = False
    final_short: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# 1. UT BOT  –  ATR Trailing Stop
# ─────────────────────────────────────────────────────────────────────────────

def compute_ut_bot(df: pd.DataFrame, key_value: float = 2, atr_period: int = 6) -> pd.DataFrame:
    """
    Replicates Pine Script UT Bot logic.
    
    Entry logic (from Pine):
        buy  = close > xATRTrailingStop AND crossover(ema(close,1), xATRTrailingStop)
        sell = close < xATRTrailingStop AND crossunder(ema(close,1), xATRTrailingStop)
    
    Returns df with columns:
        ut_atr, ut_nLoss, ut_trailing_stop, ut_pos, ut_buy, ut_sell,
        ut_bar_buy, ut_bar_sell
    """
    src = df["close"].values
    high = df["high"].values
    low  = df["low"].values

    n = len(df)

    # True Range → ATR
    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - np.roll(src, 1)),
            np.abs(low  - np.roll(src, 1))
        )
    )
    tr[0] = high[0] - low[0]

    # Wilder's ATR (RMA)
    atr = np.zeros(n)
    atr[atr_period - 1] = tr[:atr_period].mean()
    alpha = 1.0 / atr_period
    for i in range(atr_period, n):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]

    n_loss = key_value * atr

    # ATR Trailing Stop
    trailing = np.zeros(n)
    for i in range(1, n):
        prev = trailing[i - 1]
        c  = src[i]
        cp = src[i - 1]

        if c > prev and cp > prev:
            trailing[i] = max(prev, c - n_loss[i])
        elif c < prev and cp < prev:
            trailing[i] = min(prev, c + n_loss[i])
        elif c > prev:
            trailing[i] = c - n_loss[i]
        else:
            trailing[i] = c + n_loss[i]

    # Position direction
    pos = np.zeros(n, dtype=int)
    for i in range(1, n):
        if src[i - 1] < trailing[i - 1] and src[i] > trailing[i - 1]:
            pos[i] = 1
        elif src[i - 1] > trailing[i - 1] and src[i] < trailing[i - 1]:
            pos[i] = -1
        else:
            pos[i] = pos[i - 1]

    # EMA(close, 1) == close itself
    ema1 = src.copy()

    # Buy: close > trailing AND ema crosses over trailing
    above = ema1 > trailing
    above_prev = np.roll(above, 1)
    above_prev[0] = False
    crossover_up   = above & ~above_prev      # crossover
    crossover_down = ~above & above_prev      # crossunder

    ut_buy  = (src > trailing) & crossover_up
    ut_sell = (src < trailing) & crossover_down

    df = df.copy()
    df["ut_atr"]           = atr
    df["ut_nLoss"]         = n_loss
    df["ut_trailing_stop"] = trailing
    df["ut_pos"]           = pos
    df["ut_buy"]           = ut_buy
    df["ut_sell"]          = ut_sell
    df["ut_bar_buy"]       = src > trailing   # bar colored green
    df["ut_bar_sell"]      = src < trailing   # bar colored red

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. HULL SUITE  –  HMA / EHMA / THMA
# ─────────────────────────────────────────────────────────────────────────────

def _wma(series: np.ndarray, period: int) -> np.ndarray:
    weights = np.arange(1, period + 1, dtype=float)
    result  = np.full(len(series), np.nan)
    for i in range(period - 1, len(series)):
        result[i] = np.dot(series[i - period + 1 : i + 1], weights) / weights.sum()
    return result


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(series), np.nan)
    alpha  = 2.0 / (period + 1)
    start  = next((i for i, v in enumerate(series) if not np.isnan(v)), None)
    if start is None:
        return result
    result[start] = series[start]
    for i in range(start + 1, len(series)):
        result[i] = alpha * series[i] + (1 - alpha) * result[i - 1]
    return result


def _hma(src: np.ndarray, length: int) -> np.ndarray:
    half  = max(1, length // 2)
    sqrt_ = max(1, round(np.sqrt(length)))
    wma1  = _wma(src, half)
    wma2  = _wma(src, length)
    diff  = 2 * wma1 - wma2
    return _wma(diff, sqrt_)


def _ehma(src: np.ndarray, length: int) -> np.ndarray:
    half  = max(1, length // 2)
    sqrt_ = max(1, round(np.sqrt(length)))
    ema1  = _ema(src, half)
    ema2  = _ema(src, length)
    diff  = 2 * ema1 - ema2
    return _ema(diff, sqrt_)


def _thma(src: np.ndarray, length: int) -> np.ndarray:
    l3 = max(1, length // 3)
    l2 = max(1, length // 2)
    w1 = _wma(src, l3)
    w2 = _wma(src, l2)
    w3 = _wma(src, length)
    diff = 3 * w1 - w2 - w3
    return _wma(diff, length)


def compute_hull_suite(
    df: pd.DataFrame,
    length: int = 55,
    mode: str = "HMA",
    mult: float = 1.0,
) -> pd.DataFrame:
    """
    Computes Hull Suite.
    MHULL = hull[0],  SHULL = hull[2]
    hull_bull = MHULL > SHULL  (trending up)
    hull_bear = MHULL < SHULL
    """
    src = df["close"].values
    real_len = max(1, int(length * mult))

    if mode == "HMA":
        hull = _hma(src, real_len)
    elif mode == "EHMA":
        hull = _ehma(src, real_len)
    elif mode == "THMA":
        hull = _thma(src, real_len)
    else:
        hull = _hma(src, real_len)

    mhull = hull.copy()
    shull = np.roll(hull, 2)
    shull[:2] = np.nan

    df = df.copy()
    df["hull"]      = hull
    df["hull_mhull"] = mhull
    df["hull_shull"] = shull
    df["hull_bull"] = mhull > shull
    df["hull_bear"] = mhull < shull

    # Crossover signals (for alerts)
    hull_up   = df["hull_bull"].values
    hull_up_p = np.roll(hull_up, 1)
    hull_up_p[0] = False
    df["hull_cross_up"]   = hull_up  & ~hull_up_p
    df["hull_cross_down"] = ~hull_up & hull_up_p

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 3. FAIR VALUE GAP (FVG) DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def compute_fvg(
    df: pd.DataFrame,
    threshold_pct: float = 0.0,
) -> tuple[pd.DataFrame, list[FVGZone]]:
    """
    Detects Fair Value Gaps.
    Bull FVG: low[i] > high[i-2] AND close[i-1] > high[i-2]
    Bear FVG: high[i] < low[i-2] AND close[i-1] < low[i-2]

    Tracks mitigation: bull FVG mitigated when close < fvg.bottom
                       bear FVG mitigated when close > fvg.top
    """
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    n      = len(df)

    fvg_zones: list[FVGZone] = []
    bull_fvg_flags = np.zeros(n, dtype=bool)
    bear_fvg_flags = np.zeros(n, dtype=bool)
    in_bull = np.zeros(n, dtype=bool)
    in_bear = np.zeros(n, dtype=bool)

    active_bull: list[FVGZone] = []
    active_bear: list[FVGZone] = []

    for i in range(2, n):
        threshold = threshold_pct / 100.0

        # Detect new FVGs
        bull_gap = lows[i] - highs[i - 2]
        bear_gap = lows[i - 2] - highs[i]

        if (lows[i] > highs[i - 2] and
                closes[i - 1] > highs[i - 2] and
                (bull_gap / highs[i - 2]) > threshold):
            z = FVGZone(top=lows[i], bottom=highs[i - 2], is_bull=True, bar_index=i)
            fvg_zones.append(z)
            active_bull.append(z)
            bull_fvg_flags[i] = True

        elif (highs[i] < lows[i - 2] and
              closes[i - 1] < lows[i - 2] and
              (bear_gap / highs[i]) > threshold):
            z = FVGZone(top=lows[i - 2], bottom=highs[i], is_bull=False, bar_index=i)
            fvg_zones.append(z)
            active_bear.append(z)
            bear_fvg_flags[i] = True

        # Check mitigation
        still_bull = []
        for z in active_bull:
            if closes[i] < z.bottom:
                z.mitigated = True
            else:
                still_bull.append(z)
                if z.bottom <= closes[i] <= z.top:
                    in_bull[i] = True
        active_bull = still_bull

        still_bear = []
        for z in active_bear:
            if closes[i] > z.top:
                z.mitigated = True
            else:
                still_bear.append(z)
                if z.bottom <= closes[i] <= z.top:
                    in_bear[i] = True
        active_bear = still_bear

    df = df.copy()
    df["fvg_bull"]    = bull_fvg_flags
    df["fvg_bear"]    = bear_fvg_flags
    df["in_bull_fvg"] = in_bull
    df["in_bear_fvg"] = in_bear

    return df, fvg_zones


# ─────────────────────────────────────────────────────────────────────────────
# 4. ORDER BLOCKS  –  Volume Pivot Detection (LuxAlgo style)
# ─────────────────────────────────────────────────────────────────────────────

def compute_order_blocks(
    df: pd.DataFrame,
    pivot_length: int = 5,
    bull_count: int = 3,
    bear_count: int = 3,
    mitigation: str = "Wick",       # "Wick" or "Close"
) -> tuple[pd.DataFrame, list[OrderBlock]]:
    """
    LuxAlgo Order Block logic:
    - Detect volume pivot highs
    - os=1 (bearish pivot → bullish OB candidate when os was 1)
    - os=0 (bullish pivot → bearish OB candidate when os was 0)
    Mitigation: wick = price touches OB edge; close = close breaches OB
    """
    highs   = df["high"].values
    lows    = df["low"].values
    closes  = df["close"].values
    volumes = df["volume"].values
    hl2     = (highs + lows) / 2.0
    n       = len(df)
    L       = pivot_length

    ob_list: list[OrderBlock] = []
    bull_ob_flags = np.zeros(n, dtype=bool)
    bear_ob_flags = np.zeros(n, dtype=bool)
    price_in_bull = np.zeros(n, dtype=bool)
    price_in_bear = np.zeros(n, dtype=bool)

    # Rolling highest/lowest
    rolling_high = pd.Series(highs).rolling(L).max().values
    rolling_low  = pd.Series(lows).rolling(L).min().values

    # os: market direction based on recent breakout
    os = np.zeros(n, dtype=int)
    for i in range(1, n):
        if highs[i - L] > rolling_high[i] if i >= L else False:
            os[i] = 0
        elif lows[i - L] < rolling_low[i] if i >= L else False:
            os[i] = 1
        else:
            os[i] = os[i - 1]

    # Volume pivot high detection
    def is_pivot_high_vol(i):
        if i < L or i + L >= n:
            return False
        center_vol = volumes[i]
        left  = volumes[max(0, i - L):i]
        right = volumes[i + 1:i + L + 1]
        return center_vol > left.max() and center_vol > right.max()

    active_bull_obs: list[OrderBlock] = []
    active_bear_obs: list[OrderBlock] = []

    for i in range(L, n - L):
        if is_pivot_high_vol(i):
            # Bullish OB: pivot when os=1 (recent downswing)
            if os[i] == 1:
                top    = hl2[i]
                bottom = lows[i]
                avg    = (top + bottom) / 2
                ob     = OrderBlock(top=top, bottom=bottom, avg=avg,
                                    is_bull=True, bar_index=i)
                ob_list.append(ob)
                active_bull_obs.append(ob)
                bull_ob_flags[i] = True
                # Keep only bull_count most recent
                if len(active_bull_obs) > bull_count:
                    active_bull_obs.pop(0)

            # Bearish OB: pivot when os=0 (recent upswing)
            elif os[i] == 0:
                top    = highs[i]
                bottom = hl2[i]
                avg    = (top + bottom) / 2
                ob     = OrderBlock(top=top, bottom=bottom, avg=avg,
                                    is_bull=False, bar_index=i)
                ob_list.append(ob)
                active_bear_obs.append(ob)
                bear_ob_flags[i] = True
                if len(active_bear_obs) > bear_count:
                    active_bear_obs.pop(0)

    # Mitigation + price-in-zone check (forward pass)
    for i in range(n):
        c = closes[i]
        lo = lows[i]
        hi = highs[i]

        mval_bull = lo if mitigation == "Wick" else c
        mval_bear = hi if mitigation == "Wick" else c

        for ob in active_bull_obs:
            if not ob.mitigated:
                if mval_bull < ob.bottom:
                    ob.mitigated = True
                elif ob.bottom <= c <= ob.top:
                    price_in_bull[i] = True

        for ob in active_bear_obs:
            if not ob.mitigated:
                if mval_bear > ob.top:
                    ob.mitigated = True
                elif ob.bottom <= c <= ob.top:
                    price_in_bear[i] = True

    df = df.copy()
    df["ob_bull_formed"]   = bull_ob_flags
    df["ob_bear_formed"]   = bear_ob_flags
    df["price_in_bull_ob"] = price_in_bull
    df["price_in_bear_ob"] = price_in_bear

    return df, ob_list


# ─────────────────────────────────────────────────────────────────────────────
# 5. THREE BAR REVERSAL (3BR)
# ─────────────────────────────────────────────────────────────────────────────

def compute_three_bar_reversal(
    df: pd.DataFrame,
    pattern_type: str = "All",          # "Normal", "Enhanced", "All"
    trend_filter: bool = False,         # If True uses Hull for filtering
) -> pd.DataFrame:
    """
    Pine Script 3BR logic:

    Bullish:
        close[2] < open[2]   (bar-2 bearish)
        low[1]  < low[2]     (bar-1 lower low)
        high[1] < high[2]    (bar-1 lower high)
        close[1] < open[1]   (bar-1 bearish)
        close > open         (current bullish)
        high > high[2]       (current breaks bar-2 high)

    Bearish:
        close[2] > open[2]   (bar-2 bullish)
        high[1] > high[2]    (bar-1 higher high)
        low[1]  > low[2]     (bar-1 higher low)
        close[1] > open[1]   (bar-1 bullish)
        close < open         (current bearish)
        low < low[2]         (current breaks bar-2 low)
    """
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df)

    bull_3br = np.zeros(n, dtype=bool)
    bear_3br = np.zeros(n, dtype=bool)

    for i in range(2, n):
        # Bullish 3BR
        base_bull = (
            c[i - 2] < o[i - 2] and
            l[i - 1] < l[i - 2] and
            h[i - 1] < h[i - 2] and
            c[i - 1] < o[i - 1] and
            c[i] > o[i] and
            h[i] > h[i - 2]
        )

        if base_bull:
            if pattern_type == "All":
                bull_3br[i] = True
            elif pattern_type == "Enhanced" and c[i] > h[i - 2]:
                bull_3br[i] = True
            elif pattern_type == "Normal" and c[i] <= h[i - 2]:
                bull_3br[i] = True

        # Bearish 3BR
        base_bear = (
            c[i - 2] > o[i - 2] and
            h[i - 1] > h[i - 2] and
            l[i - 1] > l[i - 2] and
            c[i - 1] > o[i - 1] and
            c[i] < o[i] and
            l[i] < l[i - 2]
        )

        if base_bear:
            if pattern_type == "All":
                bear_3br[i] = True
            elif pattern_type == "Enhanced" and c[i] < l[i - 2]:
                bear_3br[i] = True
            elif pattern_type == "Normal" and c[i] >= l[i - 2]:
                bear_3br[i] = True

    df = df.copy()
    df["tbr_bull"] = bull_3br
    df["tbr_bear"] = bear_3br

    return df


# ─────────────────────────────────────────────────────────────────────────────
# 6. REVERSAL SIGNAL  –  9-bar momentum counter
# ─────────────────────────────────────────────────────────────────────────────

def compute_reversal_signal(
    df: pd.DataFrame,
    count_target: int = 9,
) -> pd.DataFrame:
    """
    Pine Script reversal signal:
        con = close < close[4]   → bearish pressure
        bull_count increments while con is True, resets otherwise
        bear_count increments while con is False, resets otherwise
        Signal fires when count reaches 9
    """
    closes = df["close"].values
    n      = len(df)

    bull_count = np.zeros(n, dtype=int)
    bear_count = np.zeros(n, dtype=int)
    rs_bull    = np.zeros(n, dtype=bool)
    rs_bear    = np.zeros(n, dtype=bool)

    for i in range(4, n):
        con = closes[i] < closes[i - 4]   # bearish condition (close < close[4])

        if con:
            bull_count[i] = bull_count[i - 1] + 1 if bull_count[i - 1] < count_target else 1
            bear_count[i] = 0
        else:
            bear_count[i] = bear_count[i - 1] + 1 if bear_count[i - 1] < count_target else 1
            bull_count[i] = 0

        rs_bull[i] = bull_count[i] == count_target   # 9 consecutive closes < close[4]
        rs_bear[i] = bear_count[i] == count_target   # 9 consecutive closes >= close[4]

    df = df.copy()
    df["rs_bull_count"] = bull_count
    df["rs_bear_count"] = bear_count
    df["rs_bull"]       = rs_bull       # Bullish momentum exhaustion signal
    df["rs_bear"]       = rs_bear       # Bearish momentum exhaustion signal

    return df


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION – Run all indicators
# ─────────────────────────────────────────────────────────────────────────────

def run_all_indicators(df: pd.DataFrame, cfg) -> pd.DataFrame:
    """
    Runs every indicator and returns enriched DataFrame.
    Expects df columns: open, high, low, close, volume, timestamp
    """
    df = compute_ut_bot(df, cfg.UT_KEY_VALUE, cfg.UT_ATR_PERIOD)
    df = compute_hull_suite(df, cfg.HULL_LENGTH, cfg.HULL_MODE, cfg.HULL_MULT)
    df, _ = compute_fvg(df, cfg.FVG_THRESHOLD_PCT)
    df, _ = compute_order_blocks(df, cfg.OB_PIVOT_LENGTH,
                                  cfg.OB_BULL_COUNT, cfg.OB_BEAR_COUNT)
    df = compute_three_bar_reversal(df, cfg.TBR_PATTERN_TYPE)
    df = compute_reversal_signal(df, cfg.RS_COUNT_TARGET)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL GENERATOR  –  Combine indicators into trade signals
# ─────────────────────────────────────────────────────────────────────────────

def generate_signals(df: pd.DataFrame) -> list[SignalResult]:
    """
    Combines all indicator columns into final long/short signals.

    Long entry requires:
        • UT Bot buy signal           (primary trigger)
        • Hull Suite bullish          (trend filter)
        • Optional: TBR bullish pattern OR price in bull OB / FVG

    Short entry requires:
        • UT Bot sell signal          (primary trigger)
        • Hull Suite bearish          (trend filter)
        • Optional: TBR bearish pattern OR price in bear OB / FVG
    """
    signals = []

    def _get(row, name, default):
        """Safe column read – pandas Series doesn't have .get()."""
        return row[name] if name in row.index else default

    for i, row in df.iterrows():
        idx = df.index.get_loc(i)
        sig = SignalResult(
            bar_index  = idx,
            timestamp  = i,

            ut_buy             = bool(_get(row, "ut_buy",             False)),
            ut_sell            = bool(_get(row, "ut_sell",            False)),
            ut_trailing_stop   = float(_get(row, "ut_trailing_stop",  0.0)),
            ut_trend           = int(_get(row, "ut_pos",              0)),

            hull_bull          = bool(_get(row, "hull_bull",          False)),
            hull_bear          = bool(_get(row, "hull_bear",          False)),

            tbr_bull           = bool(_get(row, "tbr_bull",           False)),
            tbr_bear           = bool(_get(row, "tbr_bear",           False)),

            in_bull_fvg        = bool(_get(row, "in_bull_fvg",        False)),
            in_bear_fvg        = bool(_get(row, "in_bear_fvg",        False)),

            bull_ob_formed     = bool(_get(row, "ob_bull_formed",     False)),
            bear_ob_formed     = bool(_get(row, "ob_bear_formed",     False)),
            price_in_bull_ob   = bool(_get(row, "price_in_bull_ob",   False)),
            price_in_bear_ob   = bool(_get(row, "price_in_bear_ob",   False)),

            rs_bull_momentum   = bool(_get(row, "rs_bull",            False)),
            rs_bear_momentum   = bool(_get(row, "rs_bear",            False)),
        )

        # ── Long Condition ──────────────────────────────────────────────────
        # Primary: UT buy + Hull bullish
        # Bonus confluence: 3BR bull OR OB OR FVG
        long_primary     = sig.ut_buy and sig.hull_bull
        long_confluence  = sig.tbr_bull or sig.price_in_bull_ob or sig.in_bull_fvg
        sig.final_long   = long_primary and long_confluence

        # ── Short Condition ─────────────────────────────────────────────────
        short_primary    = sig.ut_sell and sig.hull_bear
        short_confluence = sig.tbr_bear or sig.price_in_bear_ob or sig.in_bear_fvg
        sig.final_short  = short_primary and short_confluence

        signals.append(sig)

    return signals

