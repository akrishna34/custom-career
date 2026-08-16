# Local MVP infrastructure setup

## Before running

1. Save this folder locally and open Terminal.
2. Confirm you have at least 12 GB of free disk space and a stable internet connection for the one-time downloads.
3. Run:

```bash
cd "/Users/krishnaagrawal/Documents/Codex/2026-08-16/hey-gpt-so-today-is-sunday/outputs"
bash bootstrap-local-mvp.sh
```

4. Type `INSTALL` when asked.

If Apple asks to install Command Line Tools, complete that dialog and run the same command again. This is expected the first time.

## What the script installs

- Apple Command Line Tools
- Homebrew, only when it is missing
- Git, Python 3.12, Node.js
- Ollama
- `qwen3:4b` for local generation
- `embeddinggemma:300m-qat-q4_0` for semantic matching

The script checks that Ollama is reachable on `127.0.0.1:11434`, pulls the models, and verifies embeddings work. Qwen3 4B is selected as a practical initial model for an M1 Pro with 16 GB unified memory; the smaller Q4 embedding model minimizes memory and disk use.

## Safety and privacy

- Review the script before running it; it asks for confirmation before downloading/installing anything.
- Homebrew and model downloads require internet access only during setup.
- Once models are downloaded, application inference is local through Ollama's localhost endpoint.
- Do not expose Ollama's port `11434` to the public internet.

## After it succeeds

Reply here with the final output, especially the `ollama list` section. The next step will scaffold the application with React, FastAPI, SQLite, and the provider interfaces from the architecture blueprint.
