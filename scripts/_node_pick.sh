#!/usr/bin/env bash
# Prints absolute path to a Node binary: prefers versions meeting Hermes/Vite minimum,
# then falls back (handles PATH shadowing e.g. IDE-bundled node vs /usr/bin/node).
set -euo pipefail

required_major=20
required_minor=19

meets_requirement() {
  local ver="$1"
  ver="${ver#v}"
  local major="${ver%%.*}"
  local rest="${ver#*.}"
  local minor="${rest%%.*}"
  if [[ "$major" -gt "$required_major" ]] || [[ "$major" -eq "$required_major" && "$minor" -ge "$required_minor" ]]; then
    return 0
  fi
  return 1
}

candidates=()
[[ -n "${NODE_BIN:-}" && -x "$NODE_BIN" ]] && candidates+=("$NODE_BIN")
[[ -x /usr/bin/node ]] && candidates+=("/usr/bin/node")
if command -v node >/dev/null 2>&1; then
  p="$(command -v node)"
  dup=0
  for c in "${candidates[@]}"; do
    [[ "$c" == "$p" ]] && dup=1 && break
  done
  [[ "$dup" -eq 0 ]] && candidates+=("$p")
fi

for c in "${candidates[@]}"; do
  [[ -x "$c" ]] || continue
  ver="$("$c" -v | sed 's/^v//')"
  if meets_requirement "$ver"; then
    echo "$c"
    exit 0
  fi
done

for c in "${candidates[@]}"; do
  if [[ -x "$c" ]]; then
    echo "$c"
    exit 0
  fi
done

exit 1
