#!/usr/bin/env bash
# Deploy (or redeploy) the production stack on a Linux server. Idempotent: run it again after every
# `git push` you want live. Guide: docs/deployment.md.
#
#   git clone <repo-url> isnad && cd isnad
#   cp .env.production.example .env.production && nano .env.production
#   scripts/deploy.sh
#
# What it does:
#   1. installs Docker Engine + the Compose plugin if missing (Ubuntu/Debian, via get.docker.com)
#   2. opens 80/443 in the OS firewall if ufw or Oracle's iptables rules are in use
#   3. git pull --ff-only (skip with --no-pull)
#   4. checks .env.production has everything production needs
#   5. docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
#      (the one-shot `migrate` service applies migrations before api/worker start)
#   6. waits for /api/health/ready through Caddy and prints the URL
#
# Options:   --no-pull     deploy the working tree as it is
#            --check-only  run step 4 and stop
# Env:       COMPOSE_PROJECT (default isnad-prod), ENV_FILE (default .env.production),
#            READY_TIMEOUT seconds (default 300), COMPOSE_OVERRIDE (an extra compose file, for local testing)
set -euo pipefail

cd "$(dirname "$0")/.."
ENV_FILE=${ENV_FILE:-.env.production}
PROJECT=${COMPOSE_PROJECT:-isnad-prod}
READY_TIMEOUT=${READY_TIMEOUT:-300}
PULL=1
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-pull) PULL=0 ;;
    --check-only) CHECK_ONLY=1 ;;
    -h | --help) sed -n '2,21p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die() { printf '  \033[31m✗\033[0m %s\n' "$*" >&2; exit 1; }

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

# ---------------------------------------------------------------- 1. Docker
bold "1/6 Docker"
if ! command -v docker >/dev/null 2>&1; then
  [ "$(uname -s)" = "Linux" ] || die "Docker is missing — install Docker Desktop first."
  echo "  installing Docker Engine (get.docker.com)…"
  curl -fsSL https://get.docker.com | $SUDO sh
  if [ -n "$SUDO" ]; then $SUDO usermod -aG docker "$USER"; fi
fi
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if [ -n "$SUDO" ] && $SUDO docker info >/dev/null 2>&1; then
    DOCKER=("$SUDO" docker) # just added to the docker group; takes effect at the next login
  else
    die "Docker is installed but not running (try: sudo systemctl start docker)."
  fi
fi
"${DOCKER[@]}" compose version >/dev/null 2>&1 || die "the Docker Compose plugin is missing (apt install docker-compose-plugin)."
ok "$("${DOCKER[@]}" --version)"
COMPOSE_FILES=(-f docker-compose.prod.yml)
if [ -n "${COMPOSE_OVERRIDE:-}" ]; then COMPOSE_FILES+=(-f "$COMPOSE_OVERRIDE"); fi
compose() { "${DOCKER[@]}" compose -p "$PROJECT" "${COMPOSE_FILES[@]}" --env-file "$ENV_FILE" "$@"; }

# ---------------------------------------------------------------- 2. Firewall
bold "2/6 Firewall (80, 443)"
if [ "$(uname -s)" = "Linux" ]; then
  if command -v ufw >/dev/null 2>&1 && $SUDO ufw status 2>/dev/null | grep -q "Status: active"; then
    $SUDO ufw allow 80/tcp >/dev/null && $SUDO ufw allow 443/tcp >/dev/null && $SUDO ufw allow 443/udp >/dev/null
    ok "ufw allows 80/tcp, 443/tcp, 443/udp"
  elif [ -f /etc/iptables/rules.v4 ] && command -v iptables >/dev/null 2>&1; then
    # Oracle Cloud's Ubuntu images REJECT everything but SSH in the INPUT chain.
    for rule in "-p tcp --dport 80" "-p tcp --dport 443" "-p udp --dport 443"; do
      # shellcheck disable=SC2086
      $SUDO iptables -C INPUT $rule -j ACCEPT 2>/dev/null || $SUDO iptables -I INPUT 1 $rule -j ACCEPT
    done
    if command -v netfilter-persistent >/dev/null 2>&1; then $SUDO netfilter-persistent save >/dev/null 2>&1 || true; fi
    ok "iptables INPUT accepts 80/tcp, 443/tcp, 443/udp"
  else
    ok "no host firewall found"
  fi
  warn "the cloud provider's firewall (security list / security group) must also allow 80 and 443 — see docs/deployment.md"
else
  ok "not Linux — skipped"
fi

# ---------------------------------------------------------------- 3. Code
bold "3/6 Code"
if [ "$PULL" = 1 ] && [ "$CHECK_ONLY" = 0 ] && [ -d .git ]; then
  git pull --ff-only
fi
ok "$(git log --oneline -1 2>/dev/null || echo 'not a git checkout')"

# ---------------------------------------------------------------- 4. Settings
bold "4/6 $ENV_FILE"
if [ ! -f "$ENV_FILE" ]; then
  cp .env.production.example "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  die "created $ENV_FILE from the example — fill it in (see comments inside), then run this again."
fi
chmod 600 "$ENV_FILE" 2>/dev/null || true

# Read one variable without sourcing the file (values such as CORS_ORIGINS=["…"] aren't shell-safe).
get() {
  local line
  line=$(grep -E "^[[:space:]]*$1=" "$ENV_FILE" | tail -n 1 | tr -d '\r') || true
  line=${line#*=}
  line=${line%\"}; line=${line#\"}; line=${line%\'}; line=${line#\'}
  printf '%s' "$line"
}
errors=0
need() { if [ -z "$(get "$1")" ]; then printf '  \033[31m✗\033[0m %s is empty — %s\n' "$1" "$2"; errors=$((errors + 1)); fi; }

need DOMAIN "the hostname Caddy serves (e.g. isnad.example.com or 203-0-113-10.sslip.io)"
need PUBLIC_URL "the https:// URL people open"
need DATABASE_URL "Supabase session pooler URI (port 5432)"
need SUPABASE_URL "https://<project-ref>.supabase.co"
need SUPABASE_ANON_KEY "public anon key, baked into the frontend"
need JWT_SECRET "32+ random characters"
need FAKE_ADAPTERS "true or false"

DOMAIN=$(get DOMAIN)
PUBLIC_URL=$(get PUBLIC_URL)
FAKE=$(get FAKE_ADAPTERS)
STORAGE=$(get STORAGE_BACKEND); STORAGE=${STORAGE:-supabase}

case "$FAKE" in true | false | "") ;; *) warn "FAKE_ADAPTERS should be true or false, not '$FAKE'"; errors=$((errors + 1)) ;; esac
secret=$(get JWT_SECRET)
if [ -n "$secret" ] && [ ${#secret} -lt 32 ]; then warn "JWT_SECRET is shorter than 32 characters"; errors=$((errors + 1)); fi
case "$PUBLIC_URL" in
  "" ) ;;
  */) warn "PUBLIC_URL must not end with /"; errors=$((errors + 1)) ;;
  http://* | https://*) ;;
  *) warn "PUBLIC_URL must start with https:// (or http:// for an IP-only smoke test)"; errors=$((errors + 1)) ;;
esac
case "$DOMAIN" in
  "" | http://* | https://*) ;;
  *) if [ -n "$PUBLIC_URL" ] && [ "$PUBLIC_URL" != "https://$DOMAIN" ]; then
       warn "PUBLIC_URL ($PUBLIC_URL) should be https://$DOMAIN"; errors=$((errors + 1))
     fi ;;
esac
case "$(get DATABASE_URL)" in
  *:6543/*) warn "DATABASE_URL uses the transaction pooler (6543) — use the session pooler (5432)"; errors=$((errors + 1)) ;;
  *@localhost* | *@127.0.0.1*) warn "DATABASE_URL points at localhost — inside a container that is the container itself" ;;
esac
if [ "$STORAGE" = "supabase" ]; then
  need SUPABASE_SERVICE_KEY "service_role key, needed for STORAGE_BACKEND=supabase"
else
  warn "STORAGE_BACKEND=$STORAGE — generated files will not be downloadable in production (the API serves /files only outside production)"
fi
if [ "$FAKE" = "false" ]; then
  [ -n "$(get OPENAI_API_KEY)" ] || warn "FAKE_ADAPTERS=false but OPENAI_API_KEY is empty — Writer/Research runs will fail"
  [ -n "$(get SEARCH_API_KEY)" ] || warn "FAKE_ADAPTERS=false but SEARCH_API_KEY is empty — Research runs will fail"
fi
g=0
for v in GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET CREDENTIALS_ENCRYPTION_KEY; do
  if [ -n "$(get "$v")" ]; then g=$((g + 1)); fi
done
case $g in
  0) warn "Google connections not configured (optional) — Settings → Connections will say so" ;;
  3) ok "Google connections configured — redirect URI: $(get GOOGLE_REDIRECT_URI | grep . || echo "$PUBLIC_URL/api/connections/google/callback")" ;;
  *) warn "Google needs all three of GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, CREDENTIALS_ENCRYPTION_KEY" ;;
esac
for v in SEED_DEMO_DATA OAUTH_BIND_BROWSER DOWNLOAD_URL_EXPIRES_IN JWT_EXPIRY_MINUTES; do
  if grep -qE "^[[:space:]]*$v=[[:space:]]*$" "$ENV_FILE"; then
    warn "$v= is empty — comment it out or give it a value (an empty boolean/number stops the API)"; errors=$((errors + 1))
  fi
done
[ "$errors" -eq 0 ] || die "$errors problem(s) in $ENV_FILE"
ok "required settings present (FAKE_ADAPTERS=$FAKE, STORAGE_BACKEND=$STORAGE)"

case "$DOMAIN" in
  http://* | https://*) ;;
  *)
    if command -v getent >/dev/null 2>&1 && command -v curl >/dev/null 2>&1; then
      resolved=$(getent ahostsv4 "$DOMAIN" | awk 'NR==1 {print $1}') || true
      public=$(curl -fsS -4 --max-time 5 https://ifconfig.me 2>/dev/null) || true
      if [ -z "$resolved" ]; then
        warn "$DOMAIN does not resolve yet — Let's Encrypt will fail until the DNS A record exists"
      elif [ -n "$public" ] && [ "$resolved" != "$public" ]; then
        warn "$DOMAIN resolves to $resolved but this server's public IPv4 is $public"
      else
        ok "$DOMAIN → $resolved"
      fi
    fi ;;
esac
[ "$CHECK_ONLY" = 0 ] || exit 0

# ---------------------------------------------------------------- 5. Build and start
bold "5/6 Build and start (first build takes several minutes)"
if ! compose up -d --build --remove-orphans; then
  compose logs --tail 50 migrate api || true
  die "docker compose up failed (a failed migration shows in the migrate log above)"
fi
compose ps

# ---------------------------------------------------------------- 6. Ready?
bold "6/6 Waiting for $PUBLIC_URL/api/health/ready"
case "$DOMAIN" in
  http://*) port=$(get HTTP_PORT); port=${port:-80}; host=${DOMAIN#http://}; host=${host%%/*}
            probe=(curl -fsS --max-time 5 -H "Host: ${host%%:*}" "http://127.0.0.1:$port/api/health/ready") ;;
  *) port=$(get HTTPS_PORT); port=${port:-443}; host=${DOMAIN#https://}; host=${host%%/*}
     # --resolve talks to this machine directly, so it works before DNS or hairpin NAT does,
     # but still checks the real certificate.
     probe=(curl -fsS --max-time 5 --resolve "$host:$port:127.0.0.1" "https://$host:$port/api/health/ready") ;;
esac
deadline=$((SECONDS + READY_TIMEOUT))
body=""
until body=$("${probe[@]}" 2>/dev/null) && printf '%s' "$body" | grep -q ' agents"'; do
  if [ $SECONDS -ge $deadline ]; then
    echo "  last answer: ${body:-none}"
    compose logs --tail 30 caddy api worker || true
    die "not ready after ${READY_TIMEOUT}s. Certificate problems show in the caddy log; see docs/deployment.md → Troubleshooting."
  fi
  sleep 5
done
ok "$body"
"${DOCKER[@]}" image prune -f >/dev/null 2>&1 || true

bold "Live at $PUBLIC_URL"
echo "  Open it on a phone on mobile data. Logs: docker compose -p $PROJECT -f docker-compose.prod.yml logs -f"
