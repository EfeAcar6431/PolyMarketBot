"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Clock, DollarSign, ChevronDown, ChevronUp } from "lucide-react";
import { SubMarketDetail } from "./SubMarketDetail";

function parsePrices(market: any): { yes: number | null; no: number | null } {
  if (market.tokens?.length) {
    const yesT = market.tokens.find((t: any) => t.outcome?.toLowerCase() === "yes");
    const noT = market.tokens.find((t: any) => t.outcome?.toLowerCase() === "no");
    return {
      yes: yesT ? parseFloat(yesT.price) : null,
      no: noT ? parseFloat(noT.price) : null,
    };
  }
  if (market.outcomePrices) {
    try {
      const prices =
        typeof market.outcomePrices === "string"
          ? JSON.parse(market.outcomePrices)
          : market.outcomePrices;
      if (prices.length >= 2) {
        return { yes: parseFloat(prices[0]), no: parseFloat(prices[1]) };
      }
    } catch {}
  }
  return { yes: null, no: null };
}

function isResolved(market: any): boolean {
  const { yes } = parsePrices(market);
  if (yes === null) return false;
  return market.closed === true || market.closed === "true" || yes >= 0.99 || yes <= 0.01;
}

function SubMarketRow({
  market,
  isSelected,
  onClick,
}: {
  market: any;
  isSelected: boolean;
  onClick: () => void;
}) {
  const { yes, no } = parsePrices(market);
  const resolved = isResolved(market);

  return (
    <button
      onClick={resolved ? undefined : onClick}
      disabled={resolved}
      className={cn(
        "flex w-full items-center justify-between gap-4 px-5 py-2.5 text-left transition-colors",
        resolved
          ? "opacity-40 cursor-default"
          : "hover:bg-muted/50 cursor-pointer",
        isSelected && !resolved && "bg-accent/10 border-l-2 border-l-accent"
      )}
    >
      <span className="text-xs font-medium leading-snug flex-1 min-w-0 truncate">
        {market.question}
        {resolved && (
          <span className="ml-2 text-[10px] text-muted-foreground font-normal">
            Resolved
          </span>
        )}
      </span>
      <div className="flex items-center gap-2 shrink-0">
        {yes != null && (
          <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-bold text-success tabular-nums">
            {(yes * 100).toFixed(0)}¢
          </span>
        )}
        {no != null && (
          <span className="rounded-md bg-danger/15 px-2 py-0.5 text-xs font-bold text-danger tabular-nums">
            {(no * 100).toFixed(0)}¢
          </span>
        )}
      </div>
    </button>
  );
}

interface EventCardProps {
  event: any;
}

export function EventCard({ event }: EventCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null);

  const subMarkets: any[] = event.markets || [];
  const activeMarkets = subMarkets.filter((m) => !isResolved(m));
  const resolvedMarkets = subMarkets.filter((m) => isResolved(m));

  const topMarket = activeMarkets[0] || subMarkets[0];
  const topPrices = topMarket ? parsePrices(topMarket) : { yes: null, no: null };

  const volume = event.volume24hr || event.volume || 0;
  const endDate = event.endDate || event.end_date;
  const imageUrl = event.image;

  const selectedMarket = subMarkets.find((m) => m.id === selectedMarketId) || null;

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden transition-colors hover:border-border/80">
      <div
        className="cursor-pointer p-5 flex gap-4"
        onClick={() => {
          if (expanded) {
            setExpanded(false);
            setSelectedMarketId(null);
          } else {
            setExpanded(true);
            if (subMarkets.length === 1 && topMarket) {
              setSelectedMarketId(topMarket.id);
            }
          }
        }}
      >
        {imageUrl && (
          <img
            src={imageUrl}
            alt=""
            className="h-12 w-12 rounded-lg object-cover shrink-0 bg-muted"
          />
        )}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold leading-snug">
            {event.title || event.question}
          </h3>

          <div className="mt-2 flex flex-wrap items-center gap-3">
            {topPrices.yes != null && topMarket && (
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-muted-foreground">Top:</span>
                <span className="rounded-md bg-success/15 px-2 py-0.5 text-xs font-bold text-success">
                  {(topPrices.yes * 100).toFixed(0)}¢ Yes
                </span>
              </div>
            )}

            {subMarkets.length > 1 && (
              <span className="text-xs text-muted-foreground">
                {activeMarkets.length} active market{activeMarkets.length !== 1 ? "s" : ""}
              </span>
            )}

            {Number(volume) > 0 && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <DollarSign className="h-3 w-3" />
                {Number(volume) >= 1_000_000
                  ? `${(Number(volume) / 1_000_000).toFixed(1)}M`
                  : Number(volume) >= 1_000
                  ? `${(Number(volume) / 1_000).toFixed(0)}K`
                  : Number(volume).toLocaleString()}{" "}
                vol
              </div>
            )}

            {endDate && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                {new Date(endDate).toLocaleDateString()}
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 self-center text-muted-foreground">
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-border">
          {subMarkets.length > 1 && (
            <div className="divide-y divide-border/50">
              <div className="px-5 py-2">
                <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Active Markets ({activeMarkets.length})
                </span>
              </div>
              {activeMarkets.map((m, i) => (
                <div key={m.id || i}>
                  <SubMarketRow
                    market={m}
                    isSelected={m.id === selectedMarketId}
                    onClick={() =>
                      setSelectedMarketId(
                        m.id === selectedMarketId ? null : m.id
                      )
                    }
                  />
                  {m.id === selectedMarketId && (
                    <SubMarketDetail
                      market={m}
                      onClose={() => setSelectedMarketId(null)}
                    />
                  )}
                </div>
              ))}
              {resolvedMarkets.length > 0 && (
                <>
                  <div className="px-5 py-2">
                    <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      Resolved ({resolvedMarkets.length})
                    </span>
                  </div>
                  {resolvedMarkets.slice(0, 5).map((m, i) => (
                    <SubMarketRow
                      key={m.id || `r-${i}`}
                      market={m}
                      isSelected={false}
                      onClick={() => {}}
                    />
                  ))}
                  {resolvedMarkets.length > 5 && (
                    <div className="px-5 py-2 text-xs text-muted-foreground">
                      +{resolvedMarkets.length - 5} more resolved
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {subMarkets.length === 1 && selectedMarket && (
            <SubMarketDetail
              market={selectedMarket}
              onClose={() => setSelectedMarketId(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
