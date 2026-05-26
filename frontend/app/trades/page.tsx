"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { TradeTable } from "@/components/TradeTable";
import { PnLChart } from "@/components/PnLChart";
import { PortfolioCard } from "@/components/PortfolioCard";
import { formatUSD } from "@/lib/utils";
import {
  BarChart3,
  TrendingUp,
  Trophy,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

export default function TradesPage() {
  const { data: trades } = useQuery({
    queryKey: ["trades"],
    queryFn: () => api.getTrades({ limit: "100" }),
  });

  const { data: stats } = useQuery({
    queryKey: ["trade-stats"],
    queryFn: api.getTradeStats,
  });

  const { data: pnlSeries } = useQuery({
    queryKey: ["pnl-series"],
    queryFn: () => api.getPnlSeries(90),
  });

  return (
    <div className="mr-72 space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Trade History</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Performance analytics and trade log
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <PortfolioCard
          title="Total Trades"
          value={String(stats?.total_trades ?? 0)}
          icon={BarChart3}
        />
        <PortfolioCard
          title="Total P&L"
          value={formatUSD(stats?.total_pnl ?? 0)}
          icon={TrendingUp}
          trend={(stats?.total_pnl ?? 0) >= 0 ? "up" : "down"}
        />
        <PortfolioCard
          title="Win Rate"
          value={`${stats?.win_rate ?? 0}%`}
          subtitle={`${stats?.win_count ?? 0}W / ${stats?.loss_count ?? 0}L`}
          icon={Trophy}
          trend={(stats?.win_rate ?? 0) >= 50 ? "up" : "neutral"}
        />
        <PortfolioCard
          title="Avg Trade"
          value={formatUSD(stats?.avg_trade_pnl ?? 0)}
          subtitle={`Best: ${formatUSD(stats?.best_trade ?? 0)} / Worst: ${formatUSD(stats?.worst_trade ?? 0)}`}
          icon={stats?.avg_trade_pnl >= 0 ? ArrowUpRight : ArrowDownRight}
          trend={(stats?.avg_trade_pnl ?? 0) >= 0 ? "up" : "down"}
        />
      </div>

      <PnLChart data={pnlSeries ?? []} height={300} />

      <div>
        <h2 className="mb-3 text-sm font-semibold">Recent Trades</h2>
        <TradeTable trades={trades ?? []} />
      </div>
    </div>
  );
}
