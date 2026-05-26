"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  TrendingUp,
  Crosshair,
  Waves,
  Play,
  Square,
  Loader2,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Target,
  ShieldAlert,
} from "lucide-react";

function StatusBadge({ running }: { running: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase",
        running
          ? "bg-success/15 text-success"
          : "bg-muted text-muted-foreground"
      )}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          running ? "bg-success animate-pulse" : "bg-muted-foreground"
        )}
      />
      {running ? "Running" : "Stopped"}
    </span>
  );
}

function ScalperPanel() {
  const qc = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["scalper-status"],
    queryFn: api.getScalperStatus,
    refetchInterval: 5000,
  });
  const { data: positions } = useQuery({
    queryKey: ["scalper-positions"],
    queryFn: () => api.getScalperPositions(),
    refetchInterval: 10000,
  });
  const { data: signals } = useQuery({
    queryKey: ["scalper-signals"],
    queryFn: api.getScalperSignals,
    refetchInterval: 10000,
  });

  const startMut = useMutation({
    mutationFn: api.startScalper,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scalper-status"] }),
  });
  const stopMut = useMutation({
    mutationFn: api.stopScalper,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scalper-status"] }),
  });

  const running = status?.running ?? false;
  const openPositions = (positions || []).filter(
    (p: any) => p.status === "open"
  );

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-blue-400" />
          <h2 className="text-base font-semibold">Live Scalper</h2>
          <StatusBadge running={running} />
        </div>
        <button
          onClick={() => (running ? stopMut.mutate() : startMut.mutate())}
          disabled={startMut.isPending || stopMut.isPending}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
            running
              ? "bg-danger/15 text-danger hover:bg-danger/25"
              : "bg-success/15 text-success hover:bg-success/25"
          )}
        >
          {startMut.isPending || stopMut.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : running ? (
            <Square className="h-3 w-3" />
          ) : (
            <Play className="h-3 w-3" />
          )}
          {running ? "Stop" : "Start"}
        </button>
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        Statistical pre-filter + LLM agent for short-term trades on active
        markets.
      </p>

      {/* Open Positions */}
      {openPositions.length > 0 && (
        <div className="mb-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Open Positions ({openPositions.length})
          </p>
          <div className="space-y-2">
            {openPositions.map((pos: any) => {
              const pnlPct =
                pos.entry_price > 0
                  ? ((pos.current_price - pos.entry_price) / pos.entry_price) *
                    100
                  : 0;
              const isUp = pnlPct >= 0;
              return (
                <div
                  key={pos.id}
                  className="flex items-center justify-between rounded-lg bg-muted p-3"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">
                      {pos.market_title}
                    </p>
                    <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                      <span className="uppercase font-bold">{pos.side}</span>
                      <span>@ {pos.entry_price?.toFixed(4)}</span>
                      <span className="flex items-center gap-0.5">
                        <Target className="h-2.5 w-2.5" />
                        {pos.exit_target?.toFixed(4)}
                      </span>
                      <span className="flex items-center gap-0.5">
                        <ShieldAlert className="h-2.5 w-2.5" />
                        {pos.stop_loss?.toFixed(4)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right ml-3">
                    <p
                      className={cn(
                        "text-xs font-bold",
                        isUp ? "text-success" : "text-danger"
                      )}
                    >
                      {isUp ? (
                        <ArrowUpRight className="inline h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="inline h-3 w-3" />
                      )}
                      {pnlPct.toFixed(2)}%
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      ${pos.size?.toFixed(2)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Signal Heatmap */}
      {signals && signals.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Signal Scores
          </p>
          <div className="space-y-1.5">
            {signals.slice(0, 8).map((s: any) => {
              const score = s.composite ?? 0;
              const absScore = Math.abs(score);
              return (
                <div
                  key={s.token_id}
                  className="flex items-center gap-2 text-[11px]"
                >
                  <span className="flex-1 truncate text-muted-foreground">
                    {s.question?.slice(0, 40)}
                  </span>
                  <div className="w-20 h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full transition-all",
                        score > 0 ? "bg-success" : "bg-danger"
                      )}
                      style={{ width: `${absScore * 100}%` }}
                    />
                  </div>
                  <span
                    className={cn(
                      "w-12 text-right font-mono font-bold",
                      score > 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {score > 0 ? "+" : ""}
                    {score.toFixed(3)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function SniperPanel() {
  const qc = useQueryClient();
  const { data: status } = useQuery({
    queryKey: ["sniper-status"],
    queryFn: api.getSniperStatus,
    refetchInterval: 5000,
  });
  const { data: detections } = useQuery({
    queryKey: ["sniper-detections"],
    queryFn: () => api.getSniperDetections(20),
    refetchInterval: 15000,
  });

  const startMut = useMutation({
    mutationFn: api.startSniper,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sniper-status"] }),
  });
  const stopMut = useMutation({
    mutationFn: api.stopSniper,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sniper-status"] }),
  });

  const running = status?.running ?? false;
  const items = detections || [];
  const betCount = items.filter((d: any) => d.action === "bet").length;
  const hitRate =
    items.length > 0 ? ((betCount / items.length) * 100).toFixed(0) : "0";

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Crosshair className="h-5 w-5 text-orange-400" />
          <h2 className="text-base font-semibold">Market Sniper</h2>
          <StatusBadge running={running} />
        </div>
        <button
          onClick={() => (running ? stopMut.mutate() : startMut.mutate())}
          disabled={startMut.isPending || stopMut.isPending}
          className={cn(
            "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
            running
              ? "bg-danger/15 text-danger hover:bg-danger/25"
              : "bg-success/15 text-success hover:bg-success/25"
          )}
        >
          {startMut.isPending || stopMut.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : running ? (
            <Square className="h-3 w-3" />
          ) : (
            <Play className="h-3 w-3" />
          )}
          {running ? "Stop" : "Start"}
        </button>
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        WebSocket + polling to detect new markets and snipe mispriced ones before
        smart money arrives.
      </p>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="rounded-lg bg-muted p-3 text-center">
          <p className="text-[10px] font-medium uppercase text-muted-foreground">
            Detected
          </p>
          <p className="text-lg font-bold">{items.length}</p>
        </div>
        <div className="rounded-lg bg-muted p-3 text-center">
          <p className="text-[10px] font-medium uppercase text-muted-foreground">
            Sniped
          </p>
          <p className="text-lg font-bold text-success">{betCount}</p>
        </div>
        <div className="rounded-lg bg-muted p-3 text-center">
          <p className="text-[10px] font-medium uppercase text-muted-foreground">
            Hit Rate
          </p>
          <p className="text-lg font-bold">{hitRate}%</p>
        </div>
      </div>

      {/* Detection Timeline */}
      {items.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Recent Detections
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {items.slice(0, 10).map((d: any) => (
              <div
                key={d.id}
                className="flex items-start gap-2 rounded-lg bg-muted p-3"
              >
                <div
                  className={cn(
                    "mt-0.5 h-2 w-2 rounded-full flex-shrink-0",
                    d.action === "bet" ? "bg-success" : "bg-muted-foreground"
                  )}
                />
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate">
                    {d.market_title}
                  </p>
                  <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                    <span>
                      Initial: {(d.initial_price * 100).toFixed(0)}%
                    </span>
                    {d.price_5min_later != null && (
                      <span>
                        5min: {(d.price_5min_later * 100).toFixed(0)}%
                      </span>
                    )}
                    <span
                      className={cn(
                        "font-bold uppercase",
                        d.action === "bet"
                          ? "text-success"
                          : "text-muted-foreground"
                      )}
                    >
                      {d.action}
                    </span>
                    {d.bet_size > 0 && (
                      <span className="text-foreground font-medium">
                        ${d.bet_size.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-[9px] text-muted-foreground whitespace-nowrap">
                  {d.detected_at?.slice(11, 19)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function WhalePanel() {
  const { data: status } = useQuery({
    queryKey: ["whale-status"],
    queryFn: api.getWhaleStatus,
    refetchInterval: 5000,
  });
  const running = status?.running ?? false;

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Waves className="h-5 w-5 text-purple-400" />
          <h2 className="text-base font-semibold">Whale Conviction</h2>
          <StatusBadge running={running} />
        </div>
      </div>
      <p className="text-xs text-muted-foreground mb-3">
        Follows top sports bettors with LLM agent analysis. Runs as part of the
        main agent loop when enabled.
      </p>
      <p className="text-[10px] text-muted-foreground">
        Configure on the{" "}
        <a href="/agent" className="text-accent hover:underline">
          Agent page
        </a>
        . View whale watchlist on the{" "}
        <a href="/whales" className="text-accent hover:underline">
          Whales page
        </a>
        .
      </p>
    </div>
  );
}

export default function StrategiesPage() {
  return (
    <div className="mr-72 space-y-8">
      <div>
        <h1 className="text-xl font-bold tracking-tight">
          Trading Strategies
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Three independent AI-agent strategies, each with its own loop and
          controls
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <WhalePanel />
        <ScalperPanel />
      </div>

      <SniperPanel />
    </div>
  );
}
