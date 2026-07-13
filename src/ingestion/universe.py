"""
Loads the curated asset universe from config/universe.yaml.

Keeping it in config means the list can be reviewed, extended, or swapped 
"""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "universe.yaml"


def load_universe() -> list[str]:
    """Return the list of ticker symbols to ingest."""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return [entry["symbol"] for entry in config["assets"]]


def load_universe_with_metadata() -> list[dict]:
    """Return full entries (symbol, category, note)"""
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    return config["assets"]


if __name__ == "__main__":
    universe = load_universe()
    print(f"Curated universe: {len(universe)} assets")
    entries = load_universe_with_metadata()
    from collections import Counter
    for category, count in Counter(e["category"] for e in entries).items():
        print(f"  {category:15s} {count}")