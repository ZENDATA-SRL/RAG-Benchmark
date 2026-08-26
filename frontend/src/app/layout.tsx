import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Benchmark",
  description: "RAG benchmark frontend",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" data-theme="light" className="h-full antialiased">
      <body className="min-h-full bg-bg text-text-primary">{children}</body>
    </html>
  );
}
