# Private Contracts

A local workspace for NMO’s Arabic and English employment contracts, service contracts and extension letters. This first Mac version is built for the Apple M1 with 8 GB of memory.

**GitHub contains source code only.** Private templates, employee documents, personal rules, databases, model downloads and the built Mac app stay on the local computer. See [DEVELOPMENT.md](DEVELOPMENT.md) for source setup and future edits. The configured Mac installation described below includes private local files that a fresh GitHub clone does not contain.

## Open the app

Double-click **Private Contracts.app** in this folder, or **Start Private Contracts.command**. Keep the app, `data` and `runtime` folders together. The interface opens at an address beginning with `http://127.0.0.1:` in your browser. That address is inside this computer; it is not a website on the internet.

If macOS asks about a locally built application, use Finder’s **Open** action. This is a locally packaged app, not an App Store installation.

If the AI is stopped after restarting your Mac, click its status at the top, then **Start local engine**. This starts the downloaded model on this computer.

## Create a contract

1. Choose **Create a contract** and its type.
2. Add the offer, ID/passport and employee list. For the list, enter the employee’s name exactly as shown or the row number. Existing contracts may be added as an identity source when that is the agreed source.
3. Choose **Read with local AI**. Suggestions stay unconfirmed. You may also enter agreed information manually if there is no offer.
4. Check each field against the displayed original page. Confirm missing grades, uncertain names or numbers yourself. Issuing authority must contain the city only.
5. Choose **Create Word & PDF**. Open the PDF and check text direction, page breaks and signature space. Each run saves a new revision and an evidence file.

Your employment and service templates are configured locally from the approved contract references. Only tagged fields are filled. All filled text uses bold formatting for both Arabic and Latin scripts. Original source files are preserved.

Employment contracts use the job title without the project name, and the reporting manager’s title without their name. Service contracts retain project and manager details. Your three specific Shelter Field Assistant instructions are saved under **Templates & rules**. An absent manager location does not leave a dangling “based in” phrase.

The extension letter is configured for employee names, identity details, the original contract date, the new period and signature dates. Its general scope clauses remain unchanged. The original is retained under Templates.

## Review an existing contract

Choose **Review a contract**. Add the offer, identity source and list, plus the existing contract under **Contract to review**. Read and confirm the expected fields, then select **Review contract**.

Findings show the field, document and page or Word paragraph when available. For the configured Word structures, repeated fields and each language side are checked separately. Fixed wording is compared with the configured template. Scans use local Arabic/English OCR and require visual checking. PDF comparisons cannot establish that Word formatting or every unchanged clause is identical.

Review produces local HTML notes and a JSON evidence record. Review mode does not silently rewrite the supplied contract.

## Privacy and offline use

- Employee documents, extracted text, previews, history and outputs stay under this folder’s `data` directory.
- No cloud model, online OCR, telemetry, CDN or online document conversion is used.
- Python refuses external connections and DNS lookups. The dedicated Ollama server binds to loopback, disables cloud features and runs under a macOS rule blocking outbound connections. PDF conversion has the same outbound restriction.
- Software and model downloads are separate setup actions. They do not receive employee files. The installed model and tools can be used with Wi-Fi disconnected.
- Keep this whole folder outside iCloud, Dropbox, OneDrive and other synced locations. The app does not control your browser extensions, operating-system backups or other applications. Use a trusted browser profile; disconnect the internet when handling sensitive work if you want that additional assurance.
- The database is local but not independently encrypted. Protect your Mac account; FileVault can provide disk encryption if enabled. Back up the entire folder using a storage method you control.
- Logs contain operation types and engine timings, not document bodies or prompts. Evidence and review files do contain employee information and should be handled like the contracts themselves.

## Accuracy and limits

This app assists preparation and checking. The small local model can misread Arabic names, scans and dates. It must not be treated as an authority on identity, salary, legal wording or missing information. Required fields must be confirmed before generation; date/expiry warnings require a separate acknowledgement. No value is filled from an incomplete model response. No cloud fallback is used if local AI fails.

The existing templates retain their original wording, pagination rules and bilingual layout. Longer values may alter wrapping, so inspect the generated PDF. The app flags nearly empty PDF pages; it does not automatically delete possible signature pages.

## Files and maintenance

- `data/templates` — configured Word templates and original extension letter
- `data/rules.json` — your saved instructions
- `data/models` — downloaded model weights
- `data/workspace.sqlite3` — workspaces and evidence history
- `data/sources` — local copies of selected source files
- `data/outputs` — generated contracts and review reports
- `runtime/office` — local PDF conversion runtime

Ollama and Tesseract are installed on this Mac. The Mac app bundles its Python libraries, so it does not require the Codex app to run. LibreOffice’s headless runtime is copied into this project. Please keep the external Ollama and Tesseract installations available.

Windows will need a separate Windows build, locally installed model/OCR/office tools and a verified outbound firewall configuration. The source is organized for that migration, but the Mac app itself is not a Windows executable.

For local development: `.venv/bin/python run.py`; checks: `.venv/bin/python -m pytest -q tests`. Model software setup: `.venv/bin/python tools/setup_engine.py`. Model setup is the only supplied operation intended to download anything.

## Third-party components

This application uses [Ollama](https://github.com/ollama/ollama), [Qwen3-VL](https://ollama.com/library/qwen3-vl/tags), [Tesseract](https://github.com/tesseract-ocr/tesseract), [LibreOffice](https://www.libreoffice.org/about-us/licenses/), Python, lxml, Pillow, pypdf, pdfplumber, pypdfium2, num2words and PyInstaller. Their respective licenses and notices apply. The downloaded model’s license is available through Ollama’s local model information. Dependencies are installed locally, not fetched when opening employee documents.
