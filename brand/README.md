# Brand

The JinnVerse logo: a robot genie rising from a lamp, cream and gold on navy, with the wordmark
under it. It replaced the Lustjinn logo on 2026-10-21 (#245): the same mark and the same colours,
only the name changed, so the design tokens drawn from it (`web/src/lib/theme.css`) did not move.

| File | Role |
|---|---|
| `logo.svg` | The source. Everything else is derived from it. |
| `logo.png` | A full-size export (1254×1254), for a quick look; not what ships. |

Where it goes — the PWA's icon set, the waking screen, the header, the course cover — is #92.
The icon set is rendered from the SVG with `node web/scripts/icons.mjs` and committed under
`web/static/icons/`; run it again whenever the logo changes.
