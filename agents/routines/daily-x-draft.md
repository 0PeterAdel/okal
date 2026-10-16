# Daily X draft

Read the owner's current social topics from the private reviewed profile only
if that profile is available and authorized for this task. Do not include the
profile's name, email, employment history, or other private data in a public
post unless the owner explicitly chose those facts for public use.

Choose one current, verifiable topic with a dated source. For a statement
about Okal, distinguish intended work from released behavior and cite an
exact phrase in a committed repository file. Produce a concise Egyptian
Arabic X draft JSON with `platform`, `text` and an `evidence` array matching
the format in `docs/USE-FIRST-AGENTS.md`. Run
`python3 scripts/check-social-draft.py` on that file. If evidence fails,
report the failure rather than offering a publishable post.

Return the draft path and the checked source paths for owner review. Never
connect to X or Postiz, schedule a platform post, or claim a draft was
published. The owner chooses the exact text and publication time later.
