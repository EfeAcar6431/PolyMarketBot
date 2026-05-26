"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EventCard } from "@/components/MarketCard";
import { Search, Loader2 } from "lucide-react";

const SORT_OPTIONS = [
  { value: "volume24hr", label: "Volume (24h)" },
  { value: "volume", label: "Total Volume" },
  { value: "liquidity", label: "Liquidity" },
  { value: "endDate", label: "End Date" },
];

const CATEGORIES = [
  "All",
  "Sports",
  "Politics",
  "Crypto",
  "Pop Culture",
  "Business",
  "Science",
  "Tech",
];

export default function MarketsPage() {
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("volume24hr");
  const [selectedCategory, setSelectedCategory] = useState("All");

  const { data: rawResults, isLoading } = useQuery({
    queryKey: ["markets", query, sortBy],
    queryFn: () => {
      const params: Record<string, string> = { sort_by: sortBy, limit: "40" };
      if (query) params.query = query;
      return api.getMarkets(params);
    },
  });

  const events = (rawResults || []).map((item: any) => {
    if (item.markets) return item;
    return { ...item, title: item.question || item.title, markets: [item] };
  });

  const filtered =
    selectedCategory === "All"
      ? events
      : events.filter((ev: any) => {
          const cat = (ev.category || "").toLowerCase();
          return cat.includes(selectedCategory.toLowerCase());
        });

  return (
    <div className="mr-72 space-y-6">
      <div>
        <h1 className="text-xl font-bold tracking-tight">Markets</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Browse and analyze prediction markets
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search markets..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-lg border border-border bg-card pl-10 pr-4 py-2.5 text-sm text-foreground placeholder-muted-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          className="rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-foreground focus:border-accent focus:outline-none"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap gap-2">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setSelectedCategory(cat)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              selectedCategory === cat
                ? "bg-accent text-accent-foreground"
                : "bg-muted text-muted-foreground hover:bg-muted/80"
            }`}
          >
            {cat}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center">
          <p className="text-sm text-muted-foreground">No markets found</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((event: any, i: number) => (
            <EventCard key={event.id || i} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}
