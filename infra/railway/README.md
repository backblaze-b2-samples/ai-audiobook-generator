# Railway Deployment

Deploy the web, API, worker, and Redis services on Railway.

## Setup

1. Create a new Railway project
2. Add Redis to the project. Keep it private/network-isolated and use the
   authenticated Railway connection string for `REDIS_URL`.
3. Add three services from the same repo:

### Web Service (Next.js)
- **Root Directory**: `apps/web`
- **Build Command**: `pnpm install && pnpm build`
- **Start Command**: `pnpm start`
- **Port**: `3000`

### API Service (FastAPI)
- **Root Directory**: `services/api`
- **Build Command**: `pip install --require-hashes -r requirements.lock`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **ffmpeg**: not required on the API service. Master assembly runs in the worker.

### Worker Service (RQ)
- **Root Directory**: `services/api`
- **Build Command**: `pip install --require-hashes -r requirements.lock`
- **Start Command**: `python worker.py`
- **ffmpeg**: required here. Add an `apt` package via a Nixpacks/`railway.toml`
  config (e.g. `nixpacksPlan.phases.setup.aptPkgs = ["ffmpeg"]`) or a Dockerfile
  that installs it. Without ffmpeg, chapters still render but the master is skipped.

## Environment Variables

Set these on the API service:

| Variable | Value |
|----------|-------|
| `B2_ENDPOINT` | Your B2 S3 endpoint |
| `B2_REGION` | Your B2 region (e.g. `us-west-004`) |
| `B2_APPLICATION_KEY_ID` | Your B2 application key ID |
| `B2_APPLICATION_KEY` | Your B2 application key |
| `B2_BUCKET_NAME` | Your bucket name |
| `TTS_PROVIDER` | `openai` (default) or `elevenlabs` |
| `OPENAI_API_KEY` | OpenAI key (for the default provider) |
| `ELEVENLABS_API_KEY` | ElevenLabs key (only if `TTS_PROVIDER=elevenlabs`; also `pip install elevenlabs`) |
| `TTS_DEFAULT_VOICE` | Optional default narrator voice id |
| `REDIS_URL` | Railway Redis connection string |
| `BOOK_AUTH_TOKENS` | Owner token map, e.g. `prod:generated-strong-token` |
| `API_CORS_ORIGINS` | Your web service URL (e.g., `https://web-production-xxx.up.railway.app`) |

Set the same B2, TTS, `REDIS_URL`, and `BOOK_AUTH_TOKENS` configuration on the
Worker service. Set `NARRATION_RESUME_SCAN_ENABLED=false` for the first deploy from
legacy in-process renderers, drain all old API instances, then set
`NARRATION_RESUME_SCAN_ENABLED=true` on the Worker service. Optionally tune
`NARRATION_RESUME_SCAN_BATCH_SIZE`; it controls progress logging, not a hard cap.
Keep ffmpeg installed on the Worker service only.

Set this on the Web service:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | Your API service URL (e.g., `https://api-production-xxx.up.railway.app`) |
| `NEXT_PUBLIC_BOOK_OWNER` | Owner id matching one `BOOK_AUTH_TOKENS` entry |
| `NEXT_PUBLIC_BOOK_TOKEN` | Token for that owner in this sample deployment |
