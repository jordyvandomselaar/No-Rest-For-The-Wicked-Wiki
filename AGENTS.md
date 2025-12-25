# Repository Guidelines

## Project Structure & Module Organization
- `packages/site/` — Astro website. Pages in `packages/site/src/pages/`, layouts in `packages/site/src/layouts/`, styles in `packages/site/src/styles/`, static assets in `packages/site/public/`.
- `packages/crawler/` — Data-mining scripts. Entry points in `packages/crawler/src/`.
- Generated data lives in `packages/crawler/out/` (e.g., `items.json`).
- Root `package.json` uses npm workspaces (`packages/*`).

## Build, Test, and Development Commands
- `npm install` — install workspace dependencies.
- `npm run dev` — run the Astro site (`@nrftw/site`).
- `npm run build` — build the Astro site.
- `npm run preview` — preview the site build.
- `npm run crawl -w @nrftw/crawler` — scan Unity bundles (see `packages/crawler/src/crawl_items.py`).
- `npm run items -w @nrftw/crawler` — regenerate `packages/crawler/out/items.json`.

Tip: If port 4321 is blocked, run `npm run dev -w @nrftw/site -- --port 4322`.

## Coding Style & Naming Conventions
- JavaScript/TypeScript, Astro, and Python are used.
- Follow existing formatting (2-space indentation, double quotes in JS/TS).
- Prefer descriptive, lowercase file names for pages (e.g., `items.astro`, `items/[id].astro`).

## Testing Guidelines
- No formal test suite is configured yet.
- For changes to crawler output, regenerate `packages/crawler/out/items.json` and sanity-check key items.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative, and descriptive (e.g., “Work on crawler”, “add starter wiki docs and sidebar nav”).
- PRs should include a brief description of changes and how to verify (commands + expected behavior). Add screenshots for UI changes.

## Data & Content Notes
- Item data is derived from the game install and `quantumDatabase.bin`.
- Update site pages after data changes by regenerating `items.json` and rebuilding the site.
