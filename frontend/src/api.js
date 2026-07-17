/**
 * API client
 */

const API_BASE = "http://localhost:8000";

async function request(path) {
  const url = `${API_BASE}${path}`;
  let response;
  try {
    response = await fetch(url);
  } catch (networkError) {
    // fetch only rejects on network failure
    throw new Error(
      `Could not reach the API at ${url}. Is the backend running? ` +
      `(${networkError.message})`
    );
  }
  if (!response.ok) {
    throw new Error(`API returned ${response.status} for ${path}`);
  }
  return response.json();
}

/** Fetch the carousels for the dashboard, optionally filtered by market. */
export async function getCarousels(underlyingMarket = null, minSize = 1) {
  const params = new URLSearchParams();
  if (underlyingMarket) params.set("underlying_market", underlyingMarket);
  if (minSize > 1) params.set("min_size", String(minSize));
  const query = params.toString();
  return request(`/api/carousels${query ? `?${query}` : ""}`);
}

/** Fetch full detail for one asset — for the Knowledge Card. */
export async function getAsset(symbol) {
  return request(`/api/assets/${encodeURIComponent(symbol)}`);
}

/** Fetch price history for one asset — for the chart. */
export async function getPrices(symbol, days = 365) {
  return request(`/api/assets/${encodeURIComponent(symbol)}/prices?days=${days}`);
}

/** Health check */
export async function getHealth() {
  return request("/api/health");
}