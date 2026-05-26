"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Loader2, Save } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  config: Record<string, string>;
}

const FIELDS = [
  { key: "scan_interval", label: "Scan Interval (sec)", type: "number", min: 30 },
  { key: "min_edge_threshold", label: "Min Edge Threshold", type: "number", step: 0.01, min: 0 },
  { key: "llm_weight", label: "LLM Weight", type: "number", step: 0.1, min: 0, max: 1 },
  { key: "max_position_size", label: "Max Position Size ($)", type: "number", min: 1 },
  { key: "max_total_exposure", label: "Max Total Exposure ($)", type: "number", min: 1 },
  { key: "max_daily_loss", label: "Max Daily Loss ($)", type: "number", min: 1 },
  { key: "trade_cooldown", label: "Trade Cooldown (sec)", type: "number", min: 0 },
  { key: "kelly_multiplier_default", label: "Kelly Multiplier (default)", type: "number", step: 0.05, min: 0.05, max: 2 },
  { key: "kelly_multiplier_odds", label: "Kelly Multiplier (odds)", type: "number", step: 0.05, min: 0.05, max: 2 },
  { key: "odds_min_edge", label: "Odds Min Edge", type: "number", step: 0.01, min: 0 },
  { key: "mm_order_size", label: "MM Order Size ($)", type: "number", min: 1 },
];

const STRATEGY_FIELDS = [
  { key: "whale_min_trade_size", label: "Whale Min Trade ($)", type: "number", min: 100 },
  { key: "whale_kelly_multiplier", label: "Whale Kelly Mult", type: "number", step: 0.05, min: 0.1, max: 2 },
  { key: "whale_max_agent_steps", label: "Whale Agent Steps", type: "number", min: 1, max: 10 },
  { key: "scalper_interval", label: "Scalper Interval (sec)", type: "number", min: 10, max: 300 },
  { key: "scalper_position_size", label: "Scalper Position ($)", type: "number", min: 1 },
  { key: "scalper_max_positions", label: "Scalper Max Positions", type: "number", min: 1, max: 20 },
  { key: "scalper_signal_threshold", label: "Scalper Signal Threshold", type: "number", step: 0.05, min: 0.1, max: 1 },
  { key: "scalper_target_pct", label: "Scalper Target %", type: "number", step: 0.01, min: 0.01 },
  { key: "scalper_stop_pct", label: "Scalper Stop %", type: "number", step: 0.01, min: 0.01 },
  { key: "sniper_min_edge", label: "Sniper Min Edge", type: "number", step: 0.01, min: 0.01 },
  { key: "sniper_max_bet", label: "Sniper Max Bet ($)", type: "number", min: 1 },
  { key: "sniper_kelly_multiplier", label: "Sniper Kelly Mult", type: "number", step: 0.05, min: 0.1, max: 2 },
  { key: "sniper_llm_timeout", label: "Sniper LLM Timeout (s)", type: "number", min: 3, max: 30 },
];

const TOGGLES = [
  { key: "whale_conviction_enabled", label: "Whale Conviction", description: "Follow top sports bettors with LLM agent" },
  { key: "scalper_enabled", label: "Live Scalper", description: "Statistical signals + agent for short-term trades" },
  { key: "sniper_enabled", label: "Market Sniper", description: "Detect and snipe mispriced new markets" },
  { key: "odds_comparison", label: "Odds Comparison", description: "Bet sportsbook vs Polymarket discrepancies" },
  { key: "sentiment_monitoring", label: "Sentiment Contrarian", description: "Detect and fade overreactions" },
  { key: "market_making", label: "Market Making", description: "Post two-sided limit orders" },
];

export function RiskConfigForm({ config }: Props) {
  const [form, setForm] = useState<Record<string, string>>({});
  const qc = useQueryClient();

  useEffect(() => {
    setForm(config);
  }, [config]);

  const mutation = useMutation({
    mutationFn: (data: Record<string, any>) => api.updateAgentConfig(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const allFields = [...FIELDS, ...STRATEGY_FIELDS];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const updates: Record<string, any> = {};
    for (const f of allFields) {
      if (form[f.key] !== config[f.key]) {
        updates[f.key] = Number(form[f.key]);
      }
    }
    for (const t of TOGGLES) {
      if (form[t.key] !== config[t.key]) {
        updates[t.key] = form[t.key] === "true";
      }
    }
    if (Object.keys(updates).length > 0) {
      mutation.mutate(updates);
    }
  };

  const toggleValue = (key: string) => {
    const val = form[key] ?? config[key] ?? "false";
    setForm({ ...form, [key]: val === "true" ? "false" : "true" });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Strategy Toggles */}
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Active Strategies
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {TOGGLES.map((t) => {
            const isOn = (form[t.key] ?? config[t.key] ?? "false") === "true";
            const isAgent = ["whale_conviction_enabled", "scalper_enabled", "sniper_enabled"].includes(t.key);
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => toggleValue(t.key)}
                className={cn(
                  "rounded-lg border-2 p-3 text-left transition-colors",
                  isOn
                    ? isAgent ? "border-purple-500/50 bg-purple-500/10" : "border-accent bg-accent/10"
                    : "border-border bg-muted/50 opacity-60"
                )}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold">{t.label}</span>
                  <div className="flex items-center gap-1.5">
                    {isAgent && <span className="text-[9px] font-bold uppercase text-purple-400">AI</span>}
                    <div
                      className={cn(
                        "h-3 w-6 rounded-full transition-colors",
                        isOn ? (isAgent ? "bg-purple-500" : "bg-accent") : "bg-border"
                      )}
                    >
                      <div
                        className={cn(
                          "h-3 w-3 rounded-full bg-white transition-transform",
                          isOn ? "translate-x-3" : "translate-x-0"
                        )}
                      />
                    </div>
                  </div>
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  {t.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      {/* Core Parameters */}
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Core Parameters
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {f.label}
              </label>
              <input
                type={f.type}
                step={f.step}
                min={f.min}
                max={f.max}
                value={form[f.key] || ""}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Strategy-Specific Parameters */}
      <div>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Strategy Parameters
        </p>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {STRATEGY_FIELDS.map((f) => (
            <div key={f.key}>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                {f.label}
              </label>
              <input
                type={f.type}
                step={f.step}
                min={f.min}
                max={f.max}
                value={form[f.key] || ""}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground hover:bg-accent/90 transition-colors disabled:opacity-50"
      >
        {mutation.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        Save Configuration
      </button>
    </form>
  );
}
