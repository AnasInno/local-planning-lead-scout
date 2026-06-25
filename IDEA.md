# Local Planning Lead Scout

## Persona

A roofer or small trade owner who wants a useful Monday-morning lead shortlist without spending the morning inside council planning portals.

Selected queue item: `IDEA-2026-06-22-01`.

## Pain

Promising roof, loft, extension, and repair jobs are buried among tree works, signage, telecoms, and other low-fit planning records.

## Current workflow

Open public planning portals, search recent records by area, skim descriptions one by one, copy references and addresses into a spreadsheet, then manually decide which jobs deserve follow-up.

## Input

The owner enters a trade, a town/postcode, and a date range. `Manchester` runs fake demo planning records included in the folder; postcode/outcode searches such as `M14` use public planning data near that area.

## Output

An AI-ranked Monday-morning shortlist with:

- address
- planning reference
- AI reason for why it matched
- AI suggested next action
- fit level and fit score
- planning link
- simple CSV download and print view

The deterministic scoring step only preselects candidates. Owner-facing rows require AI fit, reason, and next action before they appear.

## One-day scope

Build a double-click local app that keeps the technical planning lead engine intact while giving owners a simpler workflow: trade and area in, short AI-ranked planning shortlist out.

## Idea filter score

- Pain is boring and common: 2/2
- Input/output are obvious: 2/2
- Demo can run in under 2 minutes: 2/2
- Saves real manual effort: 2/2
- Post/story is clear without hype: 2/2

Total: 10/10

## Rejection risks

- Scraping private planning portals would create data and access risks.
- CRM/email sending would turn a lead scout into an outreach system.
- Applicant names must not be sent to AI or used in outreach copy.
- Live homeowner data must not be committed to samples, fixtures, outputs, or docs.
