"use client";

import { formatUSD } from "@/lib/utils";

interface Props {
  positions: any[];
}

export function PositionsTable({ positions }: Props) {
  if (!positions || positions.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-8 text-center">
        <p className="text-sm text-muted-foreground">No active positions</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="border-b border-border px-5 py-3">
        <h3 className="text-sm font-semibold">Active Positions</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th className="px-5 py-2.5 text-left font-medium">Market</th>
              <th className="px-5 py-2.5 text-right font-medium">Side</th>
              <th className="px-5 py-2.5 text-right font-medium">Size</th>
              <th className="px-5 py-2.5 text-right font-medium">Avg Price</th>
              <th className="px-5 py-2.5 text-right font-medium">Current</th>
              <th className="px-5 py-2.5 text-right font-medium">P&L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos: any, i: number) => (
              <tr
                key={pos.asset || i}
                className="border-b border-border/50 hover:bg-muted/30 transition-colors"
              >
                <td className="px-5 py-3 font-medium max-w-[300px] truncate">
                  {pos.title || pos.asset || `Position ${i + 1}`}
                </td>
                <td className="px-5 py-3 text-right">
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium">
                    {pos.side || "YES"}
                  </span>
                </td>
                <td className="px-5 py-3 text-right">{pos.size || "—"}</td>
                <td className="px-5 py-3 text-right">
                  {pos.avgPrice ? formatUSD(pos.avgPrice) : "—"}
                </td>
                <td className="px-5 py-3 text-right">
                  {pos.currentPrice ? formatUSD(pos.currentPrice) : "—"}
                </td>
                <td className="px-5 py-3 text-right font-medium">
                  {pos.pnl != null ? (
                    <span className={pos.pnl >= 0 ? "text-success" : "text-danger"}>
                      {formatUSD(pos.pnl)}
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
