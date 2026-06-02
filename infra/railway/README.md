# Railway Deployment

Deploy both services (web + api) on Railway.

## Setup

1. Create a new Railway project
2. Add two services from the same repo:

### Web Service (Next.js)
- **Root Directory**: `apps/web`
- **Build Command**: `pnpm install && pnpm build`
- **Start Command**: `pnpm start`
- **Port**: `3000`

### API Service (FastAPI)
- **Root Directory**: `services/api`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **ffmpeg**: the M4B master assembler shells out to `ffmpeg`. Make it available on the
  API service — add an `apt` package via a Nixpacks/`railway.toml` config (e.g.
  `nixpacksPlan.phases.setup.aptPkgs = ["ffmpeg"]`) or a Dockerfile that installs it.
  Without ffmpeg, chapters still render but the master is skipped.

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
| `API_CORS_ORIGINS` | Your web service URL (e.g., `https://web-production-xxx.up.railway.app`) |

Set this on the Web service:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | Your API service URL (e.g., `https://api-production-xxx.up.railway.app`) |
