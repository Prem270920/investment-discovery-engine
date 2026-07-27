"""
Tests for the validation and normalization layer.

Most of these encode a bug that actually happened. The override-map tests in
particular guard the project's most important data decision: that where an asset
is LISTED is not the same as what it HOLDS. A run where the override map failed
to load silently benchmarked a NASDAQ tracker against the ASX 200.
"""

import pytest

from src.processing.normalize import AssetValidationError, normalize_asset


def raw(**overrides):
    """A valid yfinance-shaped record, overridable per test."""
    base = {
        "symbol": "TEST.AX",
        "shortName": "Test Asset",
        "quoteType": "ETF",
        "currency": "AUD",
        "sector": None,
        "beta": None,
        "dividendYield": 3.0,
        "marketCap": None,
        "trailingPE": 20.0,
        "latest_close": 100.0,
    }
    base.update(overrides)
    return base


class TestUnderlyingMarket:
    def test_cross_listed_etf_resolves_to_its_underlying_market(self):
        """IVV.AX is ASX-listed and AUD-priced but holds the S&P 500.

        This is the test. A naive '.AX means Australian' rule gets this wrong,
        which would put a US fund in the Australia filter and benchmark it
        against the wrong index.
        """
        asset = normalize_asset(raw(symbol="IVV.AX", currency="AUD"))

        assert asset.listed_exchange == "ASX"
        assert asset.underlying_market == "US"

    def test_domestic_etf_stays_local(self):
        asset = normalize_asset(raw(symbol="VAS.AX"))
        assert asset.underlying_market == "AU"

    def test_global_etf_is_tagged_global(self):
        asset = normalize_asset(raw(symbol="VGS.AX"))
        assert asset.underlying_market == "GLOBAL"

    def test_unmapped_asset_falls_back_and_warns(self):
        """Assets without an override rely on inference. That's correct for
        individual stocks, but the warning makes them a reviewable list rather
        than a silent assumption."""
        asset = normalize_asset(raw(symbol="NOTMAPPED.AX", quoteType="EQUITY",
                                    sector="Financials"))

        assert asset.underlying_market == "AU"
        assert any("no curated override" in w for w in asset.data_warnings)


class TestListedExchange:
    def test_ax_suffix_is_asx(self):
        assert normalize_asset(raw(symbol="ANZ.AX", quoteType="EQUITY",
                                   sector="Financials")).listed_exchange == "ASX"

    def test_plain_symbol_is_us(self):
        assert normalize_asset(raw(symbol="AAPL", quoteType="EQUITY",
                                   currency="USD", sector="Technology")).listed_exchange == "US"


class TestRejections:
    def test_missing_symbol_is_rejected(self):
        with pytest.raises(AssetValidationError):
            normalize_asset(raw(symbol=None))

    def test_missing_price_is_rejected(self):
        """Without a price the record is useless downstream."""
        with pytest.raises(AssetValidationError):
            normalize_asset(raw(latest_close=None))

    def test_non_numeric_price_is_rejected(self):
        with pytest.raises(AssetValidationError):
            normalize_asset(raw(latest_close="not a number"))


class TestQuoteTypeAwareWarnings:
    def test_etf_nulls_produce_no_warnings(self):
        """yfinance returns null sector/beta/marketCap for every ETF. Those are
        expected, not errors a warning about them would drown the real signals.
        """
        asset = normalize_asset(raw(symbol="IVV.AX", quoteType="ETF",
                                    sector=None, beta=None, marketCap=None))

        assert not asset.data_warnings

    def test_equity_missing_sector_warns(self):
        """A stock with no sector IS odd, unlike an ETF."""
        asset = normalize_asset(raw(symbol="CBA.AX", quoteType="EQUITY", sector=None))

        assert any("missing sector" in w for w in asset.data_warnings)


class TestVendorCorrections:
    def test_quote_type_override_applies_and_leaves_a_trail(self):
        """yfinance misreports VTS.AX as EQUITY; it's an ETF. We correct known-bad
        vendor data — but never silently."""
        asset = normalize_asset(raw(symbol="VTS.AX", quoteType="EQUITY"))

        assert asset.quote_type == "ETF"
        assert any("quote_type corrected" in w for w in asset.data_warnings)


class TestDividendYieldGuard:
    def test_implausible_yield_is_flagged_but_not_altered(self):
        """Warn-only by design: silently 'fixing' a financial figure is worse
        than surfacing that it looks wrong."""
        asset = normalize_asset(raw(symbol="VAS.AX", dividendYield=95.0))

        assert asset.dividend_yield == 95.0          # unchanged
        assert any("dividend_yield" in w for w in asset.data_warnings)

    def test_plausible_yield_passes_quietly(self):
        asset = normalize_asset(raw(symbol="VAS.AX", dividendYield=3.14))

        assert asset.dividend_yield == pytest.approx(3.14)
        assert not any("dividend_yield" in w for w in asset.data_warnings)

    def test_missing_yield_is_none_not_zero(self):
        """None means 'we don't know'; zero would be a claim."""
        asset = normalize_asset(raw(symbol="VAS.AX", dividendYield=None))

        assert asset.dividend_yield is None