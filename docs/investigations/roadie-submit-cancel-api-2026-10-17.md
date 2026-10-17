# Roadie Driver Submit/Cancel API investigation — 2026-10-17

> **Handoff / investigation log.** Status: endpoints and methods confirmed from app telemetry; request body and authentication details **not** captured. This is a research record, not a working API client. All observations below are from the **Samsung test device**, not the production Motorola. No API requests were replayed.

## 1. Goal and boundaries

Longer-term idea: a local Roadie offer dashboard showing dozens of nearby offers (approximately 50–60 when available), with a user-selected offer and a deliberate **Submit** action. The existing Watcher/Publisher and the production Motorola must remain untouched. First establish what the official Android app does, then decide whether an integration is viable and permitted. No autonomous offers, repeated submissions, or speculative calls.

**Devices and environment**
- Mac: **NZMAC**, macOS Terminal, ADB, Python 3.
- **Test** device: rooted **Samsung Galaxy A04**, ADB serial `R92W7087QDX`, Android 13.
- Test package: `com.roadie.drive.android.app`, app version **2.147.0** as recorded in analytics.
- **Production** device: separate Motorola, not used for this test and **must not be touched**.
- **Important existing artifact**: an APK was **previously extracted from the Motorola and reportedly exists in the Mac's Downloads directory**. Its exact filename, version, and path have **not yet been reverified** in this session. **Do not blindly pull another APK** before checking Downloads and comparing versions. The last proposed Samsung APK pull command was not executed in the visible log.

## 2. Prior app/data findings

The rooted test app has a SQLite database:

`/data/data/com.roadie.drive.android.app/databases/driver_route.db`

Observed table: `consolidation`, with `payloadJson` storing offer data. Opening a map marker/carousel loads multiple offer records into the database, potentially allowing an independent read-only display of available offers. The prior reliable database-copy approach was a **rooted tar snapshot on the phone**, followed by `adb pull`; an earlier `adb exec-out cat` attempt yielded a corrupt database copy. The actual schema, record count and freshness rules should be revalidated before implementing a live dashboard. Do not conflate a cached offer with a currently actionable offer.

Other observed read-side HTTP requests:
- `GET /consolidations/details?ids=76936393,76944197&latitude=…&longitude=…`
- `GET /consolidations/76944197/detail`
- `GET /v1/consolidations/item-descriptors?legacy_ids=76944197`
- `POST /consolidations/search` (search, **not** Submit)
- `POST /v1/consolidations/fit-check?ids=…`
- `GET /my_profile/offers?duration=168h`

The OkHttp disk cache `*.0` files include request URLs, method, response metadata and **sensitive Set-Cookie values**. The `*.1` files can contain cached bodies. **Never commit raw cache files, session cookies, authorization headers, full logcat or private location/profile data to this public repository.**

## 3. One real manual test (October 17, 2026, Eastern time)

The operator used the **official Roadie Android UI** on Samsung to submit an offer and then cancel that same offer.

- Example `consolidation_id`: **76944197**
- Displayed price at the time: **$35.57** (historical test offer, not a current offer).
- Approx. **18:26:59 EDT**: user tapped Submit in app.
- Approx. **18:27:34–35 EDT**: user canceled the submitted offer in app.
- Phone log captured at `/sdcard/roadie_submit.log`, pulled to Mac `/tmp/roadie_submit.log` (~1.4 MB).
- These actions were **manual**. We did **not** execute a standalone API request or establish that one would work.

### 3.1 Analytics — useful timestamps but not business endpoints

Selected logcat evidence (timestamps EDT):

```text
18:26:59.149 D/DismissRouteComplete: showTransition type: SHOW_SUBMITTING
18:26:59.393 D/AnalyticsEvent: Send Event perform_gig_submit_offer ... {consolidation_id=76944197, fit_check_level=unavailable}
18:26:59.965 D/AnalyticsManager: Successfully sent Roadie Event ... eventName=perform_gig_submit_offer ... consolidationId=76944197
18:27:34.928 D/DismissRouteComplete: showTransition type: SHOW_SUBMITTING
18:27:35.414 D/AnalyticsEvent: Send Event perform_gig_cancel_offer ... {consolidation_id=76944197}
18:27:35.420 D/DismissRouteComplete: showTransition type: OFFER_CANCELED
18:27:35.847 D/AnalyticsManager: Successfully sent Roadie Event ... eventName=perform_gig_cancel_offer ... consolidationId=76944197
```

**Do not mistake analytics `perform_gig_submit_offer` and `perform_gig_cancel_offer` for actual submission/cancellation API calls.** They report events to analytics providers.

### 3.2 Actual HTTP requests found in Sentry breadcrumbs

The critical breakthrough was reading Sentry HTTP breadcrumbs stored locally on the rooted test phone:

`/data/data/com.roadie.drive.android.app/cache/sentry/<installation-specific-id>/.scope-cache/breadcrumbs.json`

Although named `breadcrumbs.json`, it contains binary prefixes/record framing; a direct `grep` printed only “Binary file ... matches”. Piping through `strings` exposed individual JSON events.

**Confirmed Submit:**

```http
POST https://api.roadie.com/consolidations/76944197/offers?fit_check=unavailable
HTTP/2 200
request_content_length: 428
response_content_length: 606
start: 2026-10-17T22:26:59.161Z
end:   2026-10-17T22:26:59.391Z
```

- 230 ms round trip as measured by breadcrumb timestamps.
- The `fit_check=unavailable` **query parameter** is directly observed.
- **The 428-byte request body is unknown**; breadcrumbs contain its length only.
- Response JSON/body is also unknown; only 606-byte response length and HTTP 200 were observed.
- The URL in breadcrumb's `url` field omits the query; the separate `http.query` field supplies `fit_check=unavailable`.

**Confirmed Cancel:**

```http
PATCH https://api.roadie.com/consolidations/76944197/offers/516770066/cancel
HTTP/2 200
request_content_length: 0
start: 2026-10-17T22:27:34.932Z
end:   2026-10-17T22:27:35.413Z
```

- 481 ms round trip.
- The **offer ID 516770066** is **not** the same as the consolidation ID 76944197. A subsequent cancellation requires the specific created offer ID.
- The cancel request had **zero-byte body** in this observation.
- No evidence yet for required authentication headers, CSRF, signatures, nonce, or server-side checks. Do not assume a bare HTTP client can perform either action.

**Related near-time events:**

```text
22:26:57.634Z POST /consolidations/search                  200
22:26:59.161Z POST /consolidations/76944197/offers      200
22:27:31.294Z GET  /consolidations/76944197/detail     200
22:27:31.296Z POST /v1/consolidations/fit-check         200
22:27:34.932Z PATCH /consolidations/76944197/offers/516770066/cancel 200
```

The Android UI also emitted a `StopTransitionView` class-cast error involving `ConsolidationDetailDialog` and `ActiveRouteFragment` around Submit/Cancel. The business calls nonetheless returned 200; no causal impact has been established.

## 4. Exact read-only discovery commands that worked

**Find relevant local files (Samsung only):**

```bash
adb -s R92W7087QDX shell "su -c 'grep -rilE \"offer|submit|cancel|76944197\" /data/data/com.roadie.drive.android.app/cache 2>/dev/null | head -30'"
```

**Find HTTP breadcrumbs without dumping the raw binary cache** (outputs may contain personal metadata; inspect locally before sharing):

```bash
adb -s R92W7087QDX shell "su -c 'cat /data/data/com.roadie.drive.android.app/cache/sentry/*/.scope-cache/breadcrumbs.json'" | strings | grep -iE 'submit|cancel|offer|consolidation|POST|DELETE|PATCH' | tail -30 | cut -c 1-300
```

**Parse the Submit breadcrumb as JSON** (the recorded test ID is historical):

```bash
adb -s R92W7087QDX shell "su -c 'cat /data/data/com.roadie.drive.android.app/cache/sentry/*/.scope-cache/breadcrumbs.json'" | strings | grep '"path":"/consolidations/76944197/offers"' | sed -E 's/^[^{]*//' | python3 -c 'import sys,json; [print(json.dumps(json.loads(x),indent=2)) for x in sys.stdin]'
```

**APK paths on Samsung, obtained with `pm path`:**

```text
/data/app/~~DIaRW_qD4phs0n_4MVGKXQ==/com.roadie.drive.android.app-JbgGbXjzGUtEPokFI6PSdg==/base.apk
/data/app/~~DIaRW_qD4phs0n_4MVGKXQ==/com.roadie.drive.android.app-JbgGbXjzGUtEPokFI6PSdg==/split_config.arm64_v8a.apk
/data/app/~~DIaRW_qD4phs0n_4MVGKXQ==/com.roadie.drive.android.app-JbgGbXjzGUtEPokFI6PSdg==/split_config.xhdpi.apk
```

Those install paths are device/version-specific and will change after updates. **Do not copy these paths as stable references.** Prior `pm path` command was successful; a subsequent `adb pull` was only **suggested**, not confirmed executed.

## 5. What is proven vs. not proven

| Question | Status |
| --- | --- |
| Official Android app submits via `POST /consolidations/{id}/offers` | **Confirmed** for one manual UI action |
| Submit query includes `fit_check=unavailable` in this case | **Confirmed** |
| Submit body size was 428 bytes | **Confirmed** |
| Exact Submit body fields/values | **Unknown** |
| Official Android app cancels via `PATCH /consolidations/{id}/offers/{offer_id}/cancel` | **Confirmed** for one manual UI action |
| Cancel body size was 0 bytes | **Confirmed** |
| Successful response code for both actions | **200 observed** |
| Authentication/session requirements | **Unknown** |
| Offer ID can be obtained from Submit response | **Plausible, not confirmed** |
| Standalone client can safely Submit/Cancel | **Not tested** |
| Bulk list of 50–60 actionable offers is always available | **Not proven** |
| Motorola APK already exists in Mac Downloads | **Operator reports yes; exact path/version unverified** |
| Samsung APK was pulled in this investigation | **No confirmation** |

## 6. Next actions — read-only first

1. **Check Mac Downloads for the previously extracted Motorola APK**; record its filename, app version and hash. Compare version to Samsung app 2.147.0. Avoid redundant download.
2. Inspect APK **offline** with an existing Java/Kotlin decompiler (e.g. JADX if already installed, or install only with operator consent). Search for the Retrofit/OkHttp declaration of `/consolidations/{id}/offers`, associated request DTO/data class, JSON serialization, and the `fit_check` query parameter.
3. Establish the **exact 428-byte request schema** from static code where possible. Record required fields, defaults, and whether device/location data is included; redact all real credentials.
4. Identify how the **offer ID** is obtained from the Submit response or local model before Cancel. Do not infer response structure from the URL.
5. Review whether an **authorized, supported** integration exists. Prefer official UI or supported interfaces if direct API use would be fragile or violate service terms.
6. Only after review, decide on a **controlled manual test**; obtain explicit operator permission for any action that could submit/cancel a real offer.
7. For dashboard data, independently validate SQLite freshness and reconciliation with visible offers. Keep production Watcher/Publisher unchanged.

## 7. Operator workflow and safety rules

- **One terminal command per assistant turn**, then wait for the output.
- Russian explanations; Mac/Android UI menu names in English.
- Explicitly target `-s R92W7087QDX` for Samsung. Never use unqualified ADB commands when multiple devices may be connected.
- No modifications to production Motorola, existing Watcher, Publisher, Watchdog, or production SQLite.
- Never blind-tap an unknown screen, silently submit a real offer, or claim an API call worked without testing.
- Keep secrets, cookies, access tokens, private profile identifiers, and raw location traces **out of GitHub**. This repository is public.
- Continue this investigation from **this file**, rather than repeating prior extraction or confusing analytics events with HTTP endpoints.

## 8. Sources and provenance

Source: operator-supplied terminal output in the Roadie project conversation, October 17, 2026. Local evidence on NZMAC: `/tmp/roadie_submit.log` (may be ephemeral). Phone: `/sdcard/roadie_submit.log` and Sentry breadcrumb cache (may rotate). This document captures observed facts without publishing sensitive raw evidence.
