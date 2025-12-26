# No Rest For The Wicked Wiki Monorepo

This repo is split into multiple packages.

## Packages

- `packages/site` — Astro website for the community wiki.
- `packages/crawler` — Asset crawler / data mining tooling.

## Quick start

```sh
bun install
bun run dev
```

## Package commands

```sh
bun run --cwd packages/site dev
bun run --cwd packages/site build
bun run --cwd packages/site preview
```
