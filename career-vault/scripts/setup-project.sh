#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v python3.12 >/dev/null || { echo "Python 3.12 is required. Run bootstrap-local-mvp.sh first."; exit 1; }
command -v npm >/dev/null || { echo "Node.js is required. Run bootstrap-local-mvp.sh first."; exit 1; }
command -v ollama >/dev/null || { echo "Ollama is required. Run bootstrap-local-mvp.sh first."; exit 1; }

echo "Creating Python virtual environment"
python3.12 -m venv "${project_root}/backend/.venv"
"${project_root}/backend/.venv/bin/python" -m pip install --upgrade pip
"${project_root}/backend/.venv/bin/pip" install -r "${project_root}/backend/requirements.txt"

echo "Installing frontend dependencies"
npm --prefix "${project_root}/frontend" install

echo "Checking local Ollama models"
ollama list

echo "Project dependencies are ready. Follow README.md to start backend and frontend."
