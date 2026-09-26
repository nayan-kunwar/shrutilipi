"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  videoId: string;
  lang: string;
  title: string;
}

type Target = {
  name: string;
  href: string;
  icon: React.ReactNode;
};

function BubbleIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  );
}

function PlaneIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m22 2-7 20-4-9-9-4 20-7z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-10 7L2 7" />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function LetterIcon({ letter }: { letter: string }) {
  return (
    <span aria-hidden="true" className="inline-flex h-4 w-4 items-center justify-center text-xs font-bold leading-none">
      {letter}
    </span>
  );
}

export default function ShareButtons({ videoId, lang, title }: Props) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function buildLinks() {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    const url = `${origin}/?url=${encodeURIComponent(videoId)}&lang=${encodeURIComponent(lang)}`;
    const displayName = title || videoId;
    const text = `"${displayName}" — transcript via ShrutiLipi`;
    const t = encodeURIComponent(text);
    const u = encodeURIComponent(url);
    const full = encodeURIComponent(`${text} ${url}`);
    const targets: Target[] = [
      { name: "WhatsApp", href: `https://wa.me/?text=${full}`, icon: <BubbleIcon /> },
      { name: "Telegram", href: `https://t.me/share/url?url=${u}&text=${t}`, icon: <PlaneIcon /> },
      { name: "X", href: `https://twitter.com/intent/tweet?text=${t}&url=${u}`, icon: <LetterIcon letter="X" /> },
      { name: "Facebook", href: `https://www.facebook.com/sharer/sharer.php?u=${u}`, icon: <LetterIcon letter="f" /> },
      { name: "Email", href: `mailto:?subject=${encodeURIComponent(displayName)}&body=${t}%0A%0A${u}`, icon: <MailIcon /> },
    ];
    return { url, targets };
  }

  async function copyLink() {
    const { url } = buildLinks();
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setOpen(false);
    setTimeout(() => setCopied(false), 2000);
  }

  const { targets } = buildLinks();

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium transition hover:border-brand hover:text-brand dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-brand dark:hover:text-brand"
      >
        {copied ? <span className="text-brand">Link copied ✓</span> : "Share"}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-10 mt-1 w-44 rounded-xl border border-zinc-200 bg-white py-1 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          {targets.map((t) => (
            <a
              key={t.name}
              role="menuitem"
              href={t.href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-zinc-700 transition hover:bg-zinc-50 hover:text-brand dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-brand"
            >
              {t.icon}
              {t.name}
            </a>
          ))}
          <button
            role="menuitem"
            onClick={() => void copyLink()}
            className="flex w-full items-center gap-2 border-t border-zinc-200 px-3 py-2 text-left text-xs text-zinc-700 transition hover:bg-zinc-50 hover:text-brand dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-brand"
          >
            <LinkIcon />
            Copy link
          </button>
        </div>
      )}
    </div>
  );
}
