"""
Curated asset metadata overrides.

"""

# symbol -> curated facts we can't reliably get from yfinance
ASSET_OVERRIDES: dict[str, dict[str, str]] = {

    # ASX-listed, US underlying
    "IVV.AX":  {"underlying_market": "US"},      # tracks S&P 500
    "IHVV.AX": {"underlying_market": "US"},      # S&P 500, AUD-hedged
    "NDQ.AX":  {"underlying_market": "US"},      # tracks NASDAQ 100
    "VTS.AX":  {"underlying_market": "US"},      # US total market

    # ASX-listed, GLOBAL underlying
    "VGS.AX":  {"underlying_market": "GLOBAL"},  # MSCI World ex-Australia
    "IOO.AX":  {"underlying_market": "GLOBAL"},  # Global 100
    "VEU.AX":  {"underlying_market": "GLOBAL"},  # All-World ex-US
    "VGE.AX":  {"underlying_market": "GLOBAL"},  # Emerging markets

    # US-listed, GLOBAL underlying
    "VXUS":    {"underlying_market": "GLOBAL"},  # Total international
    "VEA":     {"underlying_market": "GLOBAL"},  # Developed markets
    "VWO":     {"underlying_market": "GLOBAL"},  # Emerging markets
}


def get_override(symbol: str) -> dict[str, str]:
    """Return curated overrides for a symbol, or an empty dict if none exist."""
    return ASSET_OVERRIDES.get(symbol, {})