#!/bin/sh
# Default container command: migrate, optionally seed the demo, then serve the API with the
# background worker in the same process (Render free tier: 512 MB, one process).
set -e

signallens migrate

if [ "${SL_SEED_DEMO:-false}" = "true" ]; then
    # Idempotent: existing demo user, pages and lab workspace are left as they are.
    signallens seed-demo --lab || echo "seed-demo failed; continuing without demo data" >&2
fi

export SL_RUN_WORKER_IN_API=true
exec signallens api --host 0.0.0.0 --port "${PORT:-8000}"
