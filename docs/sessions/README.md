# Browser sessions (Release Health): v10 vs v11

How Release Health sessions and trace shape compare across SDK versions and session
lifecycles in the React app. Every capture was recorded from Spotlight while running
the same scenario.

## Scenario

1. Load `/`, then go client-side to `/products` → `/about` → `/products`.
2. Add to cart → `/cart` → `/checkout-form`, then submit and land on `/complete`.
3. Do a full page load of `/?crash=true&errnum=1`, which throws an uncaught ReferenceError.
4. Do a full page load of `/about`.

That's three page loads and seven client-side navigations.

## Capture it yourself

```bash
docker compose -f docker-compose.yaml -f docker-compose.spotlight.yaml up -d spotlight flask
curl -sN -H 'Accept: text/event-stream' http://localhost:8969/stream > capture.txt
# run the scenario in the browser, then:
python3 docs/sessions/summarize.py capture.txt
```

Restart the `spotlight` container before each capture. New subscribers get its buffered
envelopes replayed.

## Results

| | v10.47, `lifecycle: 'route'` (v10 default) | v10.47, `lifecycle: 'page'` | v11.8, `lifecycle: 'page'` (v11 default) |
|---|---|---|---|
| Session IDs for the scenario | 8 (one per load and per navigation) | 1 visible* | 3, one per page load (the run had a 4th load whose session was lost, see Caveats) |
| Status for the uncaught error | `crashed` | `crashed` | `unhandled` |
| Browser `transaction` events | yes | 13 | **0** |
| Browser spans | nested in transactions | nested in transactions | 128 streamed spans across 12 segments |
| App tags (`customerType`, `api`, …) on spans | as transaction tags | as transaction tags | as span attributes (via `setAttributes`) |

Files: [v10-route.txt](v10-route.txt), [v10-page.txt](v10-page.txt), [v11-page.txt](v11-page.txt),
[v11-page-with-user.txt](v11-page-with-user.txt).

\* v10's Spotlight integration only starts forwarding in `afterAllSetup`, but the session
integration sends the initial `ok` session during setup. Spotlight therefore never sees
that first envelope, while sentry.io still receives it. v11 defers the session send until
the browser is idle, so Spotlight gets it.

## What sessions change, and what they don't

- Sessions are their own envelope item (`session`). They feed Release Health
  (crash-free sessions and users, adoption). They are **not** part of a trace, so turning
  them on or off, or choosing `'page'` vs `'route'`, leaves the shape of traces and spans
  unchanged.
- `'route'` inflates session counts (one visit here produced 8 sessions) and dilutes the
  crash-free rate. `'page'` gives one session per real page load.
- The trace-shape change comes from **span streaming**, the v11 default
  (`traceLifecycle: 'stream'`). There is no `transaction` event any more: each finished
  span is sent in small batches, and the pageload/navigation root becomes a "segment" span.
  Scope tags no longer reach spans; only attributes do.
- Browser → Flask distributed traces still stitch on v11. Every Flask transaction's
  `trace_id` matched a browser segment.

## v11 changes made in `react/src/index.js`

- `@sentry/react` and `@sentry/webpack-plugin` bumped to `~11.8.0` / `^11.8.0`.
- Removed `enableLogs` and `enableMetrics`, which v11 dropped. Logs and metrics are now
  captured whenever you use their APIs.
- Scope tags are mirrored as scope attributes, so spans stay filterable by `customerType`,
  `api`, `backendType`, `frontendSlowdown`, `se` and `cexp`. Tags are kept because errors,
  and the fetch wrapper that forwards them as headers to Flask, still use them.
- The user is now also set on the isolation scope (`Sentry.setUser`). Sessions read the
  user from there. Without it, every `'page'` session had `did=None`, so Crash Free Users
  had no data.

## Caveats

- `sendDefaultPii` was unset, and v11 replaces it with `dataCollection`, whose defaults
  are more permissive: cookies, HTTP bodies, user info. That's fine for a demo, but check
  it before reusing this config for a customer.
- Because v11 waits for idle before sending a session, an ok session can be lost if the
  page is left before the idle callback fires. This happened once here, in a background
  (hidden) tab on the busy `/products` page.
- Web vitals: on v11 CLS/LCP/INP are separate spans, and in Chromium 151+ they are
  reported per soft navigation. Expect page-load vitals to drop compared with v10.
