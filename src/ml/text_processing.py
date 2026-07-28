"""
Text processing for beginner-friendly asset descriptions

TWO TECHNIQUES, chosen because the source data demands different treatment

  * EQUITIES have 1,163-1,825 chars of dense prose (7-13 sentences). The problem
    is length -> extractive summarization compresses to the 2-3 most informative
    sentences.

  * US ETFs have only 451-503 chars of prospectus boilerplate. The problem isn't
    length, it's jargon ("publicly-issued U.S. Treasury securities with a
    remaining maturity greater than twenty years")

  * ASX ETFs return NO description text at all, so they keep the existing
    metric-derived explainer. Nothing to process.

WHY EXTRACTIVE, NOT ABSTRACTIVE: an abstractive model (BART/T5) generates new
text and can therefore hallucinate. In a finance tool for beginners, a summary
that invents a fact about a company is worse than no summary. Extractive
selection is incapable of hallucinating so every word came from the source.
"""

import math
import re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

_ABBREVIATIONS = [
    "U.S.", "U.K.", "Inc.", "Corp.", "Ltd.", "Co.", "plc.", "S.A.",
    "Jr.", "Sr.", "St.", "No.", "Approx.", "etc.", "vs.", "e.g.", "i.e.",
]

_VOWEL_GROUPS = re.compile(r"[aeiouy]+")

# Composite ranking weights
CENTRALITY_WEIGHT = 0.6
READABILITY_WEIGHT = 0.4

def split_sentences(text: str):
    """Split prose into sentences, guarding common abbreviations."""
    if not text:
        return []

    # Temporarily mask abbreviation periods so they don't trigger a split.
    masked = text
    for i, abbr in enumerate(_ABBREVIATIONS):
        masked = masked.replace(abbr, abbr.replace(".", f"<ABBR{i}>"))

    parts = re.split(r"(?<=[.!?])\s+", masked)

    # Unmask and clean
    sentences = []
    for part in parts:
        for i, abbr in enumerate(_ABBREVIATIONS):
            part = part.replace(f"<ABBR{i}>", ".")
        part = part.strip()
        if len(part) > 15:
            sentences.append(part)
    return sentences

def count_syllables(word: str):
    """Approximate syllable count by counting vowel groups.

    A heuristic, not a dictionary lookup — accurate enough for a readability
    score computed over hundreds of words, where individual errors average out.
    """
    word = word.lower().strip(".,;:!?\"'()")
    if not word:
        return 0
    count = len(_VOWEL_GROUPS.findall(word))
    # Silent trailing 'e' ("make" is one syllable, not two).
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)

def flesch_reading_ease(text: str):
    """Flesch Reading Ease: higher is easier.

        206.835 - 1.015 * (words/sentence) - 84.6 * (syllables/word)

    compute this before and after processing to measure the effect rather
    than assert it. the same discipline as backtesting the forecasts.
    """
    sentences = split_sentences(text)
    if not sentences:
        return None

    words = re.findall(r"\b[\w'-]+\b", text)
    if not words:
        return None

    syllables = sum(count_syllables(w) for w in words)

    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllables / len(words)

    score = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    return round(score, 1)

def reading_level(score: float | None) -> str:
    """Turn a Flesch score into a human label."""
    if score is None:
        return "unknown"
    if score >= 80:
        return "very easy"
    if score >= 70:
        return "easy"
    if score >= 60:
        return "plain English"
    if score >= 50:
        return "fairly difficult"
    if score >= 30:
        return "difficult (college level)"
    return "very difficult (graduate level)"

def _normalize(values: np.ndarray) -> np.ndarray:
    """Min-max scale to 0-1 so two differently-scaled scores can be blended.

    Centrality is a similarity sum (roughly 0-5); Flesch runs from negative to
    100+
    """
    values = np.asarray(values, dtype=float)
    low, high = values.min(), values.max()
    if high - low < 1e-12:
        return np.full_like(values, 0.5)
    return (values - low) / (high - low)


def _sentence_readability(sentence: str) -> float:
    """Flesch score for a single sentence we already know is one sentence.

    Separate from flesch_reading_ease() so we don't re-run the splitter on
    something already split — and so a short sentence can't fail the split
    and come back as None.
    """
    words = re.findall(r"\b[\w'-]+\b", sentence)
    if not words:
        return 0.0
    syllables = sum(count_syllables(w) for w in words)
    return 206.835 - 1.015 * len(words) - 84.6 * (syllables / len(words))

def extractive_summary(text: str, max_sentences: int = 3) -> str:
    """Select the most central sentences via TF-IDF cosine centrality"""
    sentences = split_sentences(text)
    if len(sentences) <= max_sentences:
        return " ".join(sentences)

    try:
        vectorizer = TfidfVectorizer(stop_words="english")
        matrix = vectorizer.fit_transform(sentences)
    except ValueError:
        # This happens if the text is too short to extract any features.
        return " ".join(sentences[:max_sentences])

    similarity = cosine_similarity(matrix)
    # Exclude self-similarity (always 1.0) so it doesn't dominate the score.
    np.fill_diagonal(similarity, 0)
    centrality = similarity.sum(axis=1)

    top_indices = np.argsort(centrality)[-max_sentences:]
    top_indices = sorted(top_indices)  # restore document order

    return " ".join(sentences[i] for i in top_indices)

#  Jargon glossing
# Terms that appear in real yfinance fund descriptions (verified against the
# probe output) and mean nothing to a beginner.
JARGON = {
    "replication strategy":
        "the fund buys the same investments as the index it follows, rather than picking its own",
    "underlying index":
        "the market index the fund is designed to copy",
    "remaining maturity":
        "how long until the bond is paid back",
    "face value":
        "the amount a bond pays back when it matures",
    "equity securities":
        "shares in companies",
    "fixed income":
        "bonds — loans to governments or companies that pay regular interest",
    "market capitalization":
        "the total value of all a company's shares",
    "diversified":
        "spread across many different investments, so one bad result matters less",
    "large-cap":
        "large, well-established companies",
    "small-cap":
        "smaller companies — usually more volatile",
    "benchmark index":
        "a standard list of investments used to measure performance against",
    "net assets":
        "the total value of everything the fund holds",
    "sampling":
        "the fund holds a representative selection rather than every investment in the index",
    "depositary receipts":
        "a way of holding foreign shares through a local listing",
}

def find_jargon(text: str) -> list[dict]:
    """Return glosses for jargon terms present in the text."""
    if not text:
        return []

    lowered = text.lower()
    found = []
    for term, plain in JARGON.items():
        position = lowered.find(term)
        if position != -1:
            found.append({"term": term, "plain": plain, "_pos": position})

    found.sort(key=lambda item: item["_pos"])
    return [{"term": f["term"], "plain": f["plain"]} for f in found]

def _self_test() -> None:
    equity = (
        "Apple Inc. designs, manufactures, and markets smartphones, personal "
        "computers, tablets, wearables, and accessories worldwide. The company "
        "offers iPhone, a line of smartphones; Mac, a line of personal computers; "
        "and iPad, a line of multi-purpose tablets. It also provides AppleCare "
        "support services. The company sells its products through its retail "
        "stores, online stores, and direct sales force. Apple Inc. was founded "
        "in 1976 and is headquartered in Cupertino, California."
    )
    etf = (
        "In seeking to track the performance of the index, the fund employs a "
        "replication strategy. It generally invests substantially all, but at "
        "least 95%, of its total assets in the securities comprising the "
        "underlying index. The index consists of publicly-issued U.S. Treasury "
        "securities that have a remaining maturity greater than twenty years."
    )

    print("EQUITY — extractive summarization")
    print("-" * 60)
    sents = split_sentences(equity)
    print(f"source: {len(sents)} sentences, {len(equity)} chars")
    before = flesch_reading_ease(equity)
    summary = extractive_summary(equity, max_sentences=2)
    after = flesch_reading_ease(summary)
    print(f"readability: {before} ({reading_level(before)}) "
          f"-> {after} ({reading_level(after)})")
    print(f"summary: {summary}\n")

    print("ETF — jargon glossing")
    print("-" * 60)
    print(f"source: {len(split_sentences(etf))} sentences")
    for item in find_jargon(etf):
        print(f"  {item['term']}: {item['plain']}")

    print("\nSanity checks")
    print("-" * 60)
    print(f"'U.S. Treasury' stays intact: "
          f"{'U.S. Treasury' in ' '.join(split_sentences(etf))}")
    print(f"syllables('investment') = {count_syllables('investment')} (expect 3)")
    print(f"syllables('make') = {count_syllables('make')} (expect 1)")


if __name__ == "__main__":
    _self_test()