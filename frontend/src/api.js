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

/** Fetch the stored ARIMA forecast for one asset. Returns null if none exists. */
export async function getForecast(symbol) {
  try {
    return await request(`/api/assets/${encodeURIComponent(symbol)}/forecast`);
  } catch {
    return null;
  }
}

export async function getDescription(symbol) {
  try {
    return await request(`/api/assets/${encodeURIComponent(symbol)}/description`);
  } catch {
    return null;
  }
}

/** Search assets by symbol or name */
export async function searchAssets(query, limit = 8) {
  const q = query.trim();
  if (!q) return [];
  try {
    return await request(`/api/assets/search?q=${encodeURIComponent(q)}&limit=${limit}`);
  } catch {
    return [];
  }
}