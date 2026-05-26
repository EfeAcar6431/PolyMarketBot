"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Brain, Loader2, X } from "lucide-react";

interface OrderLevel {
  price: string;
  size: string;
}

function OrderBookPanel({
  bids,
  asks,
  spread,
}: {
  bids: OrderLevel[];
  asks: OrderLevel[];
  spread: string;
}) {
  const topAsks = [...asks]
    .sort((a, b) => parseFloat(a.price) - parseFloat(b.price))
    .slice(0, 8)
    .reverse();
  const topBids = [...bids]
    .sort((a, b) => parseFloat(b.price) - parseFloat(a.price))
    .slice(0, 8);

  const maxSize = Math.max(
    ...topAsks.map((l) => parseFloat(l.size)),
    ...topBids.map((l) => parseFloat(l.size)),
    1
  );

  return (
    <div className="space-y-1">
      <div className="grid grid-cols-3 text-[10px] font-medium uppercase tracking-wider text-muted-foreground px-2 pb-1">
        <span>Price</span>
        <span className="text-right">Shares</span>
        <span className="text-right">Total</span>
      </div>

      {topAsks.map((level, i) => {
        const price = parseFloat(level.price);
        const size = parseFloat(level.size);
        const fill = (size / maxSize) * 100;
        return (
          <div key={`a-${i}`} className="relative grid grid-cols-3 px-2 py-0.5 text-xs tabular-nums">
            <div
              className="absolute inset-y-0 right-0 bg-danger/8"
              style={{ width: `${fill}%` }}
            />
            <span className="relative text-danger">{(price * 100).toFixed(1)}¢</span>
            <span className="relative text-right">{size.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            <span className="relative text-right text-muted-foreground">
              ${(price * size).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </div>
        );
      })}

      <div className="flex items-center justify-center gap-2 py-1.5 text-xs">
        <span className="text-muted-foreground">Spread:</span>
        <span className="font-bold">{spread}</span>
      </div>

      {topBids.map((level, i) => {
        const price = parseFloat(level.price);
        const size = parseFloat(level.size);
        const fill = (size / maxSize) * 100;
        return (
          <div key={`b-${i}`} className="relative grid grid-cols-3 px-2 py-0.5 text-xs tabular-nums">
            <div
              className="absolute inset-y-0 right-0 bg-success/8"
              style={{ width: `${fill}%` }}
            />
            <span className="relative text-success">{(price * 100).toFixed(1)}¢</span>
            <span className="relative text-right">{size.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            <span className="relative text-right text-muted-foreground">
              ${(price * size).toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function PriceChart({ data }: { data: { t: number; p: number }[] }) {
  if (!data.length) {
    return (
      <div className="flex h-[200px] items-center justify-center text-xs text-muted-foreground">
        No price history available
      </div>
    );
  }

  const chartData = data.map((d) => ({
    time: new Date(d.t * 1000).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    }),
    price: d.p * 100,
  }));

  const last = chartData[chartData.length - 1]?.price ?? 50;
  const first = chartData[0]?.price ?? 50;
  const color = last >= first ? "#22c55e" : "#ef4444";

  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis
          dataKey="time"
          tick={{ fontSize: 10, fill: "#a1a1aa" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 10, fill: "#a1a1aa" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${v}¢`}
        />
        <Tooltip
          contentStyle={{
            background: "#111113",
            border: "1px solid #27272a",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#a1a1aa" }}
          formatter={(value) => [`${Number(value).toFixed(1)}¢`, "Price"]}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke={color}
          strokeWidth={2}
          fill="url(#priceGrad)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

interface Props {
  market: any;
  onClose: () => void;
}

export function SubMarketDetail({ market, onClose }: Props) {
  const [tab, setTab] = useState<"book" | "chart" | "analysis">("book");

  const clobTokenIds = market.clobTokenIds
    ? typeof market.clobTokenIds === "string"
      ? JSON.parse(market.clobTokenIds)
      : market.clobTokenIds
    : [];

  const tokenId = clobTokenIds[0] || "";
  const conditionId = market.conditionId || market.condition_id || market.id;

  const outcomePrices = market.outcomePrices
    ? typeof market.outcomePrices === "string"
      ? JSON.parse(market.outcomePrices)
      : market.outcomePrices
    : [];
  const yesPrice = outcomePrices[0] ? parseFloat(outcomePrices[0]) : null;
  const noPrice = outcomePrices[1] ? parseFloat(outcomePrices[1]) : null;

  const { data: bookData, isLoading: bookLoading } = useQuery({
    queryKey: ["orderbook", tokenId],
    queryFn: () => api.getOrderbook(conditionId, tokenId),
    enabled: !!tokenId && tab === "book",
  });

  const { data: historyData, isLoading: historyLoading } = useQuery({
    queryKey: ["price-history", tokenId],
    queryFn: () => api.getPriceHistory(conditionId, tokenId),
    enabled: !!tokenId && tab === "chart",
  });

  const [analysis, setAnalysis] = useState<any>(null);
  const analyzeMut = useMutation({
    mutationFn: () => api.analyzeMarket(conditionId),
    onSuccess: (data) => setAnalysis(data),
  });

  const bids = bookData?.bids || [];
  const asks = bookData?.asks || [];
  const bestBid = bids.length
    ? Math.max(...bids.map((b: OrderLevel) => parseFloat(b.price)))
    : 0;
  const bestAsk = asks.length
    ? Math.min(...asks.map((a: OrderLevel) => parseFloat(a.price)))
    : 0;
  const spread =
    bestBid && bestAsk
      ? `${((bestAsk - bestBid) * 100).toFixed(1)}¢`
      : "—";

  return (
    <div className="border-t border-border bg-muted/30">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold truncate">{market.question}</h4>
          <div className="mt-1 flex items-center gap-3">
            {yesPrice != null && (
              <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-bold text-success">
                Yes {(yesPrice * 100).toFixed(0)}¢
              </span>
            )}
            {noPrice != null && (
              <span className="rounded-md bg-danger/15 px-2 py-0.5 text-xs font-bold text-danger">
                No {(noPrice * 100).toFixed(0)}¢
              </span>
            )}
            {market.volume24hr && (
              <span className="text-[10px] text-muted-foreground">
                ${Number(market.volume24hr).toLocaleString(undefined, { maximumFractionDigits: 0 })} 24h vol
              </span>
            )}
          </div>
        </div>
        <button onClick={onClose} className="shrink-0 p-1 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex border-b border-border">
        {(["book", "chart", "analysis"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              if (t === "analysis" && !analysis && !analyzeMut.isPending) {
                analyzeMut.mutate();
              }
            }}
            className={cn(
              "px-4 py-2 text-xs font-medium transition-colors",
              tab === t
                ? "border-b-2 border-accent text-accent"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t === "book"
              ? "Order Book"
              : t === "chart"
              ? "Price Chart"
              : "AI Analysis"}
          </button>
        ))}
      </div>

      <div className="p-4">
        {tab === "book" && (
          bookLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : !tokenId ? (
            <p className="text-xs text-muted-foreground text-center py-4">
              No token ID available for this market
            </p>
          ) : (
            <OrderBookPanel bids={bids} asks={asks} spread={spread} />
          )
        )}

        {tab === "chart" && (
          historyLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <PriceChart data={historyData || []} />
          )
        )}

        {tab === "analysis" && (
          analyzeMut.isPending ? (
            <div className="flex items-center justify-center gap-2 py-8">
              <Loader2 className="h-4 w-4 animate-spin text-accent" />
              <span className="text-xs text-muted-foreground">Running AI analysis...</span>
            </div>
          ) : analysis ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    LLM Prob
                  </p>
                  <p className="mt-1 text-lg font-bold">
                    {(analysis.estimated_probability * 100).toFixed(0)}%
                  </p>
                </div>
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    Confidence
                  </p>
                  <p className="mt-1 text-lg font-bold">
                    {(analysis.confidence * 100).toFixed(0)}%
                  </p>
                </div>
                <div className="rounded-lg bg-muted p-3 text-center">
                  <p className="text-[10px] text-muted-foreground uppercase tracking-wider">
                    Edge
                  </p>
                  <p
                    className={cn(
                      "mt-1 text-lg font-bold",
                      analysis.edge > 0 ? "text-success" : "text-danger"
                    )}
                  >
                    {analysis.edge > 0 ? "+" : ""}
                    {(analysis.edge * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {analysis.reasoning}
                </p>
              </div>
            </div>
          ) : (
            <div className="flex justify-center py-8">
              <button
                onClick={() => analyzeMut.mutate()}
                className="flex items-center gap-2 rounded-lg bg-accent/15 px-4 py-2 text-xs font-medium text-accent hover:bg-accent/25"
              >
                <Brain className="h-4 w-4" />
                Run AI Analysis
              </button>
            </div>
          )
        )}
      </div>
    </div>
  );
}
