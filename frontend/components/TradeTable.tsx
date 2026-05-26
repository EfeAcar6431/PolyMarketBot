"use client";

import { cn, formatUSD, timeAgo } from "@/lib/utils";

interface Props {
  trades: any[];
}

export function TradeTable({ trades }: Props) {
  if (!trades || trades.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">No trades yet</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="px-4 py-2.5 text-left font-medium">Date</th>
              <th className="px-4 py-2.5 text-left font-medium">Market</th>
              <th className="px-4 py-2.5 text-center font-medium">Side</th>
              <th className="px-4 py-2.5 text-right font-medium">Price</th>
              <th className="px-4 py-2.5 text-right font-medium">Size</th>
              <th className="px-4 py-2.5 text-right font-medium">P&L</th>
              <th className="px-4 py-2.5 text-center font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((trade) => (
              <tr
                key={trade.id}
                className="border-b border-border/50 hover:bg-muted/30 transition-colors"
              >
                <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">
                  {timeAgo(trade.created_at)}
                </td>
                <td className="px-4 py-3 max-w-[250px] truncate font-medium">
                  {trade.market_question || trade.market_id}
                </td>
                <td className="px-4 py-3 text-center">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-bold",
                      trade.side === "buy"
                        ? "bg-success/15 text-success"
                        : "bg-danger/15 text-danger"
                    )}
                  >
                    {trade.side.toUpperCase()}
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {(trade.price * 100).toFixed(1)}¢
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatUSD(trade.size)}
                </td>
                <td
                  className={cn(
                    "px-4 py-3 text-right font-medium tabular-nums",
                    trade.pnl > 0
                      ? "text-success"
                      : trade.pnl < 0
                      ? "text-danger"
                      : "text-muted-foreground"
                  )}
                >
                  {formatUSD(trade.pnl)}
                </td>
                <td className="px-4 py-3 text-center">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase",
                      trade.status === "filled" && "bg-success/15 text-success",
                      trade.status === "placed" && "bg-info/15 text-info",
                      trade.status === "failed" && "bg-danger/15 text-danger",
                      trade.status === "pending" && "bg-warning/15 text-warning",
                      trade.status === "paper" && "bg-warning/15 text-warning"
                    )}
                  >
                    {trade.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
