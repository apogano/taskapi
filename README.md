# Task API

![CI](https://github.com/apogano/taskapi/actions/workflows/ci.yml/badge.svg)

A multi-user task management REST API built with FastAPI and PostgreSQL, deployed to Google Cloud Run through an automated CI/CD pipeline.

I built it as a hands-on project to learn production-style backend development: layered architecture, database migrations, authentication, testing, structured logging and cloud deployment.

## Features

- JWT authentication: register, login, `/users/me`, with argon2 password hashing
- Refresh token rotation with theft detection: each refresh token is single-use; reusing an already-rotated token revokes the whole token family
- Task CRUD with filtering (`done`) and pagination (`limit`, `offset`)
- Per-user data isolation: a user can only see and modify their own tasks
- Database migrations with Alembic
- Structured JSON logging, with a request ID on every request, response and log line
- Consistent error handling: unexpected errors return a generic 500 and never leak internals
- Tests run against a real PostgreSQL database, each test isolated in a rolled-back transaction
- CI/CD with GitHub Actions and keyless authentication to GCP (Workload Identity Federation)
- A scheduled Cloud Run Job clears expired and revoked refresh tokens daily

## Tech stack

| Area | Tools |
|---|---|
| API | FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy 2.0, Alembic, psycopg 3 |
| Auth | PyJWT, pwdlib (argon2) |
| Tooling | uv, pytest, ruff |
| Runtime | Docker, Google Cloud Run, Cloud SQL, Secret Manager, Artifact Registry |
| CI/CD | GitHub Actions, Workload Identity Federation |

## API overview

| Method | Path | Description | Auth |
|---|---|---|---|
| `POST` | `/auth/register` | Create an account | no |
| `POST` | `/auth/login` | OAuth2 password form (`username` is the email), returns an access + refresh token pair | no |
| `POST` | `/auth/refresh` | Exchange a refresh token for a new pair (rotation) | no (refresh token in body) |
| `POST` | `/auth/logout` | Revoke a refresh token | no (refresh token in body) |
| `GET` | `/users/me` | Current user | yes |
| `POST` | `/tasks` | Create a task | yes |
| `GET` | `/tasks` | List own tasks. Query: `done`, `limit` (1-100, default 50), `offset` | yes |
| `GET` | `/tasks/{id}` | Get one task | yes |
| `PATCH` | `/tasks/{id}` | Partial update | yes |
| `DELETE` | `/tasks/{id}` | Delete a task | yes |
| `GET` | `/health` | Liveness check (does not touch the database) | no |

"Auth" here means the bearer access token on the `Authorization` header. `/auth/refresh` and `/auth/logout` instead take a refresh token in the JSON body, since that is the credential they operate on.

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

### Configuration

Settings are read from environment variables (or from `.env` locally).

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | required | SQLAlchemy URL, e.g. `postgresql+psycopg://user:pass@host:5432/db` |
| `SECRET_KEY` | required | Key used to sign JWTs. Never commit it |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Access token (JWT) lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOG_JSON` | `false` | JSON logs (used on Cloud Run) instead of plain text |
| `ENABLE_DOCS` | `false` | Serve `/docs`, `/redoc` and `/openapi.json` |

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
├── logging_config.py  # text/JSON logging with request ID
├── middleware.py      # request ID, request log, catch-all 500
├── errors.py          # domain exceptions -> HTTP responses
├── cli.py             # maintenance commands (refresh token cleanup), run outside the request cycle
├── dependencies/      # FastAPI dependency providers (services, current user)
├── routers/           # HTTP layer only
├── services/          # business logic and transaction boundaries
├── repositories/      # database queries only
├── models/            # SQLAlchemy models (Task, User, RefreshToken)
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
- **Logging.** One structured log line per request (method, path, status, duration), never bodies, query strings, passwords or tokens. The `X-Request-ID` header is accepted only if it is short and alphanumeric, to prevent log injection.
- **Task ids are UUIDs**, so they are not guessable or enumerable.

## Deployment

```mermaid
flowchart LR
    PR["Pull request"] --> CI["Ruff, pytest, migration check"]
    CI --> Merge["Merge to main"]
    Merge --> Build["Build and push image"]
    Build --> Migrate["Cloud Run Job: alembic upgrade head"]
    Migrate --> Cleanup["Update taskapi-cleanup-tokens image"]
    Cleanup --> Deploy["Deploy new revision"]
    Deploy --> Smoke["Smoke test: GET /health"]
    Scheduler["Cloud Scheduler, daily"] -.-> Cleanup2["taskapi-cleanup-tokens runs"]
```

**Runtime.** The API runs on Cloud Run and connects to Cloud SQL (PostgreSQL) through the Cloud SQL unix socket, with no public database access. `SECRET_KEY` and `DATABASE_URL` come from Secret Manager. The container runs as a non-root user and the image contains no secrets.

**On every pull request**, the workflow runs `ruff check`, `ruff format --check`, the test suite on a PostgreSQL service container, and applies all migrations to an empty database followed by `alembic check`. The tests create the schema with `create_all` for speed, so this last step is what verifies the migrations themselves.

**On every merge to `main`**, if the checks pass, the workflow builds the image (tagged with the commit SHA), runs the migrations as a Cloud Run Job, points the `taskapi-cleanup-tokens` job at the same new image, deploys the new revision and calls `/health`. Migrations run before the deploy, so a failed migration leaves the previous version serving traffic. Deployments are serialized with a `concurrency` group.

**Scheduled maintenance.** `taskapi-cleanup-tokens` is a second Cloud Run Job, built from the same image as the service but run with `python -m app.cli` instead of `uvicorn`. A Cloud Scheduler trigger invokes it once a day to delete expired and long-revoked refresh tokens. It is kept up to date by the deploy pipeline above rather than by its own build step.

**Least privilege.** Two service accounts with separate roles:

| Service account | Purpose | Permissions |
|---|---|---|
| `taskapi-run` | Runs the app | Cloud SQL Client, access to the two secrets |
| `github-deployer` | Used by GitHub Actions | Cloud Run Developer, write access to the Artifact Registry repository, act as `taskapi-run` |

GitHub authenticates through **Workload Identity Federation**, so no service account key exists anywhere. The provider only accepts tokens from this repository on the `main` branch.

**Cleanup.** Artifact Registry keeps the 5 most recent images and deletes older ones after 30 days (`infra/cleanup-policy.json`). The 5 kept images cover rollbacks.

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

# First deployment. It stores the service configuration (service account,
# secrets, Cloud SQL, env vars); the pipeline later only changes the image.
gcloud run deploy taskapi --source . --region $REGION \
  --service-account $SA --add-cloudsql-instances $CONN \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars LOG_JSON=true --max-instances 2 --allow-unauthenticated

# Migration job (same image as the service)
IMAGE=$(gcloud run services describe taskapi --region $REGION \
  --format='value(spec.template.spec.containers[0].image)')
gcloud run jobs create taskapi-migrate --image $IMAGE --region $REGION \
  --service-account $SA --set-cloudsql-instances $CONN \
  --set-secrets SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --command alembic --args upgrade,head
gcloud run jobs execute taskapi-migrate --region $REGION --wait

# Refresh token cleanup job (same image, runs the CLI instead of the server)
gcloud run jobs create taskapi-cleanup-tokens --image=$IMAGE --region=$REGION \
  --service-account=$SA --set-cloudsql-instances=$CONN \
  --set-secrets=SECRET_KEY=secret-key:latest,DATABASE_URL=database-url:latest \
  --set-env-vars=LOG_JSON=true \
  --command=python,-m,app.cli --max-retries=1 --task-timeout=300

# Cloud Scheduler: run the cleanup job once a day
gcloud services enable cloudscheduler.googleapis.com
gcloud iam service-accounts create taskapi-scheduler \
  --display-name="Cloud Scheduler for taskapi jobs"
SCHEDULER_SA=taskapi-scheduler@${PROJECT_ID}.iam.gserviceaccount.com
gcloud run jobs add-iam-policy-binding taskapi-cleanup-tokens --region=$REGION \
  --member="serviceAccount:$SCHEDULER_SA" --role="roles/run.invoker"
gcloud scheduler jobs create http taskapi-cleanup-tokens-schedule \
  --location=$REGION --schedule="0 4 * * *" \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/taskapi-cleanup-tokens:run" \
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

- User roles / permission levels
- Background jobs (Cloud Tasks or Pub/Sub), for example notifications when a task is completed
- File attachments in Cloud Storage with signed URLs
- Rate limiting on the auth endpoints
- Alerts on 5xx errors in Cloud Monitoring

## License

MIT — see `LICENSE`.
