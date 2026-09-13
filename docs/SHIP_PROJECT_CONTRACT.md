# SHIP PROJECT CONTRACT

How a project adopts Ship, and what it must provide.

## The project.yml contract

Every project that wants `ship status`/`ship context`, or eventually
deploys, needs a `project.yml` at its root, valid against
`schema/project.schema.json`. `new-project.sh` generates one automatically
(with `deploy.enabled: false`) for every new project from the template.

Fields (see the schema for the authoritative, machine-checked contract):

- `project.{slug,name,type,repo}` — identity. `repo` starts as a `"TBD"`
  placeholder until a real git remote exists; `authorize_deploy()`
  refuses to deploy while it's still a placeholder.
- `context.*` — paths (relative to the project root) to CLAUDE.md,
  memory index, goals/decisions/blockers, graph. Used by `ship context`
  for pure discovery — no interpretation.
- `skills.{preferred,domains}` — hints for skill-router, never a hard
  route (§7 of the originating spec).
- `ci.{test,build}` — paths to this project's own `scripts/ship/test` and
  `scripts/ship/build`. Ship core never knows what's inside them.
- `deploy.{enabled,approval,target,service}` — `enabled: false` by
  default. When `true`, `target`/`service` become required by the schema
  itself (not just convention) — and even then, the CENTRAL REGISTRY
  (`registry/projects.yml`/`targets.yml`), not this file, is what actually
  authorizes a deploy. See `SHIP_SECURITY.md`.
- `health.command` — path to `scripts/ship/health`.

**No secrets, ever.** Unknown fields and invalid values both fail
validation — there is no "extra field, ignored" behavior.

## The 3 commands Ship core knows about

```
scripts/ship/test    exit 0 = tests pass
scripts/ship/build    leaves the deployable output in ./build/
scripts/ship/health   exit 0 = healthy, run AFTER a deploy+restart
```

Ship never inspects what's inside these. A Python project's `test` might
be `pytest`; a trading bot's might be `sanity.py` plus a dozen invariant
checks (temporal integrity, no-lookahead, closed-candle, identity, risk);
a website's might be unit + Playwright + a broken-links check. Ship core
stays ignorant of all of it by design (§10 of the originating spec).

## Adopting Ship on an EXISTING project (not from the template)

1. Copy `project.yml`/`scripts/ship/*`/`.github/workflows/ship.yml` from
   `projects/template/` into the project root.
2. Fill in `project.yml`'s `repo:` once the project has a real git remote.
3. Replace the 3 script stubs with real commands.
4. Validate: `PYTHONPATH=platform/ship .venv/bin/python -c
   "from shiplib.schema import load_project_config;
   load_project_config('path/to/project.yml')"`
5. Deploy stays `enabled: false` until BOTH this file says `true` AND the
   central registry (a separate, human-reviewed decision) lists the
   project as `deployment_allowed: true` for a real, connected target.
