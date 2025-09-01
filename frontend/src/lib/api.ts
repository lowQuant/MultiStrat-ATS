/**
 * API utility functions for MATS backend communication
 */

const API_BASE_URL = 'http://localhost:8000';

export interface PortfolioPosition {
  symbol: string;
  'asset class': string;
  position: number;
  '% of nav': number;
  currency: string;
  marketPrice: number;
  averageCost: number;
  'pnl %': number;
  strategy: string;
}

export interface PortfolioResponse {
  success: boolean;
  message: string;
  data: {
    positions: PortfolioPosition[];
    total_positions: number;
    total_equity: number;
    base_currency: string;
  };
}

export interface PortfolioSummaryResponse {
  success: boolean;
  message: string;
  data: {
    total_positions: number;
    total_realized_pnl: number;
    total_unrealized_pnl: number;
    total_pnl: number;
    positions: any[];
    last_updated: string;
  };
}

/**
 * Fetch portfolio positions from backend
 */
export async function fetchPortfolioPositions(): Promise<PortfolioResponse> {
  const response = await fetch(`${API_BASE_URL}/portfolio/positions`);
  if (!response.ok) {
    throw new Error(`Failed to fetch positions: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch portfolio summary from backend
 */
export async function fetchPortfolioSummary(): Promise<PortfolioSummaryResponse> {
  const response = await fetch(`${API_BASE_URL}/portfolio/summary`);
  if (!response.ok) {
    throw new Error(`Failed to fetch portfolio summary: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Refresh portfolio positions (clears caches)
 */
export async function refreshPortfolioPositions(): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${API_BASE_URL}/portfolio/refresh-positions`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to refresh positions: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch FX rates information
 */
export async function fetchFXRates(): Promise<any> {
  const response = await fetch(`${API_BASE_URL}/portfolio/fx-rates`);
  if (!response.ok) {
    throw new Error(`Failed to fetch FX rates: ${response.statusText}`);
  }
  return response.json();
}
