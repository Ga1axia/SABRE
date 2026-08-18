#!/bin/sh
# Reverse install.sh. Moves config/ and work/ aside; never deletes them.
set -eu

SABRE_HOME="${SABRE_HOME:-$HOME/.sabre}"
stamp=$(date +%Y%m%d%H%M%S)

info() { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }

if [ -x "$SABRE_HOME/runtime/venv/bin/sabre" ]; then
    "$SABRE_HOME/runtime/venv/bin/sabre" down >/dev/null 2>&1 || true
fi

rm -f "$HOME/.local/bin/sabre"
rm -f /usr/local/bin/sabre 2>/dev/null || true
info "removed sabre from PATH"

if [ -d "$SABRE_HOME/runtime" ]; then
    rm -rf "$SABRE_HOME/runtime"
    info "removed runtime"
fi

if [ -d "$SABRE_HOME/app" ]; then
    rm -rf "$SABRE_HOME/app"
    info "removed $SABRE_HOME/app"
fi

aside="$SABRE_HOME/aside-$stamp"
mkdir -p "$aside"
moved=0
for d in config work; do
    if [ -e "$SABRE_HOME/$d" ]; then
        mv "$SABRE_HOME/$d" "$aside/$d"
        moved=1
    fi
done
if [ "$moved" -eq 1 ]; then
    warn "config and work moved to $aside (not deleted)"
fi

# Leave the home dir if anything remains.
if [ -d "$SABRE_HOME" ]; then
    leftover=$(find "$SABRE_HOME" -mindepth 1 -maxdepth 1 ! -name "aside-*" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$leftover" = "0" ]; then
        # keep aside-*
        :
    fi
fi

printf '  → next: nothing. Reinstall with install.sh\n'
