"""
Step 4: Validation & Normalization layer.

"""

from dataclasses import dataclass, field

from src.processing.asset_metadata import get_override


# --- Tunable guard thresholds (kept as named constants so they're visible) ---

DIVIDEND_YIELD_SUSPECT_HIGH = 20.0

DIVIDEND_YIELD_SUSPECT_LOW = 0.05


class AssetValidationError(Exception):
    """Raised when a raw record is missing data essential to be usable."""


@dataclass
class NormalizedAsset:
    """A clean, typed, trustworthy asset record. The contract for everything
    downstream (storage, ML, API)."""
    symbol: str
    short_name: str
    quote_type: str            # 'ETF' | 'EQUITY'
    currency: str              # 'AUD' | 'USD'
    listed_exchange: str       # 'ASX' | 'US'
    underlying_market: str     # 'AU' | 'US' | 'GLOBAL'
    latest_close: float
    sector: str | None = None
    beta: float | None = None
    dividend_yield: float | None = None
    market_cap: int | None = None
    trailing_pe: float | None = None
    data_warnings: list[str] = field(default_factory=list)


def _derive_listed_exchange(symbol: str) -> str:
    """ASX tickers carry the '.AX' suffix; everything else we treat as US for
    now (our universe is ASX + US only). Kept simple and explicit."""
    return "ASX" if symbol.upper().endswith(".AX") else "US"


def _derive_underlying_market(symbol: str, listed_exchange: str) -> str:
    """Prefer the curated override; otherwise fall back to a reasonable guess
    from the listing venue. The fallback is intentionally conservative."""
    override = get_override(symbol)
    if "underlying_market" in override:
        return override["underlying_market"]
    # Fallback: assume exposure matches the listing venue. This is the naive
    # assumption we KNOW can be wrong (that's why the override map exists), so
    # any asset relying on the fallback is a candidate for manual review.
    return "AU" if listed_exchange == "ASX" else "US"


def _check_dividend_yield(raw_value, warnings: list[str]) -> float | None:
    """WARN-ONLY: we never change the value, only flag it when it looks off."""
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        warnings.append(f"dividend_yield not numeric: {raw_value!r}; dropped")
        return None

    if value < 0:
        warnings.append(f"dividend_yield negative ({value}); kept but suspect")
    elif value > DIVIDEND_YIELD_SUSPECT_HIGH:
        warnings.append(
            f"dividend_yield {value} exceeds {DIVIDEND_YIELD_SUSPECT_HIGH}; "
            f"possible unit error (raw fraction * 100?); kept unaltered"
        )
    elif 0 < value < DIVIDEND_YIELD_SUSPECT_LOW:
        warnings.append(
            f"dividend_yield {value} is very low; possible decimal-form slip "
            f"(0.03 vs 3.0?); kept unaltered"
        )
    return value


def normalize_asset(raw: dict) -> NormalizedAsset:
    """Convert one raw yfinance .info-style dict (plus a 'latest_close' we
    attach during ingestion) into a clean NormalizedAsset.

    Raises AssetValidationError if the record lacks essentials.
    """
    warnings: list[str] = []

    symbol = raw.get("symbol")
    if not symbol:
        raise AssetValidationError("record has no 'symbol'")

    latest_close = raw.get("latest_close")
    if latest_close is None:
        raise AssetValidationError(f"{symbol}: no latest_close price available")
    try:
        latest_close = float(latest_close)
    except (TypeError, ValueError):
        raise AssetValidationError(
            f"{symbol}: latest_close not numeric ({latest_close!r})"
        )

    # quote_type: prefer a curated override, 
    # since yfinance misclassifies some ETFs as EQUITY (confirmed: VTS.AX, VEU.AX).
    # We correct known-bad vendor data rather than propagate it. the override map's purpose is exactly this.
    override = get_override(symbol)
    vendor_quote_type = raw.get("quoteType") or "UNKNOWN"
    quote_type = override.get("quote_type", vendor_quote_type)

    if "quote_type" in override and override["quote_type"] != vendor_quote_type:
        warnings.append(
            f"quote_type corrected: vendor said '{vendor_quote_type}', "
            f"override says '{quote_type}'"
        )
    if quote_type == "UNKNOWN":
        warnings.append("quoteType missing; downstream sector/beta logic may skip")

    currency = raw.get("currency")
    if not currency:
        warnings.append("currency missing; cross-market comparison unreliable")
        currency = "UNKNOWN"

    listed_exchange = _derive_listed_exchange(symbol)
    underlying_market = _derive_underlying_market(symbol, listed_exchange)
    if not get_override(symbol):
        warnings.append(
            f"no curated override for {symbol}; underlying_market inferred as "
            f"'{underlying_market}' from listing venue (review candidate)"
        )

    # --- quoteType-aware handling of legitimately-null fields ---
    sector = raw.get("sector")
    if sector is None and quote_type == "EQUITY":
        # A stock with no sector is odd enough to note; an ETF without one is normal.
        warnings.append("EQUITY missing sector (unexpected)")

    beta = raw.get("beta")
    if beta is not None:
        try:
            beta = float(beta)
        except (TypeError, ValueError):
            warnings.append(f"beta not numeric ({beta!r}); dropped")
            beta = None
    # ETF beta being None is EXPECTED (confirmed in probe) — no warning.

    market_cap = raw.get("marketCap")
    if market_cap is not None:
        try:
            market_cap = int(market_cap)
        except (TypeError, ValueError):
            warnings.append(f"marketCap not numeric ({market_cap!r}); dropped")
            market_cap = None

    trailing_pe = raw.get("trailingPE")
    if trailing_pe is not None:
        try:
            trailing_pe = float(trailing_pe)
        except (TypeError, ValueError):
            warnings.append(f"trailingPE not numeric ({trailing_pe!r}); dropped")
            trailing_pe = None

    dividend_yield = _check_dividend_yield(raw.get("dividendYield"), warnings)

    return NormalizedAsset(
        symbol=symbol,
        short_name=raw.get("shortName") or symbol,
        quote_type=quote_type,
        currency=currency,
        listed_exchange=listed_exchange,
        underlying_market=underlying_market,
        latest_close=latest_close,
        sector=sector,
        beta=beta,
        dividend_yield=dividend_yield,
        market_cap=market_cap,
        trailing_pe=trailing_pe,
        data_warnings=warnings,
    )


def _self_test() -> None:
    """Runs the normalizer against the real probe data so we can see it work
    without hitting the network. These dicts mirror our Step 3 output."""
    samples = [
        {  # ETF, ASX-listed, AU exposure — clean
            "symbol": "VAS.AX", "shortName": "V300AEQ ETF UNITS [VAS]",
            "quoteType": "ETF", "currency": "AUD", "sector": None,
            "beta": None, "dividendYield": 3.14, "marketCap": None,
            "trailingPE": 20.696411, "latest_close": 108.16,
        },
        {  # EQUITY, ASX-listed, AU — full fundamentals
            "symbol": "CBA.AX", "shortName": "CWLTH BANK FPO [CBA]",
            "quoteType": "EQUITY", "currency": "AUD",
            "sector": "Financial Services", "beta": 0.802,
            "dividendYield": 3.07, "marketCap": 269446021120,
            "trailingPE": 25.906754, "latest_close": 161.14,
        },
        {  # ETF, ASX-listed, but US underlying — the edge case
            "symbol": "IVV.AX", "shortName": "ISCS&P500 ETF UNITS [IVV]",
            "quoteType": "ETF", "currency": "AUD", "sector": None,
            "beta": None, "dividendYield": 0.97, "marketCap": None,
            "trailingPE": 28.1143, "latest_close": 72.14,
        },
    ]
    for raw in samples:
        asset = normalize_asset(raw)
        print(f"\n{asset.symbol}: {asset.short_name}")
        print(f"  type={asset.quote_type} currency={asset.currency} "
              f"listed={asset.listed_exchange} underlying={asset.underlying_market}")
        print(f"  close={asset.latest_close} div_yield={asset.dividend_yield} "
              f"beta={asset.beta} sector={asset.sector}")
        if asset.data_warnings:
            print("  WARNINGS:")
            for w in asset.data_warnings:
                print(f"    - {w}")
        else:
            print("  (no warnings)")


if __name__ == "__main__":
    _self_test()