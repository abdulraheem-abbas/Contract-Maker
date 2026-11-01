# Development and GitHub

This repository contains application source code. Employee files, private Word templates, personal rules, model weights, databases, generated contracts and packaged applications are deliberately excluded. The working Mac installation keeps these locally in ignored folders.

## Source installation

Use Python 3.12 on macOS. From the project folder:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python run.py
```

The source interface can open without employee documents or a model. To read source documents with AI, install Ollama and run the separate model setup:

```sh
.venv/bin/python tools/setup_engine.py
```

That setup downloads model software only. Normal document processing has no cloud fallback. Tesseract with Arabic/English language data is required for OCR. LibreOffice is required for local PDF conversion. The prepared Mac installation already has these tools; they are not included in this source repository.

The repository does **not** include configured company templates or employee-specific rules. Keep a separate private backup of the existing `data` folder and `runtime` folder when moving to another computer. Do not commit or attach them to GitHub issues or pull requests. A fresh clone alone will not reproduce the private company configuration.

The one-time importer for the original local employee references is kept under ignored `local/`, because it contains employee-specific configuration. The generic extension mapper under `tools/` expects an original template already present locally.

## Run checks

```sh
.venv/bin/python -m pytest -q tests
```

The core tests use fictional data. Three additional tests run only when the private templates are configured locally; a clean clone skips those tests. Do not upload private templates to make those tests run remotely.

Model and PDF acceptance checks are optional, local integration checks:

```sh
.venv/bin/python tools/smoke_ai.py
.venv/bin/python tools/smoke_identity.py
.venv/bin/python tools/output_checks.py
```

Browser acceptance scripts additionally require Playwright, Node.js and a local Chrome installation. They run against the app at `http://127.0.0.1:8768`, use fictional records and write ignored local screenshots/results. The automated final-check helper can restart the local test app and archive fictional workspaces; use it in a development workspace rather than during active employee work.

To build the Mac application locally:

```sh
.venv/bin/python tools/build_mac.py
```

Windows needs a separate build and a verified firewall setup before local AI inference is enabled. The Mac application cannot be run directly on Windows.

## Before every commit

Review the staged file list and staged diff. `.gitignore` helps prevent accidental additions but does not make forced additions safe. Never commit real names, identity numbers, offers, salary lists, filled contracts, screenshots of employee documents, local rules or credentials—even to a private repository.

After a source update, the existing Mac app must be rebuilt to include Python/UI code changes. Updating source files does not replace the already packaged app automatically.
