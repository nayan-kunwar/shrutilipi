import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ShrutiLipi — YouTube URL to transcript",
  description: "Paste a YouTube URL and get a copyable transcript.",
};

const themeScript = `
(function () {
  try {
    var t = localStorage.getItem("shrutilipi-theme");
    if (t === "light") document.documentElement.classList.remove("dark");
    else document.documentElement.classList.add("dark");
  } catch (e) {
    document.documentElement.classList.add("dark");
  }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
