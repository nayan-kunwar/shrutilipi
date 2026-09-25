# ShrutiLipi

Paste a YouTube URL → get a copyable transcript. v1 = captions-only.

Monorepo: `frontend/` (Next.js, Vercel) + `backend/` (FastAPI, Render).

## Local dev (2 terminals)

Terminal 1 — backend:
```powershell
cd backend
pip install -r requirements.txt
$env:FRONTEND_URL="http://localhost:3000"
uvicorn main:app --reload --port 8000
# health: http://localhost:8000/health
```

Terminal 2 — frontend:
```powershell
cd frontend
npm install
copy .env.example .env.local
npm run dev
# app: http://localhost:3000
```

Test API directly:
```powershell
curl "http://localhost:8000/api/transcript?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

## Deploy

- **Render (backend):** New Web Service → this repo → Root Directory `backend` → Runtime Docker → env `FRONTEND_URL=https://YOUR-APP.vercel.app`
- **Vercel (frontend):** Import repo → Root Directory `frontend` → env `NEXT_PUBLIC_API_URL=https://YOUR-API.onrender.com`

## v2 (Whisper fallback)

Add `WhisperProvider` behind `TranscriptProvider` in `backend/services/providers.py`. No frontend change needed.
