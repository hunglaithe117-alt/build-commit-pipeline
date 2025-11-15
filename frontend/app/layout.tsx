import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

const navLinks = [
  { href: "/projects", label: "Projects" },
  { href: "/jobs", label: "Scan jobs" },
  { href: "/sonar-runs", label: "Scan results" },
  { href: "/failed-commits", label: "Failed commits" },
];

export const metadata: Metadata = {
  title: "Build Commit Pipeline",
  description: "Dashboard for TravisTorrent SonarQube data pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <div className="flex min-h-screen flex-col">
          <header className="border-b border-white/10 bg-slate-950 text-white">
            <div className="container flex flex-col gap-4 py-6">
              <h1 className="text-2xl font-semibold tracking-tight">Build Commit Pipeline</h1>
              <nav className="flex flex-wrap gap-2 text-sm">
                {navLinks.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-full border border-white/10 px-4 py-1.5 transition hover:bg-white/10"
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
          </header>
          <main className="container flex-1 py-10">{children}</main>
        </div>
      </body>
    </html>
  );
}
