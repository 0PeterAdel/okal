# Gmail Source Folders — read-only local navigation

## Purpose

The existing **Action / Information / Low priority / Manual review** AI classification remains unchanged. A second independent navigation layer groups cached inbox records by sender **source** and, for GitHub, by notification **topic**. Neither source nor topic is an AI-generated claim.

Select **GitHub** to see **Pull Requests**, **Issues**, **CI / Actions**, **Security**, **Discussions**, **Releases**, **Repositories**, and **Other notifications**, with counts. Other known source groups include LinkedIn, Jira/Atlassian, Google, Cloudflare, Freelance, Microsoft, and Other sources.

GitHub subjects mentioning only "(#123)" remain under **Other GitHub notifications**. This pattern alone cannot reliably distinguish Issue from Pull Request. Source/topic classification conservatively uses sender domain and subject rather than asking Ollama to guess.

## Data flow and privacy

- apps/core/src/okal_core/mail/source_folders.py reads the already-cached sender and subject metadata, uses exact email-domain boundaries, and returns stable source_group and source_type IDs.
- GET /api/v1/mail/triage adds those two fields to the existing local read-only projection; manually quarantined messages remain Other.
- static/app.js filters the already-loaded local snapshot, retaining priority columns, native reader, viewed exclusion, selection ceiling, protected-label restrictions, and the existing Trash approval gate.
- No new Gmail OAuth scopes, API requests, background polling, model calls, SQLite tables, message deletion, moving, Gmail label changes, or automatic outgoing actions. No database migration or second scheduler.
- Sender strings are **not authenticated identities**. A spoofed From address can receive a misleading organizational label. Never treat a source folder as proof of authentic email or authorization for a sensitive action. The native Gmail link stays available.
- Only the existing bounded triage sample is classified (currently up to 60 saved insights and up to 60 manual-review records). Folder counts **do not claim full mailbox totals**.
- Filter selection is not persisted in browser storage or SQLite. Locking resets it.

## Checks and acceptance

Run:

    PYTHONPATH=apps/core/src python -m unittest discover -s apps/core/tests -p test_mail_source_folders.py -v
    node --test apps/core/tests/test_inbox_status.cjs

Then run Core CI, governance and JavaScript syntax checks.

Owner-device Firefox acceptance: use previously-synced GitHub PR, Issue and workflow notifications; open each GitHub category; verify correct topic, counts, priority columns, selection and native viewer. Confirm changing filter does not contact Gmail or Ollama, modify labels, or alter the underlying SQLite records. Ambiguous subjects must stay in Other.

Do not deploy from the development branch. Review PR and required checks, then use a SQLite backup and the existing safe main-only production deployment procedure.
