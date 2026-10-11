# Changelog

## Unreleased — candidate watch-v1.0.1 (2026-10-11)
Branch: `fix/single-marker-carousel-cooldown`. Not yet merged into `main`; not tagged as a release.

- `8f497f3`: classify a single `gig_summary_card` under `gig_card_pager` as CAROUSEL even without `position_in_stack`; carousel takes precedence over map elements behind it.
- `28a40e1`: first attempt at direct-marker summary handling (superseded by later edits).
- `7cb5cdb`: initial single-card parsing change (had undefined `path` bug).
- `1b3c0fc`: direct-marker path now reads first summary and checks destination DB before opening Details.
- `c471dbe`: attempts verified-count multi-card traversal for direct markers.
- `58be45a`: fixes undefined `path` in `roadie_store.fields(nodes)`; reads single summary from node tuples.

### Verified on Mac
- `python3 -m py_compile` succeeded (no output).
- Real XML `76510555_detail_758f7017f64a.xml`: `Screen.CAROUSEL`; position synthesized as `(24,1,1)`; key `76_11`, 76 mi, 190 min, 11 deliveries, price 150.30, easy fit for Ford Mustang Mach-E.
- Standalone in-memory SQLite decision test: unknown destination requires Details; known destination skips; total=1 means zero swipes. **This does not prove Watcher's integration path.**

### Live observation
- At 16:59:48 Oct 11, Watcher started with Roadie on a summary card. At 16:59:50 it recognized CAROUSEL and pressed Back. Subsequent probes were UNKNOWN while Roadie displayed an empty map with no Refresh button; fail-closed prevented further taps. Operator manually moved map/switched apps, Roadie refreshed, and Watcher resumed.
- No new single gig was observed after that recovery. End-to-end processing of single markers, detail DB writes, and multi-card traversal are **not yet confirmed**.
