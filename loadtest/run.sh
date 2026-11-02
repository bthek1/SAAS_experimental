#!/usr/bin/env bash
# Run one k6 scenario against the local load-test stack (#9).
#
#   just k6 smoke
#   just k6 load RATE=20 HOLD=10m      # scenario options as KEY=VALUE
#
# Results go to Prometheus by remote write (the Grafana k6 dashboard, filtered by
# the testid this prints), the summary to the terminal, and the summary JSON to
# loadtest/results/<testid>.json. Start the stack first: `just loadtest-up`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]')-loadtest"
LT=(docker compose --env-file "$ROOT/.env" -f "$ROOT/infra/docker/docker-compose.loadtest.yml" -p "$PROJECT")
GRAFANA=http://localhost:3005

SCENARIO="${1:?usage: run.sh <smoke|load|stress|soak|respondent|pdf> [KEY=VALUE ...]}"
shift
[ -f "$ROOT/loadtest/k6/scenarios/${SCENARIO}.js" ] || {
  echo "no scenario loadtest/k6/scenarios/${SCENARIO}.js" >&2
  exit 1
}
"${LT[@]}" ps --status running backend | grep -q backend || {
  echo "the load-test backend is not running: just loadtest-up" >&2
  exit 1
}

# Two k6 runs at once would load the backend together and skew both. A run left
# behind by an interrupted one is stopped first.
leftover="$(docker ps -q --filter "label=com.docker.compose.project=${PROJECT}" \
  --filter label=com.docker.compose.service=k6)"
if [ -n "$leftover" ]; then
  echo "==> stop a k6 left running by an interrupted run"
  docker stop -t 5 $leftover >/dev/null
fi

TESTID="${SCENARIO}-$(date -u +%Y%m%dT%H%M%SZ)"
envs=()
for kv in "$@"; do envs+=(-e "$kv"); done
# Without a terminal, -T stops compose allocating one and --quiet drops k6's
# per-second progress lines; the summary is still printed.
tty=() quiet=()
if ! { [ -t 0 ] && [ -t 1 ]; }; then tty=(-T) quiet=(--quiet); fi
mkdir -p "$ROOT/loadtest/results"

echo "==> ${TESTID}: ${SCENARIO} against the local load-test backend"
start_ms="$(date +%s%3N)"
status=0
"${LT[@]}" run --rm "${tty[@]}" k6 run "${quiet[@]}" \
  --out experimental-prometheus-rw \
  --tag "testid=${TESTID}" \
  --summary-export "/loadtest/results/${TESTID}.json" \
  "${envs[@]}" "scenarios/${SCENARIO}.js" || status=$?
end_ms="$(( $(date +%s%3N) + 10000 ))"
echo "==> ${TESTID} finished (exit ${status}); summary: loadtest/results/${TESTID}.json"
echo "==> Grafana: ${GRAFANA}/d/k6/k6?var-testid=${TESTID}&from=$(( start_ms - 30000 ))&to=${end_ms}"
exit "$status"
