import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/Sidebar";
import { LiveFeed } from "@/components/LiveFeed";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "PolyMarketBot",
  description: "AI-powered Polymarket trading agent dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="h-full bg-background text-foreground">
        <Providers>
          <div className="flex h-full">
            <Sidebar />
            <main className="ml-56 flex-1 overflow-y-auto">
              <div className="mx-auto max-w-6xl p-6">{children}</div>
            </main>
            <aside className="fixed inset-y-0 right-0 w-72 border-l border-border bg-card">
              <LiveFeed />
            </aside>
          </div>
        </Providers>
      </body>
    </html>
  );
}
