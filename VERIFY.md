# Verification

Standalone open-source release checks run locally before publication.

## Checks

- `make smoke` — PASS, generated `output/owner_shortlist.csv` with 5 AI-ranked fixture leads.
- `python3 -m pytest -q` — PASS, 7 tests passed.
- `make package` — PASS, created `dist/local-planning-lead-scout.zip`.
- `public release safety scan` — PASS.
- Owner browser no-key check — PASS, first load showed setup/search only and searching without a key showed the AI key requirement.
- Owner browser fixture check — PASS, shortlist table rendered, CSV download returned `text/csv`, and print view included `window.print()`.

## Notes

Generated CSV outputs are ignored in this standalone repo. Run `make smoke` to recreate the sample owner shortlist locally.
