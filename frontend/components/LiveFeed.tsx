"use client";

import { useFeed } from "@/app/providers";
import { cn, timeAgo } from "@/lib/utils";
import {
  ArrowUpRight,
  ArrowDownRight,
  Brain,
  AlertTriangle,
  XCircle,
  Info,
  Wifi,
  WifiOff,
  Trash2,
} from "lucide-react";

const LEVEL_CONFIG: Record<string, { icon: any; color: string }> = {
  trade: { icon: ArrowUpRight, color: "text-success" },
  info: { icon: Info, color: "text-info" },
  warning: { icon: AlertTriangle, color: "text-warning" },
  error: { icon: XCircle, color: "text-danger" },
};

export function LiveFeed() {
  const { events, connected, clearEvents } = useFeed();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Live Feed
          </span>
          <span
            className={cn(
              "flex items-center gap-1 text-[10px]",
              connected ? "text-success" : "text-danger"
            )}
          >
            {connected ? (
              <Wifi className="h-3 w-3" />
            ) : (
              <WifiOff className="h-3 w-3" />
            )}
          </span>
        </div>
        {events.length > 0 && (
          <button
            onClick={clearEvents}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {events.length === 0 ? (
          <p className="p-3 text-center text-xs text-muted-foreground">
            No activity yet
          </p>
        ) : (
          events.map((event, i) => {
            const cfg = LEVEL_CONFIG[event.level] || LEVEL_CONFIG.info;
            const Icon = cfg.icon;
            return (
              <div
                key={`${event.timestamp}-${i}`}
                className="flex gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50 transition-colors"
              >
                <Icon className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", cfg.color)} />
                <div className="min-w-0 flex-1">
                  <p className="text-xs leading-snug break-words">
                    {event.message}
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    {timeAgo(event.timestamp)}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
