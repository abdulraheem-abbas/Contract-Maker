# Mac acceptance checks — 1 November 2026

The packaged Mac app passed the create-and-review workflow using fictional records. Tests were run on this Apple M1 Mac with 8 GB of memory.

- 36 automated checks passed, covering dates, salaries, leading zeros, source conflicts, field confirmation, language handling, template preservation, versioned template changes and local network restrictions.
- The local model read a fictional offer’s dates, role and salary. Numeric dates were interpreted by local code; ambiguous values were left for confirmation.
- A fictional passport image preserved `00012345`, identified the document as a passport, distinguished issue and expiry dates, and used Aden as issuing city rather than Taiz, its birthplace. The Arabic full name was left unverified; it requires manual checking or entry. This is an observed limitation of this test, not a claim that every name or scan will be read correctly.
- Employment, service and extension Word/PDF generation passed. Fixed template text and package parts outside the filled document body were preserved. The generated service document had no nearly empty extra page.
- Review caught a deliberately wrong Arabic salary while the English salary remained correct, and located a deliberate change to fixed wording.
- A final regression check confirmed that degraded PDF text extraction does not produce false missing-field errors when the original Word text contains the correct field. A field with a confirmed mismatch is not also listed as a matching check.
- Requests with an invalid host, origin, session or confirmation token were refused. Path traversal was blocked. Generation from unconfirmed fields or an unacknowledged expired document was refused.
- Desktop, narrow-screen and review-page browser checks reported no JavaScript errors and no external requests.
- Version 0.2 browser checks covered uploading a replacement as a draft, mapping both repeated Arabic names, displaying rendered page images, activating a new version and restoring the previous one. Active templates were unchanged until activation. NMO turquoise and charcoal styling was checked at desktop and narrow widths.
- A disposable workspace generated Word and PDF after a template change, recorded the active version in evidence, and reviewed the result without field errors. All these checks used fictional employee information; the configured private templates were preserved.
- Reviews of changed Word layouts check each mapped field occurrence against the configured template. A repeated signature name with a deliberate error was caught, and a different table with the same row count did not trigger the original template’s slot checks.
- macOS blocked an outbound connection under the runtime’s restriction while allowing loopback. The dedicated local engine reported cloud features disabled.
- Fictional workspaces were archived under `test-results`; the app opened with a clean workspace.

These checks establish the tested behaviors. They do not guarantee perfect OCR, correct missing information, unchanged pagination for every future name, or legal correctness. Confirm fields against their sources and visually inspect the final PDF before use.

Machine-readable results are retained in `test-results/acceptance.json`, `api-checks.json`, `output-checks.json`, `ai-smoke.json`, `identity-smoke.json` and `privacy-check.json`.
