"""
Curated asset metadata overrides.

"""

# symbol -> curated facts we can't reliably get from yfinance
ASSET_OVERRIDES: dict[str, dict[str, str]] = {
    # ASX-listed but US underlying exposure — the key edge case.
    "IVV.AX": {"underlying_market": "US"},
    # ASX-listed, genuinely Australian exposure (S&P/ASX 300).
    "VAS.AX": {"underlying_market": "AU"},
    # ASX-listed single stock, Australian company.
    "CBA.AX": {"underlying_market": "AU"},
    # US-listed, US exposure.
    "VOO": {"underlying_market": "US"},
    "AAPL": {"underlying_market": "US"},
    "IVV": {"underlying_market": "US"},
}


def get_override(symbol: str) -> dict[str, str]:
    """Return curated overrides for a symbol, or an empty dict if none exist."""
    return ASSET_OVERRIDES.get(symbol, {})