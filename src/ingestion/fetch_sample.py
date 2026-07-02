
import yfinance as yf

# Deliberately mixed sample to expose data quirks:
#   .AX  -> ASX-listed (local, AUD)
#   plain -> US-listed (global, USD)
# IVV appears on both exchanges so we can compare the same fund cross-market.
SAMPLE_TICKERS = ["VAS.AX", "CBA.AX", "VOO", "AAPL", "IVV.AX", "IVV"]

# Fundamental fields we THINK we care about for feature engineering later.
# Part of this probe is checking which of these actually come back populated.
FIELDS_OF_INTEREST = [
    "symbol",
    "shortName",
    "quoteType",        # EQUITY vs ETF — matters for our categories
    "currency",
    "sector",
    "beta",             # risk metric we need for carousels
    "dividendYield",    
    "marketCap",
    "trailingPE",
]

def probe_ticker(symbol: str) -> None:
    """Fetch one ticker and print its raw fundamental fields + price shape."""
    print(f"\n{'=' * 60}")
    print(f"TICKER: {symbol}")
    print(f"{'=' * 60}")

    ticker = yf.Ticker(symbol)

    # --- Fundamentals (the .info dict) ---
    info = ticker.info
    print("  Fundamentals (.info):")
    for field in FIELDS_OF_INTEREST:
        # .get() so a missing field shows as None instead of crashing —
        # missing fields are themselves a finding we want to observe.
        value = info.get(field)
        print(f"    {field:<15} = {value!r}")

    # --- Price history (last 5 trading days) ---
    hist = ticker.history(period="5d")
    print(f"\n  Price history shape: {hist.shape}  (rows, columns)")
    print(f"  History columns: {list(hist.columns)}")
    if not hist.empty:
        latest_close = hist["Close"].iloc[-1]
        print(f"  Latest close: {latest_close:.2f} {info.get('currency')}")
    else:
        print("  WARNING: empty price history returned.")


def main() -> None:
    print("Probing sample tickers via yfinance...")
    print("(This is a read-only diagnostic — nothing is stored.)")

    for symbol in SAMPLE_TICKERS:
        try:
            probe_ticker(symbol)
        except Exception as exc:
            print(f"  ERROR fetching {symbol}: {type(exc).__name__}: {exc}")

    print(f"\n{'=' * 60}")
    print("Probe complete.")


if __name__ == "__main__":
    main()
