"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { PortfolioCard } from "@/components/PortfolioCard";
import { PositionsTable } from "@/components/PositionsTable";
import { PnLChart } from "@/components/PnLChart";
import { AgentStatusPanel } from "@/components/AgentStatusPanel";
import { formatUSD, formatPercent } from "@/lib/utils";
import { Wallet, TrendingUp, BarChart3, Trophy } from "lucide-react";

export default function DashboardPage() {
  const { data: portfolio } = useQuery({
    queryKey: ["portfolio"],
    queryFn: api.getPortfolio,
  });

  const { data: pnlSeries } = useQuery({
    queryKey: ["pnl-series"],
    queryFn: () => api.getPnlSeries(30),
  });

  const { data: stats } = useQuery({
    queryKey: ["trade-stats"],
    queryFn: api.getTradeStats,
  });

  return (
    <div className="mr-72 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Portfolio overview and agent status
          </p>
        </div>
        <AgentStatusPanel />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <PortfolioCard
          title="Balance"
          value={formatUSD(portfolio?.balance ?? 0)}
          icon={Wallet}
        />
        <PortfolioCard
          title="Total P&L"
          value={formatUSD(portfolio?.total_pnl ?? 0)}
          subtitle={
            stats
              ? `${stats.total_trades} trades`
              : undefined
          }
          icon={TrendingUp}
          trend={
            (portfolio?.total_pnl ?? 0) >= 0
              ? "up"
              : "down"
          }
        />
        <PortfolioCard
          title="Active Positions"
          value={String(portfolio?.active_positions ?? 0)}
          icon={BarChart3}
        />
        <PortfolioCard
          title="Win Rate"
          value={`${portfolio?.win_rate ?? 0}%`}
          subtitle={
            stats
              ? `${stats.win_count}W / ${stats.loss_count}L`
              : undefined
          }
          icon={Trophy}
          trend={
            (portfolio?.win_rate ?? 0) >= 50
              ? "up"
              : (portfolio?.win_rate ?? 0) > 0
              ? "down"
              : "neutral"
          }
        />
      </div>

      <PnLChart data={pnlSeries ?? []} />

      <PositionsTable positions={portfolio?.positions ?? []} />
    </div>
  );
}
