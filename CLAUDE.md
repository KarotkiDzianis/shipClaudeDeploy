# Ship — project instructions

> Inherits `~/claude/CLAUDE.md`. This file adds Ship-specific rules.

Ship is infrastructure other projects depend on for deployment. Treat
changes here with more caution than a typical feature project:

1. **Never weaken `shiplib.registry.authorize_deploy()`'s fail-closed
   behavior** without an explicit, deliberate decision — it is the one
   thing standing between a project's own (possibly compromised)
   `project.yml` and an unauthorized production deploy.
2. **Never make `registry/projects.yml`'s `repo:` field anything other
   than a real, verified git remote** before a project can deploy — the
   `"TBD"` placeholder convention exists so this can never be silently
   bypassed (see `test_unregistered_repo_placeholder_refused`).
3. **`shiplib.release.run_deploy()` must always end in `DEPLOYED` or a
   recorded rollback attempt** — never a state where a failure is
   reported but nothing was rolled back and nothing was recorded.
4. **No secrets in `project.yml`, git, or any release artifact, ever** —
   schema's `additionalProperties: false` enforces this; do not add an
   escape hatch.
5. **Ship core stays ignorant of what any given project's `test`/`build`/
   `health` actually do** (§10 of the originating spec) — do not special-
   case TradePulse or any other project's own testing/build logic inside
   `shiplib`.
6. **TradePulse's own Rule 10 (manual, one-command deploy) is unaffected
   by this platform until TradePulse explicitly onboards** — that is a
   separate, later, deliberate decision, not a side effect of anything
   built here.
7. Run the full test suite before considering any change to `shiplib/`
   done: `PYTHONPATH=. .venv/bin/python -m unittest discover tests`.
