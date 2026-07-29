"""
Compute and store beginner-friendly asset descriptions.

Two treatments, decided by what the data actually looks like (see
probe_text.py): equities get extractive summarization, US ETFs get jargon
glossing, ASX ETFs (no source text at all) get skipped entirely

no model fitting, just text processing on data already sitting in memory from ingestion.
"""

import json
import logging

import yfinance as yf
from sqlalchemy.orm import Session
from sqlalchemy import select

from src.ml.text_processing import (
    extractive_summary,
    find_jargon,
    flesch_reading_ease,
)
from src.storage.models import Asset, AssetDescription

logger = logging.getLogger("compute_descriptions")

SUMMARY_SENTENCES = 3


def _describe_equity(text: str):
    """Extractive summary for a dense equity description."""
    summary = extractive_summary(text, max_sentences=SUMMARY_SENTENCES)
    glossary = find_jargon(text)
    return summary, json.dumps(glossary) if glossary else None


def _describe_etf(text: str):
    """ETF text is already short — keep it whole, gloss the jargon in it."""
    glossary = find_jargon(text)
    return text, json.dumps(glossary) if glossary else None


def compute_and_store_descriptions(session: Session) -> tuple[int, int]:
    """Fetch source text and derive a description for every asset that has
    one. Returns (succeeded, skipped_no_text)"""
    assets = session.scalars(select(Asset).where(Asset.is_benchmark == False)).all()

    succeeded = 0
    skipped = 0

    for asset in assets:
        try:
            info = yf.Ticker(asset.symbol).info
        except Exception as exc:
            logger.warning("%s: fetch failed for description text (%s)",
                           asset.symbol, type(exc).__name__)
            skipped += 1
            continue

        text = info.get("longBusinessSummary")
        if not text:
            # Expected for ASX ETFs — not an error, just nothing to process.
            skipped += 1
            continue

        if asset.quote_type == "EQUITY":
            summary, jargon_json = _describe_equity(text)
            method = "summary"
        else:
            summary, jargon_json = _describe_etf(text)
            method = "jargon"

        source_score = flesch_reading_ease(text)
        summary_score = flesch_reading_ease(summary)

        existing = session.get(AssetDescription, asset.symbol)
        if existing is None:
            session.add(AssetDescription(
                symbol=asset.symbol,
                method=method,
                summary=summary,
                jargon=jargon_json,
                source_readability=source_score,
                summary_readability=summary_score,
            ))
        else:
            existing.method = method
            existing.summary = summary
            existing.jargon = jargon_json
            existing.source_readability = source_score
            existing.summary_readability = summary_score

        logger.info(
            "%s: %s, readability %.1f -> %.1f",
            asset.symbol, method,
            source_score if source_score is not None else float("nan"),
            summary_score if summary_score is not None else float("nan"),
        )
        succeeded += 1

    return succeeded, skipped