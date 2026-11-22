/**
 * The arithmetic behind a carousel's risk spread strip, kept apart from the
 * component so it can be tested without rendering anything.
 *
 * Risk tiers come from the backend as names (quantile buckets of volatility,
 * see clustering.py). The strip places them on a five step scale from Calm
 * (tier 1) to Volatile (tier 5).
 */

export const TIER_ORDER = ["Very low", "Low", "Moderate", "High", "Very high"];

// Plain words for each step, used in captions and dot labels.
const TIER_WORDS = ["calm", "fairly calm", "moderate", "fairly volatile", "volatile"];

/** 1 to 5 for a known tier name, null for anything else. */
export function tierNumber(riskTier) {
  const position = TIER_ORDER.indexOf(riskTier);
  return position === -1 ? null : position + 1;
}

export function tierWord(tier) {
  return TIER_WORDS[tier - 1];
}

const knownTiers = (assets) =>
  assets.map((asset) => tierNumber(asset.risk_tier)).filter((tier) => tier !== null);

/**
 * Middle tier of a carousel, used to pick its background warmth. With an
 * even count the lower of the two middle tiers wins, so a group only reads
 * warmer once more than half of it actually is. Null if no tier is known.
 */
export function medianTier(assets) {
  const tiers = knownTiers(assets).sort((left, right) => left - right);
  if (tiers.length === 0) return null;
  return tiers[Math.floor((tiers.length - 1) / 2)];
}

/**
 * A short plain caption describing how a group's risk is spread.
 *
 * Tiers 1 and 2 count as calm and 4 and 5 as volatile. Three quarters on one
 * side reads as "mostly"; at least a quarter on both sides is a genuine mix;
 * anything else leans towards whichever side is bigger.
 */
export function spreadCaption(assets) {
  const tiers = knownTiers(assets);
  if (tiers.length === 0) return "Risk not yet measured";

  if (tiers.every((tier) => tier === tiers[0])) {
    return `All ${tierWord(tiers[0])}`;
  }

  const calmShare = tiers.filter((tier) => tier <= 2).length / tiers.length;
  const volatileShare = tiers.filter((tier) => tier >= 4).length / tiers.length;

  if (calmShare >= 0.75) return "Mostly calm";
  if (volatileShare >= 0.75) return "Mostly volatile";
  if (calmShare >= 0.25 && volatileShare >= 0.25) return "Mixes calm and volatile assets";
  if (calmShare === 0 && volatileShare === 0) return "Mostly moderate";
  return calmShare > volatileShare ? "Leans calm" : "Leans volatile";
}

/**
 * Where each dot sits: its tier, and its column and row inside that tier's
 * segment. Dots sharing a tier fill a row left to right, then stack upward
 * into the next row, so none overlap. Assets keep the carousel's order, so
 * the first card's dot is the first dot in its segment.
 *
 * Returns { dots, rows } where rows is the tallest stack, for sizing.
 */
export function layoutDots(assets, dotsPerRow) {
  const filledPerTier = [0, 0, 0, 0, 0];
  const dots = [];
  for (const asset of assets) {
    const tier = tierNumber(asset.risk_tier);
    if (tier === null) continue;
    const slot = filledPerTier[tier - 1]++;
    dots.push({ symbol: asset.symbol, tier, column: slot % dotsPerRow, row: Math.floor(slot / dotsPerRow) });
  }
  const rows = dots.reduce((tallest, dot) => Math.max(tallest, dot.row + 1), 0);
  return { dots, rows };
}
