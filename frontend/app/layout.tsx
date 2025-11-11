import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Build Commit Pipeline",
  description: "Dashboard for TravisTorrent SonarQube data pipeline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <h1>Build Commit Pipeline</h1>
          <nav>
            <a href="/data-sources">Nguồn dữ liệu</a>
            <a href="/jobs">Thu thập</a>
            <a href="/sonar-runs">SonarQube</a>
            <a href="/outputs">Dữ liệu đầu ra</a>
          </nav>
        </header>
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
