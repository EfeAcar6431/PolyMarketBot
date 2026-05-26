"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Search,
  Bot,
  History,
  Activity,
  Waves,
  Brain,
  Crosshair,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: Search },
  { href: "/whales", label: "Whales", icon: Waves },
  { href: "/agent", label: "Agent", icon: Bot },
  { href: "/strategies", label: "Strategies", icon: TrendingUp },
  { href: "/thoughts", label: "Agent Thoughts", icon: Brain },
  { href: "/trades", label: "Trades", icon: History },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-border bg-card">
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <Activity className="h-5 w-5 text-accent" />
        <span className="text-sm font-bold tracking-tight">PolyMarketBot</span>
      </div>

      <nav className="flex-1 space-y-1 p-3">
        {NAV.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-accent/15 text-accent"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border p-3">
        <div className="rounded-lg bg-muted p-3">
          <p className="text-xs font-medium text-muted-foreground">
            Polymarket AI Agent
          </p>
          <p className="mt-1 text-[10px] text-muted-foreground/70">v1.0.0</p>
        </div>
      </div>
    </aside>
  );
}
