# Roadie Watcher → SQLite → Publisher → Web UI

> **Status:** conceptual architecture diagram, 2026-10-11. Some publisher HTTP endpoints and precise SQL names in the originally rendered illustration were *illustrative*, not verified against source code. Do not treat them as implementation contracts.

The diagram below is version-controlled Mermaid. The separately generated PNG infographic was not committed as a binary image; Mermaid renders directly on GitHub.

```mermaid
flowchart TD
    A["Watcher cycle: capture fresh Android UI XML via ADB"] --> B{"Verified screen type?"}
    B -->|MAP| C["Parse map marker IDs / clusters"]
    B -->|CAROUSEL| R["Existing open card: recover to MAP safely"]
    B -->|DETAIL| R
    B -->|UNKNOWN / rejected XML| U["Log rejected XML; no blind tap, swipe or DB scan"]
    R --> A
    U --> A
    C --> D{"Any marker or cluster?"}
    D -->|No| E["Remain on MAP; wait for next scan"]
    E --> A
    D -->|Yes| F["Tap verified marker or cluster"]
    F --> G["Capture fresh XML and classify"]
    G --> H{"CAROUSEL?"}
    H -->|No| U
    H -->|Yes| I["Parse FIRST gig_summary_card: price, route, miles, minutes, deliveries, fit"]
    I --> J["Compute gig_key (e.g. 76_11)"]
    J --> K{"Destination already in SQLite?"}
    K -->|No| L["Open Details if safe; capture XML; parse destination; return and verify"]
    K -->|Yes| M["Reuse known destination"]
    L --> N["Persist/merge gig data in SQLite"]
    M --> N
    N --> O{"Verified position_in_stack and total > 1?"}
    O -->|Yes| P["Swipe to next verified card; repeat capture and processing"]
    P --> I
    O -->|No / unverified| Q["No speculative swipe; recover to MAP"]
    Q --> A
    N -.-> S["Publisher: separate process reads SQLite"]
    S --> T["Publisher exposes/transforms data for web consumer — verify exact mechanism in code"]
    T --> V["Web page reads published data and displays gigs"]
```

## Important evidence and limitations

- Real single gig XML contained `gig_card_pager` and `gig_summary_card` but **no** `position_in_stack`. The patched parser synthesizes position `1/1` for that case; do **not** interpret that as proof there are no hidden cards.
- Real fixture parsed as `Screen.CAROUSEL`, key `76_11`, 76 miles, 190 minutes, 11 deliveries, price 150.30.
- After Back, Roadie sometimes displays a blank map without Refresh; watcher rejected screen as UNKNOWN until operator interacted with app. No automatic fix yet.
- Actual single-card end-to-end handling, Details lookup, cluster traversal, Publisher interface and final web fetch route must be confirmed in code/live logs before claiming verified.

See [WATCHER_STATE.md](WATCHER_STATE.md) and [CHANGELOG.md](../CHANGELOG.md).
