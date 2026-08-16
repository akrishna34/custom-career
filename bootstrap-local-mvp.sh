#!/usr/bin/env bash
# Career Vault local MVP prerequisite installer for Apple Silicon macOS.
# Run: bash bootstrap-local-mvp.sh

set -euo pipefail

readonly MIN_FREE_GB=12
readonly OLLAMA_HEALTH_URL="http://127.0.0.1:11434/api/tags"
readonly GENERATION_MODEL="qwen3:4b"
readonly EMBEDDING_MODEL="embeddinggemma:300m-qat-q4_0"

info() { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok() { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mError: %s\033[0m\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "This installer is for macOS only."
[[ "$(uname -m)" == "arm64" ]] || die "This MVP setup is designed for an Apple Silicon Mac."

free_kb="$(df -Pk "$HOME" | awk 'NR == 2 { print $4 }')"
free_gb=$((free_kb / 1024 / 1024))
(( free_gb >= MIN_FREE_GB )) || die "Need at least ${MIN_FREE_GB} GB of free disk space; found ${free_gb} GB."

cat <<'MESSAGE'

Career Vault local MVP setup

This script downloads and installs:
  - Apple Command Line Tools (if missing; macOS opens its installer and this script stops)
  - Homebrew (if missing)
  - Git, Python 3.12, and Node.js
  - Ollama for local model inference
  - Qwen3 4B (generation) and EmbeddingGemma Q4 (semantic matching)

Downloads are required for this setup. The downloaded AI models stay on this Mac
and are called through http://127.0.0.1:11434 after installation.
MESSAGE

read -r -p "Type INSTALL to continue: " confirmation
[[ "$confirmation" == "INSTALL" ]] || { warn "Cancelled. No changes were made."; exit 0; }

if ! xcode-select -p >/dev/null 2>&1; then
  info "Apple Command Line Tools are required before Homebrew can be installed."
  xcode-select --install || true
  cat <<'MESSAGE'

Complete the Apple installer dialog, then run this script again. macOS controls
that installation, so the script intentionally stops here.
MESSAGE
  exit 0
fi
ok "Apple Command Line Tools are available"

if ! command -v brew >/dev/null 2>&1; then
  info "Installing Homebrew using its official installer"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if [[ -x /opt/homebrew/bin/brew ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [[ -x /usr/local/bin/brew ]]; then
  eval "$(/usr/local/bin/brew shellenv)"
else
  die "Homebrew installation completed but the brew command was not found. Open a new terminal and run the script again."
fi
ok "Homebrew is available: $(brew --version | head -1)"

info "Installing development prerequisites"
brew update
brew install git python@3.12 node
ok "Git: $(git --version)"
ok "Python: $(python3.12 --version)"
ok "Node: $(node --version)"

if ! command -v ollama >/dev/null 2>&1; then
  info "Installing Ollama"
  brew install --cask ollama
fi
ok "Ollama CLI is installed"

info "Starting Ollama locally"
if ! curl --silent --fail "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
  if [[ -d "/Applications/Ollama.app" ]]; then
    open -gja Ollama || warn "Could not open the Ollama app automatically."
  else
    # The CLI can run its local server without the optional macOS app bundle.
    # `nohup` keeps the server available after this bootstrap script exits.
    mkdir -p "${HOME}/.ollama"
    nohup ollama serve >"${HOME}/.ollama/career-vault-server.log" 2>&1 &
    warn "Ollama app bundle was not found; started the installed CLI server instead."
  fi
fi

ollama_ready=false
for _ in $(seq 1 30); do
  if curl --silent --fail "$OLLAMA_HEALTH_URL" >/dev/null 2>&1; then
    ollama_ready=true
    break
  fi
  sleep 2
done

[[ "$ollama_ready" == true ]] || die "Ollama did not start within 60 seconds. Run 'ollama serve' in a separate Terminal window, then re-run this script."
ok "Ollama is responding locally"

info "Downloading local generation model: ${GENERATION_MODEL}"
ollama pull "$GENERATION_MODEL"

info "Downloading local embedding model: ${EMBEDDING_MODEL}"
ollama pull "$EMBEDDING_MODEL"

info "Verifying the local models"
ollama list
curl --silent --fail http://127.0.0.1:11434/api/embed \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${EMBEDDING_MODEL}\",\"input\":\"career vault health check\"}" \
  >/dev/null
ok "Embedding model answered successfully"

cat <<'MESSAGE'

Local infrastructure is ready.

Next implementation step:
  1. Create the React + FastAPI application repository.
  2. Add SQLite, migrations, and the local Ollama provider adapter.
  3. Build the guided Career Interview intake flow.

Useful checks:
  ollama list
  curl http://127.0.0.1:11434/api/tags
MESSAGE
