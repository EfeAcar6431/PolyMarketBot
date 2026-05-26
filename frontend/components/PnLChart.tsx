"use client";

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface DataPoint {
  date: string;
  pnl: number;
  cumulative_pnl: number;
}

interface Props {
  data: DataPoint[];
  height?: number;
}

export function PnLChart({ data, height = 260 }: Props) {
  if (!data || data.length === 0) {
    return (
      <div
        className="rounded-xl border border-border bg-card flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-sm text-muted-foreground">No P&L data yet</p>
      </div>
    );
  }

  const lastPnl = data[data.length - 1]?.cumulative_pnl ?? 0;
  const color = lastPnl >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h3 className="mb-3 text-sm font-semibold">Cumulative P&L</h3>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          <defs>
            <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.3} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: "#a1a1aa" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#a1a1aa" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `$${v}`}
          />
          <Tooltip
            contentStyle={{
              background: "#111113",
              border: "1px solid #27272a",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#a1a1aa" }}
            formatter={(value) => [`$${Number(value).toFixed(2)}`, "P&L"]}
          />
          <Area
            type="monotone"
            dataKey="cumulative_pnl"
            stroke={color}
            strokeWidth={2}
            fill="url(#pnlGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
