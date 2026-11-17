#!/usr/bin/env bash
# Runs once, after the dev container is created.
#
# Every step is best-effort and reports its own outcome: a failure here should
# leave you with a usable container and a clear message, not a broken one.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

warnings=()
note() { printf '\n\033[1m[post-create] %s\033[0m\n' "$1"; }
warn() { warnings+=("$1"); printf '\033[33m[post-create] WARN: %s\033[0m\n' "$1"; }

note "Enabling corepack (pnpm comes from frontend/package.json's packageManager pin)"
sudo corepack enable || warn "corepack enable failed — run it yourself before using pnpm"

note "Installing frontend dependencies"
# node_modules is a named volume, so it starts empty on a fresh container.
if ! (cd frontend && pnpm install --frozen-lockfile); then
	warn "pnpm install failed — the Python side still works; retry in frontend/"
fi

note "Waiting for Postgres at db:5432"
db_up=0
for _ in $(seq 1 30); do
	if pg_isready -h db -p 5432 -U postgres -d mafd -q; then db_up=1; break; fi
	sleep 2
done

if [ "$db_up" = "1" ]; then
	note "Applying migrations (Alembic owns the schema)"
	alembic -c backend/alembic.ini upgrade head || warn "alembic upgrade failed — run it yourself"
else
	warn "Postgres not reachable — skipped migrations. Run: alembic -c backend/alembic.ini upgrade head"
fi

cat <<'BANNER'

────────────────────────────────────────────────────────────────────────
 MAFD dev container ready.

 One-time, to create Kafka topics + train the models + build the SOP KB:
   python scripts/bootstrap.py

 Then, in separate terminals:
   uvicorn backend.api.main:app --reload --host 0.0.0.0   # API + 6 consumer groups
   cd frontend && pnpm dev --host                     # operator console

 Drive the pipeline:
   python scripts/produce_waveforms.py --fault SLG

 Checks:
   curl -fsS http://localhost:8000/ready
   pytest -q
   ruff check .

 Infrastructure is already up on the host: Kafdrop http://localhost:9000,
 Postgres localhost:5433. In here they are kafka:9092 and db:5432.
────────────────────────────────────────────────────────────────────────

BANNER

if [ ${#warnings[@]} -gt 0 ]; then
	printf '\033[33mFinished with %d warning(s):\033[0m\n' "${#warnings[@]}"
	printf '  - %s\n' "${warnings[@]}"
fi

exit 0
