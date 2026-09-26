import type { Metadata } from "next";
import "./globals.css";

const SITE_URL = "https://frontend-six-woad-540yl4bn2c.vercel.app";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "ShrutiLipi — YouTube to text: transcript, copy & download",
    template: "%s — ShrutiLipi",
  },
  description:
    "Paste a YouTube URL and get a clean transcript instantly — copy it, download as .txt, or share the link. Free YouTube transcript viewer with timestamps.",
  keywords: [
    "youtube to text",
    "youtube transcript",
    "youtube transcript downloader",
    "youtube video to text",
    "youtube captions",
    "free transcript",
    "youtube transcript with timestamps",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    title: "ShrutiLipi — YouTube to text: transcript, copy & download",
    description:
      "Paste a YouTube URL and get a clean transcript instantly — copy it, download as .txt, or share the link.",
    url: SITE_URL,
    siteName: "ShrutiLipi",
    type: "website",
  },
  twitter: {
    card: "summary",
    title: "ShrutiLipi — YouTube to text: transcript, copy & download",
    description:
      "Paste a YouTube URL and get a clean transcript instantly — copy it, download as .txt, or share the link.",
  },
  robots: { index: true, follow: true },
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
