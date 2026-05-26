"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AgentStatusPanel } from "@/components/AgentStatusPanel";
import { RiskConfigForm } from "@/components/RiskConfigForm";
import { cn } from "@/lib/utils";
import {
  ShieldAlert,
  ShieldCheck,
  Loader2,
  Zap,
  Settings,
  FlaskConical,
  Radio,
  AlertTriangle,
} from "lucide-react";

export default function AgentPage() {
  const qc = useQueryClient();

  const { data } = useQuery({
    queryKey: ["agent-status"],
    queryFn: api.getAgentStatus,
  });

  const killMut = useMutation({
    mutationFn: api.killAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const unkillMut = useMutation({
    mutationFn: api.unkillAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const goLiveMut = useMutation({
    mutationFn: api.goLive,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const goPaperMut = useMutation({
    mutationFn: api.goPaper,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const config = data?.config || {};
  const status = data?.status || "stopped";
  const isKilled = status === "killed";
  const isPaper = config.paper_mode !== "false";

  return (
    <div className="mr-72 space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Agent Controls</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Configure strategy and risk parameters
          </p>
        </div>
        <AgentStatusPanel />
      </div>

      {/* Trading Mode */}
      <div
        className={cn(
          "rounded-xl border-2 p-6",
          isPaper
            ? "border-warning/30 bg-warning/5"
            : "border-danger/30 bg-danger/5"
        )}
      >
        <div className="flex items-center gap-2 mb-3">
          {isPaper ? (
            <FlaskConical className="h-5 w-5 text-warning" />
          ) : (
            <Radio className="h-5 w-5 text-danger" />
          )}
          <h2 className="text-base font-semibold">
            Trading Mode:{" "}
            <span className={isPaper ? "text-warning" : "text-danger"}>
              {isPaper ? "Paper Trading" : "LIVE TRADING"}
            </span>
          </h2>
        </div>

        {isPaper ? (
          <>
            <p className="mb-4 text-xs text-muted-foreground">
              The agent is in <strong>paper trading mode</strong>. It will scan
              markets, run AI analysis, and generate signals — but{" "}
              <strong>no real orders will be placed</strong>. All trades are
              simulated and logged as &ldquo;paper&rdquo; trades. Your funds are
              safe.
            </p>
            <button
              onClick={() => {
                const confirmed = confirm(
                  "⚠️ SWITCH TO LIVE TRADING?\n\n" +
                    "This will allow the agent to place REAL orders with REAL money.\n\n" +
                    "Make sure you have reviewed:\n" +
                    "• Max position size\n" +
                    "• Max total exposure\n" +
                    "• Max daily loss limit\n\n" +
                    "Type OK to confirm."
                );
                if (confirmed) goLiveMut.mutate();
              }}
              disabled={goLiveMut.isPending}
              className="flex items-center gap-2 rounded-lg bg-danger/15 px-4 py-2.5 text-sm font-medium text-danger hover:bg-danger/25 transition-colors disabled:opacity-50"
            >
              {goLiveMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <AlertTriangle className="h-4 w-4" />
              )}
              Switch to Live Trading
            </button>
          </>
        ) : (
          <>
            <p className="mb-4 text-xs text-muted-foreground">
              The agent is in{" "}
              <strong className="text-danger">live trading mode</strong>. Real
              orders will be placed on Polymarket using your wallet. Use the kill
              switch below for emergency stops.
            </p>
            <button
              onClick={() => goPaperMut.mutate()}
              disabled={goPaperMut.isPending}
              className="flex items-center gap-2 rounded-lg bg-warning/15 px-4 py-2.5 text-sm font-medium text-warning hover:bg-warning/25 transition-colors disabled:opacity-50"
            >
              {goPaperMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FlaskConical className="h-4 w-4" />
              )}
              Switch to Paper Trading
            </button>
          </>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Kill Switch */}
        <div className="rounded-xl border-2 border-danger/30 bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <ShieldAlert className="h-5 w-5 text-danger" />
            <h2 className="text-base font-semibold">Kill Switch</h2>
          </div>
          <p className="mb-4 text-xs text-muted-foreground">
            Emergency stop: cancels all open orders, halts the agent
            immediately, and prevents new trades until manually re-enabled.
          </p>
          {isKilled ? (
            <button
              onClick={() => unkillMut.mutate()}
              disabled={unkillMut.isPending}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-success py-3 text-sm font-bold text-white hover:bg-success/90 transition-colors disabled:opacity-50"
            >
              {unkillMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="h-4 w-4" />
              )}
              Re-enable Trading
            </button>
          ) : (
            <button
              onClick={() => {
                if (
                  confirm(
                    "Activate kill switch? This will cancel all orders and stop the agent."
                  )
                ) {
                  killMut.mutate();
                }
              }}
              disabled={killMut.isPending}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-danger py-3 text-sm font-bold text-white hover:bg-danger/90 transition-colors disabled:opacity-50"
            >
              {killMut.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ShieldAlert className="h-4 w-4" />
              )}
              ACTIVATE KILL SWITCH
            </button>
          )}
        </div>

        {/* Quick Stats */}
        <div className="rounded-xl border border-border bg-card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="h-5 w-5 text-warning" />
            <h2 className="text-base font-semibold">Current Settings</h2>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[
              [
                "Mode",
                isPaper ? "Paper" : "LIVE",
              ],
              [
                "Scan Interval",
                `${config.scan_interval || 300}s`,
              ],
              [
                "Min Edge",
                `${((Number(config.min_edge_threshold) || 0.05) * 100).toFixed(1)}%`,
              ],
              ["LLM Weight", config.llm_weight || "0.6"],
              [
                "Max Position",
                `$${config.max_position_size || 50}`,
              ],
              [
                "Max Exposure",
                `$${config.max_total_exposure || 500}`,
              ],
              [
                "Max Daily Loss",
                `$${config.max_daily_loss || 100}`,
              ],
              [
                "Whale Conviction",
                config.whale_conviction_enabled === "true" ? "ON" : "OFF",
              ],
              [
                "Live Scalper",
                config.scalper_enabled === "true" ? "ON" : "OFF",
              ],
              [
                "Market Sniper",
                config.sniper_enabled === "true" ? "ON" : "OFF",
              ],
              [
                "Odds Compare",
                config.odds_comparison === "true" ? "ON" : "OFF",
              ],
              [
                "Sentiment",
                config.sentiment_monitoring === "true" ? "ON" : "OFF",
              ],
              [
                "Market Making",
                config.market_making === "true" ? "ON" : "OFF",
              ],
            ].map(([label, value]) => (
              <div
                key={label}
                className={cn(
                  "rounded-lg p-3",
                  label === "Mode" && !isPaper ? "bg-danger/10" : "bg-muted"
                )}
              >
                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {label}
                </p>
                <p
                  className={cn(
                    "mt-1 text-sm font-bold",
                    label === "Mode" && !isPaper && "text-danger"
                  )}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Configuration Form */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-5">
          <Settings className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-base font-semibold">Strategy Configuration</h2>
        </div>
        <RiskConfigForm config={config} />
      </div>
    </div>
  );
}
