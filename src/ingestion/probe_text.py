"""
Probe: what TEXT does yfinance actually give us?

need to know:
  * does longBusinessSummary exist for equities? for ETFs?
  * how long is it, and how dense?
  * does it differ between an Australian and a US listing?
"""

import yfinance as yf

SAMPLES = ["AAPL", "CBA.AX", "VAS.AX", "IVV.AX", "TLT", "XLE"]

TEXT_FIELDS = ["longBusinessSummary", "industry", "sector", "website", "category", "fundFamily"]


def main():
    for symbol in SAMPLES:
        print(f"\n{'=' * 70}\n{symbol}\n{'=' * 70}")
        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            continue

        print(f"  quoteType: {info.get('quoteType')}")
        for field in TEXT_FIELDS:
            value = info.get(field)
            if field == "longBusinessSummary" and value:
                print(f"  {field}: {len(value)} chars, "
                      f"~{value.count('.')} sentences")
                print(f"    first 200: {value[:200]}...")
            else:
                print(f"  {field}: {value!r}")


if __name__ == "__main__":
    main()