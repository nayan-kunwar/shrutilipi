"use client";

interface Props {
  url: string;
  lang: string;
  loading: boolean;
  onUrlChange: (v: string) => void;
  onLangChange: (v: string) => void;
  onSubmit: () => void;
}

export default function UrlInput({ url, lang, loading, onUrlChange, onLangChange, onSubmit }: Props) {
  return (
    <div className="w-full rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <label htmlFor="yt-url" className="mb-2 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        YouTube URL or video ID
      </label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          id="yt-url"
          type="text"
          spellCheck={false}
          placeholder="https://www.youtube.com/watch?v=...  or  youtu.be/..."
          value={url}
          onChange={(e) => onUrlChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSubmit();
          }}
          className="flex-1 rounded-xl border border-zinc-300 bg-zinc-50 px-4 py-2.5 text-sm text-zinc-900 outline-none placeholder:text-zinc-400 focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100 dark:placeholder:text-zinc-600"
        />
        <select
          aria-label="Caption language"
          value={lang}
          onChange={(e) => onLangChange(e.target.value)}
          className="rounded-xl border border-zinc-300 bg-zinc-50 px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-brand focus:ring-2 focus:ring-brand/30 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
        >
          <option value="en">English</option>
          <option value="es">Spanish</option>
          <option value="hi">Hindi</option>
          <option value="de">German</option>
          <option value="fr">French</option>
        </select>
        <button
          onClick={onSubmit}
          disabled={loading || !url.trim()}
          className="rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Fetching…" : "Get transcript"}
        </button>
      </div>
    </div>
  );
}
