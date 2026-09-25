import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShrutiLipi — YouTube URL to transcript",
  description: "Paste a YouTube URL and get a copyable transcript.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
