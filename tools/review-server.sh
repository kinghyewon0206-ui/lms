#!/usr/bin/env bash
# ECONOVA local review server (for the owner's curriculum review). Isolated from every real service:
# - its own SQLite database under ~/econova-private/review-server (never the repo's lms.db, never Firestore)
# - mock AI only (no OpenAI requests), AI wrong-answer feedback off
# - draft preview on (/preview/...), dev test courses on (to walk through the student flow end to end)
# Review decisions made in /admin/content are stored only in this local database. Approving there does NOT publish:
# publishing needs a signed release plan, a commit, and a deployment, which are separate human steps.
#
#   tools/review-server.sh                       start the server (http://127.0.0.1:5070)
#   tools/review-server.sh make-admin EMAIL      give an account you already signed up with admin access (local DB only)
#   tools/review-server.sh review-package c01    write the teacher review document with answers to ~/econova-private/review/
#   tools/review-server.sh reset                 delete the local review database (review decisions recorded there are lost)
set -euo pipefail
cd "$(dirname "$0")/.."
REVIEW_DIR="${ECONOVA_REVIEW_DIR:-$HOME/econova-private/review-server}"
mkdir -p "$REVIEW_DIR" && chmod 700 "$REVIEW_DIR"
export DB_BACKEND=sqlite
export SQLITE_PATH="$REVIEW_DIR/review.db"
export ECONOVA_AI_PROVIDER=mock
export ECONOVA_AI_FEEDBACK=off
export ECONOVA_CONTENT_PREVIEW=1
export ECONOVA_DEV_FIXTURES=1
export ECONOVA_PRIVATE_CONTENT_DIR="$HOME/econova-private"
export PORT="${PORT:-5070}"
unset RENDER APP_ENV
case "${1:-serve}" in
  serve)
    echo "ECONOVA review server: http://127.0.0.1:$PORT  (database: $SQLITE_PATH, AI: mock)"
    exec .venv/bin/python app.py ;;
  make-admin)
    email="${2:?usage: tools/review-server.sh make-admin EMAIL}"
    printf '%s\n' "$email" | .venv/bin/flask --app app admin-grant "$email" \
      --operator "${OPERATOR:-Local reviewer}" \
      --verification "Local review database on the owner's computer; the owner created this account themselves" ;;
  review-package)
    .venv/bin/flask --app app review-package "${2:?usage: tools/review-server.sh review-package c01}" ;;
  reset)
    rm -f "$SQLITE_PATH" && echo "Deleted $SQLITE_PATH" ;;
  *) echo "unknown command: $1" >&2; exit 2 ;;
esac
