"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  Brain,
  ChevronDown,
  ChevronRight,
  Wrench,
  MessageSquare,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Filter,
  Loader2,
} from "lucide-react";

const STRATEGY_COLORS: Record<string, string> = {
  whale_conviction: "text-purple-400 bg-purple-400/10 border-purple-400/30",
  live_scalper: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  new_market_sniper: "text-orange-400 bg-orange-400/10 border-orange-400/30",
  position_reeval: "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
};

const STRATEGY_LABELS: Record<string, string> = {
  whale_conviction: "Whale",
  live_scalper: "Scalper",
  new_market_sniper: "Sniper",
  position_reeval: "Reeval",
};

function PlanCard({ plan }: { plan: any }) {
  const [expanded, setExpanded] = useState(false);
  const chain = plan.reasoning_chain || [];
  const planJson = plan.plan_json || {};
  const orders = planJson.orders || [];
  const colorClass =
    STRATEGY_COLORS[plan.strategy] ||
    "text-muted-foreground bg-muted border-border";
  const label = STRATEGY_LABELS[plan.strategy] || plan.strategy;

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 p-4 hover:bg-muted/50 transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
        )}

        <span
          className={cn(
            "rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase",
            colorClass
          )}
        >
          {label}
        </span>

        <span className="flex-1 text-sm font-medium truncate">
          {plan.trigger_summary}
        </span>

        <div className="flex items-center gap-2 flex-shrink-0">
          {plan.executed ? (
            <CheckCircle2 className="h-4 w-4 text-success" />
          ) : plan.risk_rejection_reason ? (
            <XCircle className="h-4 w-4 text-danger" />
          ) : (
            <AlertCircle className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="text-[10px] text-muted-foreground">
            {plan.created_at?.slice(11, 19)}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-3">
          {/* Reasoning */}
          {planJson.reasoning && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Reasoning
              </p>
              <p className="text-xs text-foreground/80 leading-relaxed">
                {planJson.reasoning}
              </p>
            </div>
          )}

          {/* Confidence */}
          {planJson.confidence != null && (
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-muted-foreground">
                Confidence:
              </span>
              <div className="w-24 h-2 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${planJson.confidence * 100}%` }}
                />
              </div>
              <span className="text-xs font-bold">
                {(planJson.confidence * 100).toFixed(0)}%
              </span>
            </div>
          )}

          {/* Orders */}
          {orders.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Orders
              </p>
              <div className="space-y-1">
                {orders.map((o: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-center gap-2 rounded-lg bg-muted p-2 text-xs"
                  >
                    <span
                      className={cn(
                        "font-bold uppercase",
                        o.side === "buy" ? "text-success" : "text-danger"
                      )}
                    >
                      {o.side}
                    </span>
                    <span>${o.size?.toFixed(2)}</span>
                    <span className="text-muted-foreground">@</span>
                    <span>{o.price?.toFixed(4)}</span>
                    <span className="text-muted-foreground">|</span>
                    <span className="text-success text-[10px]">
                      TP: {o.exit_target?.toFixed(4)}
                    </span>
                    <span className="text-danger text-[10px]">
                      SL: {o.stop_loss?.toFixed(4)}
                    </span>
                    <span className="text-muted-foreground text-[10px]">
                      {o.hold_duration}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Risk Rejection */}
          {plan.risk_rejection_reason && (
            <div className="rounded-lg bg-danger/10 border border-danger/20 p-2">
              <p className="text-xs text-danger font-medium">
                Rejected: {plan.risk_rejection_reason}
              </p>
            </div>
          )}

          {/* Tool Call Chain */}
          {chain.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                Agent Steps ({chain.length})
              </p>
              <div className="space-y-1.5 max-h-48 overflow-y-auto">
                {chain.map((step: any, i: number) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-[11px] text-muted-foreground"
                  >
                    {step.type === "tool_call" ? (
                      <>
                        <Wrench className="h-3 w-3 mt-0.5 flex-shrink-0 text-accent" />
                        <span>
                          <span className="font-mono font-bold text-accent">
                            {step.tool}
                          </span>
                          ({JSON.stringify(step.args).slice(0, 80)})
                        </span>
                      </>
                    ) : step.type === "tool_result" ? (
                      <>
                        <MessageSquare className="h-3 w-3 mt-0.5 flex-shrink-0 text-muted-foreground" />
                        <span className="truncate">
                          {step.result_preview?.slice(0, 100)}...
                        </span>
                      </>
                    ) : step.type === "final_response" ? (
                      <>
                        <Brain className="h-3 w-3 mt-0.5 flex-shrink-0 text-success" />
                        <span className="text-foreground/70">
                          Final plan output
                        </span>
                      </>
                    ) : (
                      <>
                        <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0 text-danger" />
                        <span>{step.message || JSON.stringify(step)}</span>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ThoughtsPage() {
  const [filter, setFilter] = useState("");
  const { data: plans, isLoading } = useQuery({
    queryKey: ["agent-plans", filter],
    queryFn: () => api.getAgentPlans(filter, 50),
    refetchInterval: 15000,
  });

  const items = plans || [];

  return (
    <div className="mr-72 space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
          <Brain className="h-5 w-5 text-purple-400" />
          Agent Thoughts
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every agent decision with full reasoning chain, tool calls, and
          trading plans
        </p>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        {["", "whale_conviction", "live_scalper", "new_market_sniper", "position_reeval"].map(
          (key) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                filter === key
                  ? "bg-accent text-accent-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              {key
                ? STRATEGY_LABELS[key] || key
                : "All"}
            </button>
          )
        )}
      </div>

      {/* Plans */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <Brain className="mx-auto h-8 w-8 text-muted-foreground/30 mb-3" />
          <p className="text-sm text-muted-foreground">
            No agent plans yet. Start a strategy to see agent reasoning here.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((plan: any) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  );
}
