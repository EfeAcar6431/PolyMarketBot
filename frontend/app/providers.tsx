"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useState, type ReactNode } from "react";
import { useWebSocketFeed, type FeedEvent } from "@/lib/ws";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 15000,
      retry: 1,
      staleTime: 5000,
    },
  },
});

interface FeedContextValue {
  events: FeedEvent[];
  connected: boolean;
  clearEvents: () => void;
}

const FeedContext = createContext<FeedContextValue>({
  events: [],
  connected: false,
  clearEvents: () => {},
});

export const useFeed = () => useContext(FeedContext);

function FeedProvider({ children }: { children: ReactNode }) {
  const feed = useWebSocketFeed();
  return <FeedContext.Provider value={feed}>{children}</FeedContext.Provider>;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <FeedProvider>{children}</FeedProvider>
    </QueryClientProvider>
  );
}
