const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export const api = {
  getPortfolio: () => request<any>("/api/portfolio"),
  getBalance: () => request<any>("/api/portfolio/balance"),

  getMarkets: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<any[]>(`/api/markets${qs}`);
  },
  getTags: () => request<any[]>("/api/markets/tags"),
  getMarket: (id: string) => request<any>(`/api/markets/${id}`),
  getOrderbook: (conditionId: string, tokenId: string) =>
    request<any>(
      `/api/markets/${conditionId}/orderbook?token_id=${encodeURIComponent(tokenId)}`
    ),
  getPriceHistory: (conditionId: string, tokenId: string, interval = "max") =>
    request<any[]>(
      `/api/markets/${conditionId}/history?token_id=${encodeURIComponent(tokenId)}&interval=${interval}&fidelity=200`
    ),
  analyzeMarket: (id: string) =>
    request<any>(`/api/markets/${id}/analyze`, { method: "POST" }),

  getAgentStatus: () => request<any>("/api/agent/status"),
  startAgent: () => request<any>("/api/agent/start", { method: "POST" }),
  stopAgent: () => request<any>("/api/agent/stop", { method: "POST" }),
  killAgent: () => request<any>("/api/agent/kill", { method: "POST" }),
  unkillAgent: () => request<any>("/api/agent/unkill", { method: "POST" }),
  goLive: () => request<any>("/api/agent/go-live", { method: "POST" }),
  goPaper: () => request<any>("/api/agent/go-paper", { method: "POST" }),
  updateAgentConfig: (config: Record<string, any>) =>
    request<any>("/api/agent/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  getTrades: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<any[]>(`/api/trades${qs}`);
  },
  getTradeStats: () => request<any>("/api/trades/stats"),
  getPnlSeries: (days?: number) =>
    request<any[]>(`/api/trades/pnl-series${days ? `?days=${days}` : ""}`),
  getLogs: (limit?: number) =>
    request<any[]>(`/api/trades/logs${limit ? `?limit=${limit}` : ""}`),

  getWhaleWatchlist: (activeOnly = true) =>
    request<any[]>(`/api/whales/watchlist?active_only=${activeOnly}`),
  refreshWhaleWatchlist: (category = "OVERALL", timePeriod = "MONTH") =>
    request<any>(`/api/whales/watchlist/refresh?category=${category}&time_period=${timePeriod}`, {
      method: "POST",
    }),
  toggleWhale: (wallet: string, active: boolean) =>
    request<any>(`/api/whales/watchlist/${wallet}/toggle?active=${active}`, {
      method: "POST",
    }),
  getWhaleTrades: (limit = 50) =>
    request<any[]>(`/api/whales/trades?limit=${limit}`),
  getWhaleTradesForWallet: (wallet: string, limit = 20) =>
    request<any[]>(`/api/whales/trades/${wallet}?limit=${limit}`),
  getWhaleStats: (wallet: string) =>
    request<any>(`/api/whales/stats/${wallet}`),

  getSentimentAlerts: (limit = 50) =>
    request<any[]>(`/api/sentiment/alerts?limit=${limit}`),
  getMmInventory: () => request<any[]>("/api/market-making/inventory"),

  getOddsDiscrepancies: () => request<any[]>("/api/odds/discrepancies"),
  refreshOdds: () => request<any>("/api/odds/refresh", { method: "POST" }),
  getOddsSports: () => request<any[]>("/api/odds/sports"),

  // Scalper
  getScalperPositions: (status = "") =>
    request<any[]>(`/api/scalper/positions?status=${status}`),
  getScalperSignals: () => request<any[]>("/api/scalper/signals"),
  startScalper: () => request<any>("/api/scalper/start", { method: "POST" }),
  stopScalper: () => request<any>("/api/scalper/stop", { method: "POST" }),
  getScalperStatus: () => request<any>("/api/scalper/status"),

  // Sniper
  getSniperDetections: (limit = 50) =>
    request<any[]>(`/api/sniper/detections?limit=${limit}`),
  startSniper: () => request<any>("/api/sniper/start", { method: "POST" }),
  stopSniper: () => request<any>("/api/sniper/stop", { method: "POST" }),
  getSniperStatus: () => request<any>("/api/sniper/status"),

  // Agent Plans (thought log)
  getAgentPlans: (strategy = "", limit = 50) =>
    request<any[]>(
      `/api/agent-plans/plans?strategy=${strategy}&limit=${limit}`
    ),
  getAgentPlan: (id: number) => request<any>(`/api/agent-plans/plans/${id}`),
  getAllPositions: (status = "", strategy = "") =>
    request<any[]>(
      `/api/agent-plans/positions?status=${status}&strategy=${strategy}`
    ),

  // Whale conviction status
  getWhaleStatus: () => request<any>("/api/whales/status"),
};
