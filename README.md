# Task API

![CI](https://github.com/apogano/taskapi/actions/workflows/ci.yml/badge.svg)

A multi-user task management REST API built with FastAPI and PostgreSQL, deployed to Google Cloud Run through an automated CI/CD pipeline.

I built it as a hands-on project to learn production-style backend development: layered architecture, database migrations, authentication, testing, structured logging and cloud deployment.

## Features

- JWT authentication: register, login, `/users/me`, with argon2 password hashing
- Refresh token rotation with theft detection: each refresh token is single-use; reusing an already-rotated token revokes the whole token family
- Two client modes: native clients (mobile, CLI) get the refresh token in the JSON body, browsers only ever receive it as an `httpOnly` cookie that JavaScript cannot read
- Task CRUD with filtering (`done`) and pagination (`limit`, `offset`)
- Per-user data isolation: a user can only see and modify their own tasks
- Database migrations with Alembic
- Structured JSON logging, with a request ID on every request, response and log line
- Consistent error handling: unexpected errors return a generic 500 and never leak internals
- Tests run against a real PostgreSQL database, each test isolated in a rolled-back transaction
- CI/CD with GitHub Actions and keyless authentication to GCP (Workload Identity Federation)
- A scheduled Cloud Run Job clears expired and revoked refresh tokens daily
- Rate limiting on registration, login and refresh (shared between both client modes), enforced per IP and, for login, also per account, backed by PostgreSQL so it stays correct across multiple instances
- File attachments on tasks, stored in Cloud Storage: the API never handles file bytes, it only issues short-lived signed URLs for the client to upload to and download from directly
- A second scheduled Cloud Run Job clears attachments that were never confirmed after upload
- Alerting on elevated 5xx rates and on the service being unreachable, with the alert email linking back to the logs via the request ID

## Tech stack

| Area | Tools |
|---|---|
| API | FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2.0, Alembic, psycopg 3 |
| Auth | PyJWT, pwdlib (argon2) |
| Tooling | uv, pytest, ruff |
| Runtime | Docker, Google Cloud Run, Cloud SQL, Cloud Storage, Secret Manager, Artifact Registry |
| Operations | Cloud Scheduler, Cloud Monitoring, Cloud Logging |
| CI/CD | GitHub Actions, Workload Identity Federation |

## API overview

| Method | Path | Description | Auth |
|---|---|---|---|
| `POST` | `/auth/register` | Create an account | no |
| `POST` | `/auth/login` | Native clients. OAuth2 password form (`username` is the email), returns an access + refresh token pair in JSON | no |
| `POST` | `/auth/refresh` | Native clients. Exchange a refresh token (JSON body) for a new pair | no (refresh token in body) |
| `POST` | `/auth/logout` | Native clients. Revoke a refresh token (JSON body) | no (refresh token in body) |
| `POST` | `/auth/web/login` | Browsers. Same form; returns the access token in JSON and sets the refresh token as an `httpOnly` cookie | no |
| `POST` | `/auth/web/refresh` | Browsers. Rotates the refresh token cookie, returns a new access token | no (refresh token cookie) |
| `POST` | `/auth/web/logout` | Browsers. Revokes the refresh token and clears the cookie | no (refresh token cookie) |
| `GET` | `/users/me` | Current user | yes |
| `POST` | `/tasks` | Create a task | yes |
| `GET` | `/tasks` | List own tasks, paginated. Query: `done`, `limit` (1-100, default 50), `offset` | yes |
| `GET` | `/tasks/{id}` | Get one task | yes |
| `PATCH` | `/tasks/{id}` | Partial update | yes |
| `DELETE` | `/tasks/{id}` | Delete a task | yes |
| `GET` | `/tasks/{id}/attachments` | List a task's uploaded attachments, paginated | yes |
| `POST` | `/tasks/{id}/attachments` | Create a pending attachment, returns a signed upload URL | yes |
| `POST` | `/tasks/{id}/attachments/{attachment_id}/confirm` | Confirm an upload finished; validates the file size | yes |
| `GET` | `/tasks/{id}/attachments/{attachment_id}/download-url` | Get a signed download URL (only once uploaded) | yes |
| `DELETE` | `/tasks/{id}/attachments/{attachment_id}` | Delete an attachment, from storage and the database | yes |
| `GET` | `/health` | Liveness check (does not touch the database) | no |

"Auth" here means the bearer access token on the `Authorization` header, which works identically for both client modes. The refresh and logout endpoints instead operate on a refresh token: in the JSON body for native clients, in a cookie for browsers. The two modes never mix — see Design notes.

Attachments are a three-step flow: `POST .../attachments` creates the record and returns a signed URL; the client `PUT`s the file straight to that URL (never through this API); then `POST .../confirm` checks the uploaded file's real size against `ATTACHMENT_MAX_SIZE_MB` and marks it ready. `download-url` and `DELETE` work the same way — the client talks to Cloud Storage directly using the URL the API hands it.

Registration, both login endpoints and both refresh endpoints are rate limited and return `429` with a `Retry-After` header once the limit is exceeded.

List endpoints return a page envelope rather than a bare array, so a client can tell how much more there is to fetch:

```json
{ "items": [...], "total": 142, "limit": 50, "offset": 0 }
```

`total` is the count of everything matching the current filters, not the size of the page.

Interactive docs are available at `/docs` when `ENABLE_DOCS=true`. They are disabled by default, so they are off in production.

```bash
# Register, log in, create and list tasks
curl -X POST localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"correct-horse-battery"}'

TOKENS=$(curl -s -X POST localhost:8000/auth/login \
  -d "username=alice@example.com&password=correct-horse-battery")
ACCESS_TOKEN=$(echo $TOKENS | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
REFRESH_TOKEN=$(echo $TOKENS | python -c "import sys, json; print(json.load(sys.stdin)['refresh_token'])")

curl -X POST localhost:8000/tasks \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Write the README"}'

# Returns {"items": [...], "total": N, "limit": 10, "offset": 0}
curl "localhost:8000/tasks?done=false&limit=10" -H "Authorization: Bearer $ACCESS_TOKEN"

# The access token expires quickly; get a new pair without logging in again.
# The old refresh token becomes invalid the moment this call succeeds.
curl -X POST localhost:8000/auth/refresh \
  -H "Content-Type: application/json" -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}"
```

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Docker. uv installs the right Python version (3.13+) for you.

```bash
git clone https://github.com/apogano/taskapi.git
cd taskapi

# 1. Configuration: create a .env file (see the table below)
cat > .env <<'EOF'
DATABASE_URL=postgresql+psycopg://taskapi:taskapi@localhost:5432/taskapi
SECRET_KEY=replace-me
ENABLE_DOCS=true
# Local dev runs over plain http, where a Secure cookie would never be stored
REFRESH_COOKIE_SECURE=false
EOF

# Generate a real secret key and paste it into .env
uv run python -c "import secrets; print(secrets.token_hex(32))"

# 2. Start PostgreSQL
docker compose up -d

# 3. Install dependencies and apply migrations
uv sync
uv run alembic upgrade head

# 4. Run the API
uv run uvicorn app.main:app --reload
```

The API is now on http://localhost:8000 and, with `ENABLE_DOCS=true`, the docs on http://localhost:8000/docs.

Everything except attachments works at this point. Attachments sign URLs through the IAM Credentials API rather than a local private key (see Design notes), so they also work locally, but need one-time setup:

```bash
gcloud auth application-default login
gcloud iam service-accounts add-iam-policy-binding \
  taskapi-run@your-project-id.iam.gserviceaccount.com \
  --member="user:your-email@example.com" --role="roles/iam.serviceAccountTokenCreator"
```

then add to `.env`:
```
GCS_BUCKET_NAME=your-project-id-attachments
GCS_SIGNER_SERVICE_ACCOUNT=taskapi-run@your-project-id.iam.gserviceaccount.com
```

### Configuration

Settings are read from environment variables (or from `.env` locally).

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | required | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/db` |
| `SECRET_KEY` | required | Key used to sign JWTs. Never commit it |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token (JWT) lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |
| `REFRESH_COOKIE_NAME` | `refresh_token` | Name of the browser refresh token cookie |
| `REFRESH_COOKIE_SECURE` | `true` | Send the cookie over HTTPS only; set `false` for local http development |
| `REFRESH_COOKIE_SAMESITE` | `lax` | Cookie `SameSite` policy |
| `REFRESH_COOKIE_PATH` | `/api/auth/web` | Cookie path, as seen by the browser through the frontend's `/api` proxy |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOG_JSON` | `false` | JSON logs (used on Cloud Run) instead of plain text |
| `ENABLE_DOCS` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |
| `RATE_LIMIT_BACKEND` | `postgres` | Rate limit storage backend (see Design notes) |
| `RATE_LIMIT_LOGIN_ATTEMPTS` / `RATE_LIMIT_LOGIN_WINDOW_SECONDS` | `5` / `900` | Per-IP login attempts |
| `RATE_LIMIT_LOGIN_ACCOUNT_ATTEMPTS` / `RATE_LIMIT_LOGIN_ACCOUNT_WINDOW_SECONDS` | `10` / `900` | Per-account login attempts |
| `RATE_LIMIT_REGISTER_ATTEMPTS` / `RATE_LIMIT_REGISTER_WINDOW_SECONDS` | `3` / `3600` | Per-IP registration attempts |
| `RATE_LIMIT_REFRESH_ATTEMPTS` / `RATE_LIMIT_REFRESH_WINDOW_SECONDS` | `20` / `900` | Per-IP refresh attempts |
| `GCS_BUCKET_NAME` | required for attachments | Cloud Storage bucket for attachments |
| `GCS_SIGNER_SERVICE_ACCOUNT` | required for attachments | Service account used to sign upload/download URLs (see Design notes) |
| `ATTACHMENT_UPLOAD_URL_EXPIRE_MINUTES` / `ATTACHMENT_DOWNLOAD_URL_EXPIRE_MINUTES` | `15` / `15` | Signed URL lifetime |
| `ATTACHMENT_MAX_SIZE_MB` | `25` | Rejected (and deleted) at confirm time if exceeded |

## Development

### Tests and linting

```bash
docker compose up -d        # tests need PostgreSQL
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
```

The test suite creates its own `taskapi_test` database next to the development one. Every test runs inside a transaction that is rolled back at the end, so tests never affect each other or your development data.

### Migrations

```bash
# After changing a model
uv run alembic revision --autogenerate -m "describe the change"
# Read the generated file in migrations/versions/ before applying it
uv run alembic upgrade head

uv run alembic downgrade -1   # go back one revision
uv run alembic check          # fails if models and migrations are out of sync
```

Rules I follow so that deployments stay safe:

- Migrations are additive: new columns are nullable or have a `server_default`. Column removals and renames are split across two deployments.
- New models must be imported in `app/models/__init__.py`, otherwise Alembic will not see them.

## Project structure

```
app/
├── main.py            # app assembly: logging, middleware, error handlers, routers
├── config.py          # settings from environment variables
├── database.py        # engine, session, Base
├── security.py        # password hashing and JWT helpers
├── cookies.py         # refresh token cookie: set/clear with consistent attributes
├── logging_config.py  # text/JSON logging with request ID
├── middleware.py      # request ID, request log, catch-all 500
├── errors.py          # domain exceptions -> HTTP responses
├── cli.py             # maintenance commands (stale token/attachment cleanup), run outside the request cycle
├── storage.py         # Cloud Storage signed URL generation (IAM-based signing)
├── rate_limiting/     # RateLimiter interface + PostgreSQL implementation
├── dependencies/      # FastAPI dependency providers (services, current user)
├── routers/           # HTTP layer only
├── services/          # business logic and transaction boundaries
├── repositories/      # database queries only
├── models/            # SQLAlchemy models (Task, User, RefreshToken, Attachment)
└── schemas/           # Pydantic request/response models
migrations/            # Alembic
tests/
infra/cleanup-policy.json   # Artifact Registry cleanup policy
.github/workflows/ci.yml    # CI/CD pipeline
```

## Design notes

- **Layers.** Routers handle HTTP, services hold business rules and decide when to commit, repositories only run queries. Services raise domain exceptions (`TaskNotFoundError`) and know nothing about HTTP. `errors.py` translates them to status codes, so the same services could be reused from a CLI or a background job.
- **Dependency injection.** Repositories and services are provided through FastAPI dependencies, so tests can substitute fakes.
- **Ownership is enforced in the query.** Every task query filters by `owner_id`. Someone else's task returns `404`, not `403`, so its existence is not revealed.
- **The client never sends an owner.** It is taken from the token.
- **Authentication details.** Login returns the same error for an unknown email and a wrong password, and spends the same time hashing in both cases. Emails are stored lowercase. Registration races are resolved by the database's unique constraint (`409`).
- **Refresh token rotation.** Refresh tokens are random values, stored in the database only as a SHA-256 hash (never as plain text, unlike the JWT access token which is never persisted at all). Each successful `/auth/refresh` call revokes the token just used and issues a new one in its place, so a refresh token works exactly once. Every token belongs to a `family_id` created at login. If a token that has already been rotated is presented again — the signature of a stolen, replayed token — the entire family is revoked, logging that user out on every device until they log in again. A separate `taskapi-cleanup-tokens` Cloud Run Job, triggered daily by Cloud Scheduler, deletes expired and long-revoked rows so the table doesn't grow unbounded; revoked rows are kept for a short grace period before deletion in case they are needed to investigate an incident.
- **Two client modes, kept strictly apart.** Browsers have no storage that JavaScript can't read, so any XSS on the page could steal a refresh token kept in localStorage or memory. The `httpOnly` cookie is the one place a browser holds something scripts cannot touch. Native apps have OS-level secure storage (Keychain, Keystore) and no use for cookies, so they get the token in JSON. The rule is: a token that arrives as a cookie leaves only as a cookie, and one that arrives in the body leaves only in the body. A single endpoint accepting either and letting the client choose the response format would undo the protection — an injected script could call it with the cookie the browser attaches automatically and ask for JSON back. Separate `/auth/*` and `/auth/web/*` endpoints enforce this structurally, and tests assert that neither falls back to the other's channel. Both share the same rate limit keys, so alternating between them buys an attacker nothing.
- **Cookie scope and CSRF.** The cookie is `httpOnly`, `Secure`, `SameSite=Lax` and scoped to `Path=/api/auth/web`, so the browser sends it only to the three web auth endpoints — not to `/tasks` or anything else. `SameSite=Lax` is enough against CSRF here because the frontend proxies `/api/*` to this service, so the browser sees a single origin and the cookie is first-party. Serving the frontend from a different origin would require `SameSite=None` and explicit CSRF tokens. A failed web refresh also clears the cookie, so the browser stops sending a dead token; native failures never set cookies.
- **Logging.** One structured log line per request (method, path, status, duration), never bodies, query strings, passwords or tokens. The `X-Request-ID` header is accepted only if it is short and alphanumeric, to prevent log injection.
- **Task ids are UUIDs**, so they are not guessable or enumerable.
- **Attachments never pass through the API.** `POST .../attachments` only creates a database row (status `pending`) and returns a signed Cloud Storage URL; the client uploads directly to Cloud Storage, and `confirm` is what turns the row into `uploaded`, after checking the real object size. This keeps large file bytes off the Cloud Run instance entirely — it only ever issues and validates URLs. A `pending` row whose upload never gets confirmed (abandoned upload, crashed client) is cleaned up daily by `taskapi-cleanup-attachments`, which also removes the underlying object if one was partially uploaded. Listing a task's attachments returns only confirmed ones — `pending` is internal bookkeeping, not something a client should have to reason about.
- **Signing without a private key.** Cloud Run's service account credentials have no private key to sign with locally (consistent with the keyless setup used everywhere else in this project), so `app/storage.py` routes signing through the IAM Credentials API's `signBlob`, authenticated as the service account itself. This needs one extra IAM grant beyond normal Storage access: `roles/iam.serviceAccountTokenCreator` on the service account, for itself. The same code path works unchanged locally, where it works by impersonating that service account via your own `gcloud auth application-default login` identity.
- **Rate limiting is behind a `RateLimiter` interface** (`app/rate_limiting/base.py`) with a single `hit(key, limit, window_seconds)` method. The only implementation today is PostgreSQL-backed, using an atomic `INSERT ... ON CONFLICT DO UPDATE count = count + 1` fixed-window counter, which stays correct under concurrent requests across multiple Cloud Run instances without needing a lock or a read-then-write round trip. Redis would be the conventional choice for this, but it requires an always-on Memorystore instance (no free tier, no scale-to-zero) plus a Serverless VPC Access connector for Cloud Run to reach it — not worth the cost and complexity at this project's scale when Postgres, which is already there, does the job correctly. The interface means swapping in a Redis-backed implementation later touches one dependency provider, not the endpoints. Login is protected by two independent limits: per-IP (stops one IP hammering many accounts) and per-account (stops one account being hammered from many IPs, e.g. a botnet); the account-scoped key is the submitted email as-is, so the check never has to look up whether the account exists.

## Deployment

```mermaid
flowchart LR
    PR["Pull request"] --> CI["Ruff, pytest, migration check"]
    CI --> Merge["Merge to main"]
    Merge --> Build["Build and push image"]
    Build --> Migrate["Cloud Run Job: alembic upgrade head"]
    Migrate --> Cleanup["Update cleanup job images"]
    Cleanup --> Deploy["Deploy new revision"]
    Deploy --> Smoke["Smoke test: GET /health"]
    Scheduler["Cloud Scheduler, daily"] -.-> CleanupTokens["taskapi-cleanup-tokens runs"]
    Scheduler -.-> CleanupAttachments["taskapi-cleanup-attachments runs"]
```

**Runtime.** The API runs on Cloud Run and connects to Cloud SQL (PostgreSQL) through the Cloud SQL unix socket, with no public database access. `SECRET_KEY` and `DATABASE_URL` come from Secret Manager. The container runs as a non-root user and the image contains no secrets.

**On every pull request**, the workflow runs `ruff check`, `ruff format --check`, the test suite on a PostgreSQL service container, and applies all migrations to an empty database followed by `alembic check`. The tests create the schema with `create_all` for speed, so this last step is what verifies the migrations themselves.

**On every merge to `main`**, if the checks pass, the workflow builds the image (tagged with the commit SHA), runs the migrations as a Cloud Run Job, points both cleanup jobs at the same new image, deploys the new revision and calls `/health`. Migrations run before the deploy, so a failed migration leaves the previous version serving traffic. Deployments are serialized with a `concurrency` group.

**Scheduled maintenance.** `taskapi-cleanup-tokens` and `taskapi-cleanup-attachments` are Cloud Run Jobs built from the same image as the service, run with `python -m app.cli <command>` instead of `uvicorn`. Cloud Scheduler triggers invoke them once a day — the former deletes expired and long-revoked refresh tokens, the latter deletes attachment rows (and any partially-uploaded object) whose upload was never confirmed. Both are kept up to date by the deploy pipeline above rather than by their own build step.

**Least privilege.** Two service accounts with separate roles:

| Service account | Purpose | Permissions |
|---|---|---|
| `taskapi-run` | Runs the app | Cloud SQL Client, access to the two secrets |
| `github-deployer` | Used by GitHub Actions | Cloud Run Developer, write access to the Artifact Registry repository, act as `taskapi-run` |

GitHub authenticates through **Workload Identity Federation**, so no service account key exists anywhere. The provider only accepts tokens from this repository on the `main` branch.

**Cleanup.** Artifact Registry keeps the 5 most recent images and deletes older ones after 30 days (`infra/cleanup-policy.json`). The 5 kept images cover rollbacks.

### Monitoring

Two alerts, both notifying by email:

| Alert | Catches | Config |
|---|---|---|
| Elevated 5xx rate | More than 3 server errors in 5 minutes | `infra/alert-5xx.yaml` |
| Uptime failure | `/health` unreachable, checked every 5 minutes from Europe | `infra/uptime-health.yaml` |

They cover different failures on purpose. The 5xx alert reads Cloud Run's own `request_count` metric rather than the application's logs, so it still fires when a container crashes or times out before it can log anything. But a service that is fully down serves no requests at all, so that metric goes quiet rather than spiking — which is what the uptime check is for.

The alert email includes the exact `gcloud logging read` command to run, and every error log line carries the `request_id` that was also returned in the response's `X-Request-ID` header, so a failure a user reports can be traced straight to its stack trace.

The uptime check was created in the Cloud Console; the YAML in `infra/` is an export of what exists, kept as documentation rather than as an importable config. The 5-minute interval is deliberate: checking more often would keep an instance permanently warm and defeat Cloud Run's scale-to-zero.

### Rollback

```bash
gcloud run revisions list --service taskapi --region $REGION
gcloud run services update-traffic taskapi --region $REGION \
  --to-revisions=REVISION_NAME=100
```

A rollback does not undo migrations, which is why they are kept additive.

### One-time cloud setup

<details>
<summary>Commands to recreate the environment from scratch</summary>

Replace `PROJECT_ID`, `GITHUB_REPO` (`user/repo`) and the region with your own values. Cloud SQL is billed while the instance exists, so set a budget alert first.

```bash
export PROJECT_ID=your-project-id
export REGION=europe-west1
export GITHUB_REPO=your-user/taskapi

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com \
  secretmanager.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

# Database
gcloud sql instances create taskapi-db --database-version=POSTGRES_16 \
  --edition=ENTERPRISE --tier=db-f1-micro --region=$REGION
gcloud sql databases create taskapi --instance=taskapi-db
DB_PASSWORD=$(openssl rand -hex 24)
gcloud sql users create taskapi --instance=taskapi-db --password="$DB_PASSWORD"

# Secrets
CONN=$(gcloud sql instances describe taskapi-db --format='value(connectionName)')
printf %s "postgresql+psycopg://taskapi:${DB_PASSWORD}@/taskapi?host=/cloudsql/${CONN}" \
  | gcloud secrets create database-url --data-file=-
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create secret-key --data-file=-

# Runtime service account
gcloud iam service-accounts create taskapi-run --display-name="Task API runtime"
SA=taskapi-run@${PROJECT_ID}.iam.gserviceaccount.com
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SA" --role="roles/cloudsql.client"
for s in database-url secret-key; do
  gcloud secrets add-iam-policy-binding $s \
    --member="serviceAccount:$SA" --role="roles/secretmanager.secretAccessor"
done

# Image repository and cleanup policy
gcloud artifacts repositories create taskapi --repository-format=docker --location=$REGION
gcloud artifacts repositories set-cleanup-policies taskapi \
  --location=$REGION --policy=infra/cleanup-policy.json --no-dry-run

# Attachments: private bucket, plus the signing grant that lets the service
# account sign URLs via the IAM Credentials API (it has no private key)
gcloud storage buckets create gs://${PROJECT_ID}-attachments \
  --location=$REGION --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-attachments \
  --member="serviceAccount:$SA" --role="roles/storage.objectAdmin"
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member="serviceAccount:$SA" --role="roles/iam.serviceAccountTokenCreator"
gcloud services enable iamcredentials.googleapis.com

# First deployment. It stores the service configuration (service account,
# secrets, Cloud SQL, env vars); the pipeline later only changes the image.
gcloud run deploy taskapi --source . --region $REGION \
  --service-account $SA --add-cloudsql-instances $CONN \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars LOG_JSON=true,GCS_BUCKET_NAME=${PROJECT_ID}-attachments,GCS_SIGNER_SERVICE_ACCOUNT=$SA \
  --max-instances 2 --allow-unauthenticated

# Migration job (same image as the service)
IMAGE=$(gcloud run services describe taskapi --region $REGION \
  --format='value(spec.template.spec.containers[0].image)')
gcloud run jobs create taskapi-migrate --image $IMAGE --region $REGION \
  --service-account $SA --set-cloudsql-instances $CONN \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --command alembic --args upgrade,head
gcloud run jobs execute taskapi-migrate --region $REGION --wait

# Cleanup jobs (same image, run the CLI instead of the server). cli.py takes
# the command to run as its argument.
gcloud run jobs create taskapi-cleanup-tokens --image=$IMAGE --region=$REGION \
  --service-account=$SA --set-cloudsql-instances=$CONN \
  --set-secrets=SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars=LOG_JSON=true \
  --command=python,-m,app.cli,cleanup-refresh-tokens --max-retries=1 --task-timeout=300

gcloud run jobs create taskapi-cleanup-attachments --image=$IMAGE --region=$REGION \
  --service-account=$SA --set-cloudsql-instances=$CONN \
  --set-secrets=SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars=LOG_JSON=true,GCS_BUCKET_NAME=${PROJECT_ID}-attachments,GCS_SIGNER_SERVICE_ACCOUNT=$SA \
  --command=python,-m,app.cli,cleanup-stale-attachments --max-retries=1 --task-timeout=300

# Cloud Scheduler: run both cleanup jobs once a day
gcloud services enable cloudscheduler.googleapis.com
gcloud iam service-accounts create taskapi-scheduler \
  --display-name="Cloud Scheduler for taskapi jobs"
SCHEDULER_SA=taskapi-scheduler@${PROJECT_ID}.iam.gserviceaccount.com
for job in taskapi-cleanup-tokens taskapi-cleanup-attachments; do
  gcloud run jobs add-iam-policy-binding $job --region=$REGION \
    --member="serviceAccount:$SCHEDULER_SA" --role="roles/run.invoker"
done
gcloud scheduler jobs create http taskapi-cleanup-tokens-schedule \
  --location=$REGION --schedule="0 4 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/taskapi-cleanup-tokens:run" \
  --http-method=POST --oauth-service-account-email=$SCHEDULER_SA
gcloud scheduler jobs create http taskapi-cleanup-attachments-schedule \
  --location=$REGION --schedule="0 5 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/taskapi-cleanup-attachments:run" \
  --http-method=POST --oauth-service-account-email=$SCHEDULER_SA

# Deployer service account for GitHub Actions
DEPLOY_SA=github-deployer@${PROJECT_ID}.iam.gserviceaccount.com
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/run.developer"
gcloud artifacts repositories add-iam-policy-binding taskapi --location=$REGION \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/artifactregistry.writer"
gcloud iam service-accounts add-iam-policy-binding $SA \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/iam.serviceAccountUser"

# Workload Identity Federation: only this repo, only the main branch
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository=='${GITHUB_REPO}' && assertion.ref=='refs/heads/main'"
gcloud iam service-accounts add-iam-policy-binding $DEPLOY_SA \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/${GITHUB_REPO}"
```

Monitoring, once the service is up:

```bash
gcloud services enable monitoring.googleapis.com logging.googleapis.com

# Email notification channel (or create it under Monitoring > Alerting in the Console)
gcloud beta monitoring channels create --display-name="Alerts" \
  --type=email --channel-labels=email_address=you@example.com
CHANNEL=$(gcloud beta monitoring channels list --format='value(name)' --limit=1)

# 5xx alert. Edit the service name in the file first if yours differs.
gcloud alpha monitoring policies create \
  --policy-from-file=infra/alert-5xx.yaml --notification-channels=$CHANNEL
```

The uptime check is easiest to create in the Console: **Monitoring → Uptime checks → Create**, protocol HTTPS, the service hostname, path `/health`, every 5 minutes, and pick the notification channel in the *Alert & notification* step so the alert policy is created with it. `infra/uptime-health.yaml` shows the resulting configuration.

Verify the whole chain actually reaches your inbox, rather than assuming it does — stopping the database briefly and hitting an endpoint that needs it is enough to trigger the 5xx alert.

Then update the project-specific values in `.github/workflows/ci.yml`: the `workload_identity_provider`, the `service_account` and the `IMAGE` path.

</details>

### Cost

Cloud Run scales to zero and has a free tier. Cloud SQL is the main cost, because it is billed while the instance runs. When not working on the project:

```bash
gcloud sql instances patch taskapi-db --activation-policy=NEVER    # stop
gcloud sql instances patch taskapi-db --activation-policy=ALWAYS   # start
```

While the database is stopped, endpoints that need it return `500`; `/health` keeps working.

## Possible next steps

- Background jobs (Cloud Tasks or Pub/Sub), for example notifications when a task is completed
- Cursor-based pagination, which avoids the duplicate/skipped rows that offset pagination can produce when the data changes between pages
- User roles, once there is a use case that needs them

## License

See [LICENSE](LICENSE).
