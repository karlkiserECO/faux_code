import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "faux_code",
  description: "Self-hosted multi-provider AI chat and agentic coding workbench",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
