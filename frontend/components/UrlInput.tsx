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
    <div className="w-full rounded-2xl border border-zinc-800 bg-zinc-900 p-4 shadow-sm">
      <label htmlFor="yt-url" className="mb-2 block text-sm font-medium text-zinc-300">
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
          className="flex-1 rounded-xl border border-zinc-700 bg-zinc-950 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-600 focus:border-zinc-500"
        />
        <select
          aria-label="Caption language"
          value={lang}
          onChange={(e) => onLangChange(e.target.value)}
          className="rounded-xl border border-zinc-700 bg-zinc-950 px-3 py-2.5 text-sm outline-none focus:border-zinc-500"
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
          className="rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-black transition disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Fetching…" : "Get transcript"}
        </button>
      </div>
      <p className="mt-2 text-xs text-zinc-500">
        v1 uses YouTube captions. Videos without captions will show an error.
      </p>
    </div>
  );
}
