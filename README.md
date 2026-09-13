# Ship

Generic release/deployment foundation for `~/claude` workspace projects.
TradePulse is one future consumer — nothing here is TradePulse-specific,
and TradePulse itself is untouched (see `docs/SHIP_V0_ARCHITECTURE.md`).

```
commit → GitHub Actions tests → build → package → artifact SHA256
       → Telegram approval → self-hosted deploy runner
       → atomic install/switch → verify → restart → health
       → DEPLOYED, or auto-rollback
```

## Quick start (for a project already using the template)

```bash
cd platform/ship
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/python -m unittest discover tests   # 49/49 passing
PYTHONPATH=. .venv/bin/python cli/ship status <project-slug>
PYTHONPATH=. .venv/bin/python cli/ship context <project-slug>
```

## Read next

- `docs/SHIP_V0_ARCHITECTURE.md` — what's built, tested, and what's
  genuinely NOT connected to anything real yet (read this one first)
- `docs/SHIP_PROJECT_CONTRACT.md` — how a project adopts Ship
- `docs/SHIP_RELEASE_MODEL.md` — the release object and atomicity guarantees
- `docs/SHIP_TELEGRAM_APPROVAL.md` — the approval protocol
- `docs/SHIP_DEPLOYMENT.md` — the deploy sequence and rollback contract
- `docs/SHIP_SECURITY.md` — the registry-as-authority threat model
