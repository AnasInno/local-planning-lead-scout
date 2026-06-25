# Local Planning Lead Scout

Put in your trade and area. Get this week's AI-ranked planning jobs worth checking.

## Quick start: double-click version

### macOS

1. Unzip the folder.
2. Double-click `Start.command`.
3. Paste your Gemini API key once when the app asks for it.
4. Enter your trade, town or postcode, and date range.
5. Click **Find leads**.
6. Download the shortlist CSV or open the print view.

### Windows

1. Unzip the folder.
2. Double-click `Start.bat`.
3. Paste your Gemini API key once when the app asks for it.
4. Enter your trade, town or postcode, and date range.
5. Click **Find leads**.
6. Download the shortlist CSV or open the print view.

The app is designed for owners, not developers: no terminal workflow is needed for normal use.

## Problem

Planning Lead Scout turns recent planning records into a short Monday-morning shortlist for a roofer or local trade business.

It first filters out weak matches with simple rules, then uses AI to add the final owner-facing judgement:

- address
- planning reference
- fit level
- fit score
- why the job matched your trade
- suggested next action
- planning page link

No owner shortlist row is shown unless AI has produced the fit, reason, and next action.

## Choosing an area

- `Manchester` runs the fake demo planning records included in the folder, so you can try the app without live public data.
- Postcode or outcode searches such as `M14` use live public planning data near that area.

The shortlist is for checking opportunities. It does not scrape private portals, send emails, push leads into a CRM, or claim that an applicant has asked to be contacted.

## AI setup

The app asks for a Gemini API key once and stores it locally on your computer. The key is used only to score planning leads into fit, reason, and next action.

Do not paste real keys into shared documents, screenshots, support messages, or committed files.

## Included demo data

The included sample records are fake and public-safe. They are there so the app can be tested without live planning data or real homeowner details.

## Limitations

- Uses public planning records or fake public-safe demo records only.
- No scraping private planning portals.
- No CRM or email sending.
- No applicant names in AI prompts or outreach copy.
- No committed live homeowner data.

## Verification

Owners do not need this section.

```bash
make smoke
python3 -m pytest -q
make package
```
