# Local Docker and Vercel + Render + Neon deployment

## Repository workflow

[P-043](https://github.com/AI20K-Build-Phase-Cohort-4/P-043) is the team source repository. Develop feature branches there and merge reviewed PRs into `develop`, including committed AI logs and evaluation evidence. [AI-Sale](https://github.com/AnCoder1310/AI-Sale) is the repository connected to the hosted Vercel and Render services; its `main` branch is the deployment target. Keep both as Git remotes in one local checkout (`origin` for P-043, `hosting` for AI-Sale).

To release, create a branch from `hosting/main`, merge the tested P-043 `develop` history into it, resolve integration conflicts, and open a PR to AI-Sale `main`. Merge commits preserve the original P-043 commits and authorship. Do not copy files between unrelated checkouts or push directly to either repository's `main`. Verify the hosting PR's CI, deployment and live product flow before considering the release complete.

## Local full app

From the repository root:

```bash
docker compose up --build -d
curl -f http://localhost:3000/health
curl -f http://localhost:3000/api/v1/status
```

Open <http://localhost:3000>. Caddy serves React and proxies `/api/*` to FastAPI. Local Docker now runs PostgreSQL with pgvector in the `postgres_data` volume; `docker compose down` retains it, while `docker compose down -v` deletes it. Existing SQLite or Chroma data is **not** migrated automatically. For local AI requests, put `OPENROUTER_API_KEY` in an untracked `.env`. Local demo accounts can be seeded with `DEMO_ADVISOR_PASSWORD` and `DEMO_MANAGER_PASSWORD` in `.env`, then `docker compose exec backend python -m scripts.seed_demo_users`. This local convenience is not the production account flow.

The images use `frontend/package-lock.json` and `requirements.lock`. After changing Python requirements, regenerate the lock with `uv pip compile --python-version 3.11 requirements.txt -o requirements.lock`.

## Low-cost production layout

| Component | Service | Persistent data |
| --- | --- | --- |
| React frontend and same-origin API rewrite | Vercel Hobby | None |
| FastAPI Docker web service | Render Free | None on local filesystem |
| Users, sessions, practice records, knowledge vectors | Neon Free PostgreSQL with pgvector | Neon database |

This layout has not been verified against the hosted services. Check current plan limits before relying on it for a live audience. AI provider usage may cost money.

## 1. Neon

Create a Neon PostgreSQL project and database. Copy its **pooled** connection string into Render's `DATABASE_URL`. Retain the TLS option (`sslmode=require`) from Neon. Keep the password in Render only. The backend creates its SQL tables and pgvector extension on startup; its first knowledge ingestion writes vectors to `knowledge_vectors` in the same database. Do not import local Chroma files: this deployment builds the vector index from the repository corpus. Keep `VECTOR_STORE_TYPE=pgvector` and the embedding model consistent across deploys. Changing the embedding model requires a planned reindex.

The application currently uses SQLAlchemy `create_all` for user/practice tables and direct DDL for the vector table. There is no schema migration framework. Back up production data and review schema changes before deploying future revisions. Neon connection and extension creation have not yet been verified against an actual Neon project.

Production startup fails visibly if the database or knowledge initialization fails, so `/health` cannot report a ready process with an empty required index. Investigate the provider/database failure and restart after fixing it; ingestion into an empty index is idempotent.

## 2. Render backend

Create a **Free Docker web service** from the repository root `Dockerfile`. Set health check path `/health`; the container listens on Render's `PORT`. Add the variables in [`.env.render.example`](../.env.render.example) to Render's Environment tab, replacing every placeholder. Use the final Vercel HTTPS origin in `CORS_ORIGINS`. Do not set `CHROMA_PERSIST_DIR` or attach a disk for this layout. Keep keys and passwords out of Git and chat.

At first startup, `BOOTSTRAP_MANAGER_USERNAME`, `BOOTSTRAP_MANAGER_DISPLAY_NAME`, and `BOOTSTRAP_MANAGER_PASSWORD` create the first manager **only if the database has no manager**. The manager must change the temporary password at first login. Once the change succeeds, remove `BOOTSTRAP_MANAGER_PASSWORD` from Render. Bootstrap never overwrites an existing manager. This MVP has no self-service password recovery, so plan recovery for the sole manager account.

The manager signs in and uses **Tài khoản** in the manager UI to create an Advisor account. The manager supplies a unique login name, display name, and temporary password, then gives the credentials to the advisor through a secure channel. Advisors cannot self-register or create accounts. On first login, advisors must change their temporary password before reaching practice or Copilot. Passwords are hashed; sessions are stored as token hashes and invalidated after password change. There is no email invitation, MFA, automated password reset, login rate limiting, or account audit trail yet. Assess these before handling sensitive production data.

## 3. Vercel frontend

Import the same Git repository as a separate Vercel project. Set Root Directory `frontend`, Framework Preset `Vite`, Build Command `npm run build`, Output Directory `dist`. Set `RENDER_BACKEND_URL` in Vercel to the Render service's public HTTPS **origin**, such as `https://<backend-name>.onrender.com`, with no path. Redeploy when it changes. `frontend/vercel.mjs` generates rewrites for `/api/*` and `/health` and fails the build if the URL is missing or invalid. No database URL or API key belongs in Vercel.

The browser calls `/api/v1` on the Vercel domain; the rewrite forwards to Render and keeps the auth cookie on the frontend origin. Preview deployments need deliberate `CORS_ORIGINS` and environment settings.

## Practice Room voice mode

The optional voice endpoints run in the same Render backend and use the same Neon `DATABASE_URL` as Practice sessions. The backend creates the additional `practice_voice_usage` table on first voice use; no recording or transcript text is stored in it. Back up Neon before the first deployment because this project does not have a schema migration framework.

For speech recognition, set `GROQ_API_KEY` in Render. For customer speech, set `GOOGLE_TTS_SERVICE_ACCOUNT_JSON` in Render to a single-line JSON service account credential, or configure Google Application Default Credentials for the backend. Enable Google Cloud Text-to-Speech and billing for that identity. Never set these keys in Vercel or commit them. Set the optional cost estimate variables from [`.env.render.example`](../.env.render.example) if the default rates need changing. See [Voice Mode](voice-mode.md) for provider and user-flow details.

After both the Render backend and Vercel frontend deploy, sign in as an Advisor on the Vercel site. Start a Practice session, record a short Vietnamese message, confirm the editable transcript, and play a customer reply. Then check the manager review's voice usage summary. A healthy `/health` response alone does not verify either provider.

## Verify the live deployment

After deployment, request the Vercel URL's `/health` and `/api/v1/status`. Log in as the bootstrap manager, change the initial password, create a test advisor, change that advisor's password, assign a practice scenario, run one Copilot and one Practice flow, approve the evaluation, and verify assignment history and knowledge retrieval after a Render restart. `/health` is process liveness; it does not prove database, model, or retrieval readiness. Record the live checks before opening a PR into `develop`.

References: [Render Free limitations](https://render.com/docs/free), [Render Docker services](https://render.com/docs/docker), [Neon pooled connections](https://neon.com/docs/connect/connection-pooling), [Neon pgvector](https://neon.com/docs/extensions/pgvector), [Vercel Vite](https://vercel.com/docs/frameworks/frontend/vite).
