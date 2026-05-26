"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn, formatUSD, timeAgo } from "@/lib/utils";
import {
  Waves,
  RefreshCw,
  Loader2,
  Eye,
  EyeOff,
  ExternalLink,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  ChevronRight,
  Check,
  X,
} from "lucide-react";

function WhaleBadge({ pnl }: { pnl: number }) {
  if (pnl >= 1_000_000)
    return (
      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-bold text-amber-500">
        MEGA
      </span>
    );
  if (pnl >= 100_000)
    return (
      <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[10px] font-bold text-accent">
        WHALE
      </span>
    );
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold text-muted-foreground">
      FISH
    </span>
  );
}

function WhaleRow({
  whale,
  isExpanded,
  onToggleExpand,
}: {
  whale: any;
  isExpanded: boolean;
  onToggleExpand: () => void;
}) {
  const qc = useQueryClient();
  const toggleMut = useMutation({
    mutationFn: () => api.toggleWhale(whale.wallet, !whale.active),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["whale-watchlist"] }),
  });

  const { data: liveTrades, isLoading: tradesLoading } = useQuery({
    queryKey: ["whale-live-trades", whale.wallet],
    queryFn: () => api.getWhaleTradesForWallet(whale.wallet, 10),
    enabled: isExpanded,
  });

  const pnl = Number(whale.pnl || 0);

  return (
    <div className="border-b border-border last:border-b-0">
      <div
        className={cn(
          "flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/50 transition-colors",
          !whale.active && "opacity-50"
        )}
        onClick={onToggleExpand}
      >
        <div className="flex-shrink-0">
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">
              {whale.username || whale.wallet.slice(0, 10) + "..."}
            </span>
            <WhaleBadge pnl={pnl} />
          </div>
          <p className="text-[10px] text-muted-foreground font-mono truncate">
            {whale.wallet}
          </p>
        </div>

        <div className="text-right flex-shrink-0">
          <p
            className={cn(
              "text-sm font-bold",
              pnl > 0 ? "text-success" : "text-danger"
            )}
          >
            {pnl >= 0 ? "+" : ""}
            {formatUSD(pnl)}
          </p>
          <p className="text-[10px] text-muted-foreground">
            {whale.category || "OVERALL"}
          </p>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleMut.mutate();
          }}
          className={cn(
            "flex-shrink-0 rounded-lg p-2 transition-colors",
            whale.active
              ? "text-success hover:bg-success/10"
              : "text-muted-foreground hover:bg-muted"
          )}
          title={whale.active ? "Disable tracking" : "Enable tracking"}
        >
          {toggleMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : whale.active ? (
            <Eye className="h-4 w-4" />
          ) : (
            <EyeOff className="h-4 w-4" />
          )}
        </button>

        <a
          href={`https://polymarket.com/profile/${whale.wallet}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex-shrink-0 rounded-lg p-2 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {isExpanded && (
        <div className="border-t border-border bg-muted/30 px-4 py-3">
          <p className="text-xs font-medium text-muted-foreground mb-2">
            Recent Trades (live from Polymarket)
          </p>
          {tradesLoading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground py-4">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading trades...
            </div>
          ) : !liveTrades || liveTrades.length === 0 ? (
            <p className="text-xs text-muted-foreground py-2">
              No recent trades found
            </p>
          ) : (
            <div className="space-y-1.5">
              {liveTrades.map((t: any, i: number) => (
                <div
                  key={i}
                  className="flex items-center gap-2 rounded-lg bg-card px-3 py-2 text-xs"
                >
                  <span
                    className={cn(
                      "font-bold",
                      t.side === "BUY" ? "text-success" : "text-danger"
                    )}
                  >
                    {t.side === "BUY" ? (
                      <ArrowUpRight className="inline h-3 w-3" />
                    ) : (
                      <ArrowDownRight className="inline h-3 w-3" />
                    )}{" "}
                    {t.side}
                  </span>
                  <span className="truncate flex-1 text-muted-foreground">
                    {t.title || t.outcome || "—"}
                  </span>
                  <span className="font-mono">
                    ${Number(t.size || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}
                  </span>
                  <span className="text-muted-foreground">
                    @{Number(t.price || 0).toFixed(2)}
                  </span>
                  <span className="text-muted-foreground/60">
                    {t.timestamp
                      ? timeAgo(new Date(t.timestamp * 1000).toISOString())
                      : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function WhaleTradesLog() {
  const { data: trades, isLoading } = useQuery({
    queryKey: ["whale-trades-log"],
    queryFn: () => api.getWhaleTrades(50),
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading whale trade log...
      </div>
    );
  }

  if (!trades || trades.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">
        No whale trades recorded yet. Refresh the watchlist and start the agent.
      </p>
    );
  }

  return (
    <div className="divide-y divide-border">
      {trades.map((t: any) => (
        <div key={t.id} className="flex items-center gap-3 px-4 py-2.5">
          <div
            className={cn(
              "flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full",
              t.followed ? "bg-success/15 text-success" : "bg-muted text-muted-foreground"
            )}
          >
            {t.followed ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold truncate">
                {t.username || t.wallet?.slice(0, 10) || "?"}
              </span>
              <span
                className={cn(
                  "text-[10px] font-bold",
                  t.side === "BUY" ? "text-success" : "text-danger"
                )}
              >
                {t.side}
              </span>
              <span className="text-xs text-muted-foreground truncate">
                {t.market_title || t.outcome || "—"}
              </span>
            </div>
            <p className="text-[10px] text-muted-foreground truncate">
              {t.follow_reason || "—"}
            </p>
          </div>
          <div className="text-right flex-shrink-0">
            <p className="text-xs font-mono">
              ${Number(t.size || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}
            </p>
            <p className="text-[10px] text-muted-foreground">
              @{Number(t.price || 0).toFixed(2)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export default function WhalesPage() {
  const qc = useQueryClient();
  const [expandedWallet, setExpandedWallet] = useState<string | null>(null);

  const { data: watchlist, isLoading } = useQuery({
    queryKey: ["whale-watchlist"],
    queryFn: () => api.getWhaleWatchlist(false),
  });

  const refreshMut = useMutation({
    mutationFn: () => api.refreshWhaleWatchlist("OVERALL", "MONTH"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["whale-watchlist"] }),
  });

  return (
    <div className="mr-72 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Waves className="h-5 w-5 text-accent" /> Whale Tracker
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Monitor top Polymarket traders and follow their moves
          </p>
        </div>
        <button
          onClick={() => refreshMut.mutate()}
          disabled={refreshMut.isPending}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-50"
        >
          {refreshMut.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh Leaderboard
        </button>
      </div>

      {/* Watchlist */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">
            Watchlist{" "}
            {watchlist && (
              <span className="text-muted-foreground font-normal">
                ({watchlist.filter((w: any) => w.active).length} active /{" "}
                {watchlist.length} total)
              </span>
            )}
          </h2>
        </div>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-8 justify-center">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading watchlist...
          </div>
        ) : !watchlist || watchlist.length === 0 ? (
          <div className="text-center py-12">
            <Waves className="h-10 w-10 text-muted-foreground/30 mx-auto mb-3" />
            <p className="text-sm text-muted-foreground mb-4">
              No whales in watchlist yet
            </p>
            <button
              onClick={() => refreshMut.mutate()}
              disabled={refreshMut.isPending}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-50"
            >
              Import from Leaderboard
            </button>
          </div>
        ) : (
          watchlist.map((whale: any) => (
            <WhaleRow
              key={whale.wallet}
              whale={whale}
              isExpanded={expandedWallet === whale.wallet}
              onToggleExpand={() =>
                setExpandedWallet(
                  expandedWallet === whale.wallet ? null : whale.wallet
                )
              }
            />
          ))
        )}
      </div>

      {/* Whale Trade Log */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">
            Whale Trade Log{" "}
            <span className="text-muted-foreground font-normal">
              (follow / skip decisions)
            </span>
          </h2>
        </div>
        <WhaleTradesLog />
      </div>
    </div>
  );
}
