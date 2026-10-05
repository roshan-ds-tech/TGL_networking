#!/usr/bin/env sh
# Read-only smoke test of a deployed TGL instance. Writes no data.
#   sh scripts/smoke-live.sh https://tgl.skykeen.in
set -u
BASE="${1:?usage: smoke-live.sh https://your-deployment}"
BASE="${BASE%/}"
fail=0

expect() { # expect <path> <status> [grep-pattern]
  body=$(curl -sS -m 30 -o /tmp/tgl-smoke.$$ -w "%{http_code}" "$BASE$1") || body="000"
  if [ "$body" != "$2" ]; then
    echo "FAIL  $1 -> HTTP $body (want $2)"; fail=1
  elif [ -n "${3:-}" ] && ! grep -q "$3" /tmp/tgl-smoke.$$; then
    echo "FAIL  $1 -> missing '$3'"; fail=1
  else
    echo "ok    $1 -> $body"
  fi
}
header() { # header <path> <header-regex>
  if curl -sS -m 30 -I "$BASE$1" | grep -qiE "$2"; then echo "ok    $1 has /$2/"; else echo "FAIL  $1 lacks /$2/"; fail=1; fi
}

expect /api/health 200 '"ok"'
expect / 200 'The Growth League'
expect /login 200 '<div id="root">'
expect /signup 200
expect /app/networking 200
expect /admin 200
expect /robots.txt 200 'Sitemap'
expect /sitemap.xml 200 'urlset'
expect /favicon.png 200
expect /this-page-does-not-exist 404
expect /api/does-not-exist 404
expect /api/categories/availability 200 'capacity_per_category'
expect /api/v1/auth/session 200 '"authenticated":false'
expect /api/admin/registrations 401
expect /api/v1/status 401
expect /docs 404
expect /openapi.json 404
expect /.env 404
expect /TGL_Web_App_Project_Proposal_Vertex_Networking.docx 404
header / 'strict-transport-security'
header / 'content-security-policy'
header / 'x-frame-options: DENY'
header /login 'x-robots-tag: noindex'
if curl -sS -m 30 -I "$BASE/" | grep -qi 'x-robots-tag'; then echo "FAIL  / must be indexable"; fail=1; else echo "ok    / is indexable"; fi
asset=$(curl -sS -m 30 "$BASE/" | grep -oE '/assets/index-[^"]+\.js' | head -1)
if [ -n "$asset" ]; then
  expect "$asset" 200
  header "$asset" 'cache-control: public, max-age=31536000, immutable'
  if curl -sS -m 30 "$BASE$asset" | grep -q 'localhost:8000'; then echo "FAIL  bundle points at localhost"; fail=1; else echo "ok    bundle has no localhost API URL"; fi
else
  echo "FAIL  no JS bundle referenced from /"; fail=1
fi
rm -f /tmp/tgl-smoke.$$
[ "$fail" -eq 0 ] && echo "\nALL SMOKE CHECKS PASSED" || { echo "\nSMOKE CHECKS FAILED"; exit 1; }
