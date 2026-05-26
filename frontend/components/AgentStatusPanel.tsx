"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Play, Square, Loader2, FlaskConical, Radio } from "lucide-react";

export function AgentStatusPanel() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["agent-status"],
    queryFn: api.getAgentStatus,
  });

  const startMut = useMutation({
    mutationFn: api.startAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });
  const stopMut = useMutation({
    mutationFn: api.stopAgent,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["agent-status"] }),
  });

  const status = data?.status || "stopped";
  const isPaper = data?.config?.paper_mode !== "false";
  const isRunning = status === "running";
  const isLoading = startMut.isPending || stopMut.isPending;

  return (
    <div className="flex items-center gap-3">
      <div
        className={cn(
          "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider",
          isPaper
            ? "bg-warning/15 text-warning"
            : "bg-danger/15 text-danger"
        )}
      >
        {isPaper ? (
          <FlaskConical className="h-3 w-3" />
        ) : (
          <Radio className="h-3 w-3" />
        )}
        {isPaper ? "Paper" : "Live"}
      </div>

      <div className="flex items-center gap-2">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            isRunning ? "bg-success animate-pulse" : status === "error" ? "bg-danger" : "bg-muted-foreground"
          )}
        />
        <span className="text-xs font-medium uppercase tracking-wide">
          {status}
        </span>
      </div>
      <button
        onClick={() => (isRunning ? stopMut.mutate() : startMut.mutate())}
        disabled={isLoading}
        className={cn(
          "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
          isRunning
            ? "bg-danger/15 text-danger hover:bg-danger/25"
            : "bg-success/15 text-success hover:bg-success/25"
        )}
      >
        {isLoading ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : isRunning ? (
          <Square className="h-3 w-3" />
        ) : (
          <Play className="h-3 w-3" />
        )}
        {isRunning ? "Stop" : "Start"}
      </button>
    </div>
  );
}
