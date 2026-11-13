#!/usr/bin/env bash
# Run one k6 scenario (#9).
#
#   just k6 smoke                       # local stack (just loadtest-up)
#   just k6 load RATE=20 HOLD=10m       # scenario options as KEY=VALUE
#   just k6 smoke TARGET=lxc            # from saas-loadgen through saas-gateway (Proxmox LXC)
#
# Results go to Prometheus by remote write (the Grafana k6 dashboard, filtered by
# the testid this prints), the summary to the terminal, and the summary JSON to
# loadtest/results/<testid>.json.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SCENARIO="${1:?usage: run.sh <smoke|load|stress|soak|respondent|pdf|outage|catalog> [TARGET=local|lxc] [KEY=VALUE ...]}"
shift
[ -f "$ROOT/loadtest/k6/scenarios/${SCENARIO}.js" ] || {
  echo "no scenario loadtest/k6/scenarios/${SCENARIO}.js" >&2
  exit 1
}

TARGET=local
envs=()
for kv in "$@"; do
  case "$kv" in
    TARGET=*) TARGET="${kv#TARGET=}" ;;
    *) envs+=(-e "$kv") ;;
  esac
done

TESTID="${SCENARIO}-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$ROOT/loadtest/results"
# Without a terminal, no TTY is allocated and --quiet drops k6's per-second
# progress lines; the summary is still printed.
interactive=false
if [ -t 0 ] && [ -t 1 ]; then interactive=true; fi
GRAFANA=""
PROMETHEUS=""

run_local() {
  local project lt leftover tty=() quiet=()
  project="$(basename "$ROOT" | tr '[:upper:]' '[:lower:]')-loadtest"
  lt=(docker compose --env-file "$ROOT/.env" -f "$ROOT/infra/docker/docker-compose.loadtest.yml" -p "$project")
  "${lt[@]}" ps --status running gateway | grep -q gateway || {
    echo "the load-test stack is not running: just loadtest-up" >&2
    exit 1
  }
  # Two k6 runs at once would load the backend together and skew both. A run
  # left behind by an interrupted one is stopped first.
  leftover="$(docker ps -q --filter "label=com.docker.compose.project=${project}" \
    --filter label=com.docker.compose.service=k6)"
  if [ -n "$leftover" ]; then
    echo "==> stop a k6 left running by an interrupted run"
    docker stop -t 5 $leftover >/dev/null
  fi
  $interactive || { tty=(-T); quiet=(--quiet); }
  GRAFANA=http://localhost:3005
  PROMETHEUS=http://127.0.0.1:9095
  echo "==> ${TESTID}: ${SCENARIO} against the local load-test backend"
  "${lt[@]}" run --rm "${tty[@]}" k6 run "${quiet[@]}" \
    --out experimental-prometheus-rw \
    --tag "testid=${TESTID}" \
    --summary-export "/loadtest/results/${TESTID}.json" \
    "${envs[@]}" "scenarios/${SCENARIO}.js"
}

run_lxc() {
  local ips loadgen monitor ssh tty=-T quiet=--quiet rc=0 k6_opts=""
  ips="$(just -f "$ROOT/justfile" infra stack output ips --json)"
  loadgen="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["loadgen"])' <<<"$ips")"
  monitor="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["monitor"])' <<<"$ips")"
  for ip in "$loadgen" "$monitor"; do
    python3 -c "import ipaddress,sys; sys.exit(0 if ipaddress.ip_address(sys.argv[1]).is_private else 'refusing: not a private address')" "$ip"
  done
  ssh=(ssh -o BatchMode=yes -o ConnectTimeout=10 "root@${loadgen}")
  "${ssh[@]}" 'if pgrep -x k6 >/dev/null; then echo "==> stop a k6 left running by an interrupted run"; pkill -INT -x k6; sleep 3; pkill -KILL -x k6 || true; fi'
  # Scripts are synced on every run; /root/k6/results is left alone.
  rsync -a --delete -e "ssh -o BatchMode=yes" \
    "$ROOT/loadtest/k6/lib" "$ROOT/loadtest/k6/scenarios" "root@${loadgen}:/root/k6/"
  # With a TTY, Ctrl-C reaches k6 (which stops and still prints its summary)
  # instead of killing only the local ssh while k6 carries on.
  $interactive && { tty=-t; quiet=""; }
  # printf on an empty array would still print '' (an extra k6 argument).
  if [ "${#envs[@]}" -gt 0 ]; then k6_opts="$(printf '%q ' "${envs[@]}")"; fi
  GRAFANA="http://${monitor}:3000"
  PROMETHEUS="http://${monitor}:9090"
  echo "==> ${TESTID}: ${SCENARIO} from saas-loadgen through saas-gateway"
  # /root/k6.env (roles/loadgen) holds BASE_URL, OWNERS, the owner password and
  # the remote-write settings, so no secret is on this command line.
  "${ssh[@]}" "$tty" "set -a && . /root/k6.env && set +a && cd /root/k6 && \
    k6 run ${quiet} --out experimental-prometheus-rw --tag testid=${TESTID} --tag target=lxc \
    --summary-export results/${TESTID}.json ${k6_opts} scenarios/${SCENARIO}.js" || rc=$?
  scp -q -o BatchMode=yes "root@${loadgen}:/root/k6/results/${TESTID}.json" "$ROOT/loadtest/results/" || true
  return "$rc"
}

start_ms="$(date +%s%3N)"
status=0
case "$TARGET" in
  local) run_local || status=$? ;;
  lxc) run_lxc || status=$? ;;
  *) echo "TARGET must be local or lxc, not ${TARGET}" >&2; exit 2 ;;
esac
end_ms="$(( $(date +%s%3N) + 10000 ))"
# The run's window and where its metrics are, for `just k6-report <testid>`.
cat > "$ROOT/loadtest/results/${TESTID}.meta.json" <<META
{"testid": "${TESTID}", "scenario": "${SCENARIO}", "target": "${TARGET}", "start_ms": ${start_ms}, "end_ms": ${end_ms}, "exit": ${status}, "prometheus": "${PROMETHEUS}", "grafana": "${GRAFANA}"}
META
echo "==> ${TESTID} finished (exit ${status}); summary: loadtest/results/${TESTID}.json"
echo "==> Grafana: ${GRAFANA}/d/k6/k6?var-testid=${TESTID}&from=$(( start_ms - 30000 ))&to=${end_ms}"
exit "$status"
