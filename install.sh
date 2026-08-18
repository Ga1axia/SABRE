#!/bin/sh
# SABRE installer. POSIX sh. No dependencies beyond curl and git.
# Does not create OS users, start services, or write outside $SABRE_HOME
# and one PATH symlink.
set -eu

SABRE_HOME="${SABRE_HOME:-$HOME/.sabre}"
SABRE_REF="${SABRE_REF:-main}"
SABRE_REPO_URL="${SABRE_REPO_URL:-https://github.com/<org>/sabre.git}"
HERMES_INSTALL_URL="${HERMES_INSTALL_URL:-https://hermes-agent.nousresearch.com/install.sh}"
MIN_RAM_MB=8192
MIN_DISK_MB=4096

info() { printf '  ✓ %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*"; }
die() { printf '  ✗ %s\n' "$*" >&2; exit 1; }
step() { printf '\n→ %s\n' "$*"; }

detect_os() {
    os=$(uname -s 2>/dev/null || echo unknown)
    arch=$(uname -m 2>/dev/null || echo unknown)
    case "$os" in
        Darwin)
            major=$(uname -r | cut -d. -f1)
            # Darwin 21 == macOS 12
            if [ "$major" -lt 21 ]; then
                die "macOS 12+ required (found Darwin $major)"
            fi
            PLATFORM=macos
            ;;
        Linux)
            PLATFORM=linux
            ;;
        MINGW*|MSYS*|CYGWIN*|Windows*)
            die "Native Windows is not supported. Use macOS, Linux, or WSL2."
            ;;
        *)
            die "Unsupported platform: $os. SABRE requires macOS 12+ or Linux."
            ;;
    esac
    info "$os $arch"
}

need_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

ram_mb() {
    if [ "$PLATFORM" = macos ]; then
        bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        echo $((bytes / 1024 / 1024))
    else
        awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0
    fi
}

disk_mb() {
    target="$1"
    mkdir -p "$target"
    df -k "$target" 2>/dev/null | awk 'NR==2 {print int($4/1024)}'
}

verify_resources() {
    need_cmd curl
    need_cmd git
    ram=$(ram_mb)
    if [ "$ram" -gt 0 ] && [ "$ram" -lt "$MIN_RAM_MB" ]; then
        die "Need ≥ 8 GB RAM (found ${ram} MB)"
    fi
    [ "$ram" -gt 0 ] && info "${ram} MB RAM"
    disk=$(disk_mb "$SABRE_HOME")
    if [ "$disk" -gt 0 ] && [ "$disk" -lt "$MIN_DISK_MB" ]; then
        die "Need ≥ 4 GB free disk (found ${disk} MB)"
    fi
    [ "$disk" -gt 0 ] && info "${disk} MB free disk"
}

install_uv() {
    runtime="$SABRE_HOME/runtime"
    mkdir -p "$runtime"
    export UV_INSTALL_DIR="$runtime/uv"
    export UV_UNMANAGED_INSTALL="$UV_INSTALL_DIR"
    if [ -x "$UV_INSTALL_DIR/uv" ]; then
        info "uv already installed"
        return
    fi
    curl -fsSL https://astral.sh/uv/install.sh | sh
    [ -x "$UV_INSTALL_DIR/uv" ] || die "uv install failed"
    info "uv installed"
}

install_python() {
    UV="$SABRE_HOME/runtime/uv/uv"
    [ -x "$UV" ] || UV="$HOME/.local/bin/uv"
    [ -x "$UV" ] || die "uv not found"
    "$UV" python install 3.11
    info "Python 3.11 via uv"
}

script_dir() {
    # Resolve the directory containing this script when run from a checkout.
    src=$0
    case "$src" in
        /*) ;;
        *) src=$(pwd)/$src ;;
    esac
    dirname "$src"
}

install_app() {
    app="$SABRE_HOME/app"
    here=$(script_dir)
    if [ -f "$here/pyproject.toml" ] && [ -d "$here/core" ]; then
        if [ "$here" = "$app" ]; then
            info "already running from $app"
        else
            mkdir -p "$SABRE_HOME"
            if [ -d "$app/.git" ]; then
                git -C "$app" fetch --quiet origin 2>/dev/null || true
                git -C "$app" checkout --quiet "$SABRE_REF" 2>/dev/null || true
                info "upgraded existing checkout at $app"
            else
                rm -rf "$app"
                mkdir -p "$app"
                # Copy checkout without clobbering a future git remote clone layout.
                if command -v rsync >/dev/null 2>&1; then
                    rsync -a --exclude .venv --exclude .git --exclude __pycache__ "$here/" "$app/"
                else
                    tar -C "$here" --exclude .venv --exclude .git --exclude __pycache__ -cf - . | tar -C "$app" -xf -
                fi
                info "copied checkout to $app"
            fi
        fi
        return
    fi
    if [ -d "$app/.git" ]; then
        git -C "$app" fetch --quiet origin
        git -C "$app" checkout --quiet "$SABRE_REF"
        git -C "$app" pull --ff-only --quiet || true
        info "upgraded $app to $SABRE_REF"
        return
    fi
    case "$SABRE_REPO_URL" in
        *"<org>"*)
            die "SABRE_REPO_URL is still the placeholder. Set SABRE_REPO_URL to your clone URL or run ./install.sh from a checkout."
            ;;
    esac
    git clone --depth 1 --branch "$SABRE_REF" "$SABRE_REPO_URL" "$app"
    info "cloned $SABRE_REF to $app"
}

install_package() {
    UV="$SABRE_HOME/runtime/uv/uv"
    [ -x "$UV" ] || UV="$HOME/.local/bin/uv"
    app="$SABRE_HOME/app"
    venv="$SABRE_HOME/runtime/venv"
    "$UV" venv --python 3.11 "$venv"
    # shellcheck disable=SC1091
    . "$venv/bin/activate"
    "$UV" pip install --python "$venv/bin/python" -e "$app"
    info "sabre package installed"
}

install_hermes() {
    if command -v hermes >/dev/null 2>&1; then
        info "hermes already on PATH: $(command -v hermes)"
        return
    fi
    if ! curl -fsI "$HERMES_INSTALL_URL" >/dev/null 2>&1; then
        warn "Hermes installer not reachable at $HERMES_INSTALL_URL (set SABRE_HERMES_BIN later)"
        return
    fi
    curl -fsSL "$HERMES_INSTALL_URL" | sh || warn "hermes install script failed"
    if command -v hermes >/dev/null 2>&1; then
        info "hermes installed"
    else
        warn "hermes not on PATH after install; set SABRE_HERMES_BIN"
    fi
}

link_cli() {
    venv_bin="$SABRE_HOME/runtime/venv/bin/sabre"
    [ -x "$venv_bin" ] || die "sabre entry point missing after install"
    bindir="$HOME/.local/bin"
    mkdir -p "$bindir"
    ln -sfn "$venv_bin" "$bindir/sabre"
    if [ -w /usr/local/bin ] 2>/dev/null; then
        ln -sfn "$venv_bin" /usr/local/bin/sabre 2>/dev/null || true
    fi
    info "sabre on PATH via $bindir/sabre"
}

main() {
    printf 'SABRE installer\n'
    detect_os
    verify_resources
    step "runtime"
    install_uv
    install_python
    step "app"
    install_app
    install_package
    install_hermes
    link_cli
    printf '\n  ✓ sabre 0.1.0\n'
    printf '  → next: sabre setup\n'
}

main "$@"
