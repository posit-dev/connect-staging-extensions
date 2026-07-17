# Express: Real-Time Transaction Monitor

## About this example

An Express app that streams a live feed of card transactions to the browser over
Server-Sent Events (SSE) and turns the flagged ones into a shared review queue that a
team can work at once. It is themed as a bank fraud monitor, but the pattern fits any
live, collaborative dashboard: data arrives on its own, people act on it, and everyone
sees the results in real time.

The example shows three things a Node.js app can do on Connect:

- **Stream server data to the browser** as it happens, with no polling and no page
  refresh.
- **Share state across every viewer**, so all of them see the same feed, the same
  review queue, and the same running totals.
- **Use the viewer's Connect identity**, so each review action is attributed to the
  real signed-in person.

The feed is simulated (about one transaction per second) and the fraud rules are a few
simple checks, so the app runs the moment you deploy it with no database or external
service to configure.

## How it works

- **`index.js`** is the Express entrypoint. It serves the dashboard from `public/` and
  exposes three routes:
  - `GET /events` holds the connection open and pushes each new transaction as an SSE
    message. When a browser connects, the server first sends a snapshot of the current
    totals and review queue, so someone who joins late sees the shared state instead of
    only what happens next. The response sets `Cache-Control: no-cache` and
    `X-Accel-Buffering: no` so proxies (including Connect's) forward each event
    immediately, and it sends heartbeat comments to keep idle connections alive.
  - `POST /review` records that an analyst acknowledged or escalated a flagged
    transaction, then broadcasts the result to every connected browser.
  - `GET /whoami` returns the signed-in viewer's name for the header.

  The feed, the review queue, and the totals live in memory in a single process, so
  every viewer shares the same state (see **Deploy it**).
- **Viewer identity.** To attribute a review action, the server reads the
  `Posit-Connect-User-Session-Token` header that Connect adds to each request,
  exchanges it for a short-lived key scoped to that viewer, and asks Connect who they
  are. Off Connect, or without the Visitor API Key integration, it falls back to
  "Anonymous analyst" so the app still runs everywhere.
- **`public/`** is the browser side, plain HTML, CSS, and JavaScript with no build step.
  `app.js` opens an `EventSource`, renders the review queue and the live feed, and posts
  review actions back to the server. All URLs are relative so the app works under the
  content path Connect serves it from.
- **`package.json`** declares `engines.node` (`>=22`), which Connect reads at deploy
  time to pick a matching Node.js version. `package-lock.json` pins the one dependency,
  Express, to the version this was tested with.

## Customize it

- **Use your own data.** Replace `makeTransaction()` in `index.js` with a read from your
  real source: a message queue, a database change feed, or a webhook. Keep broadcasting
  each item the same way and the dashboard needs no changes.
- **Change the rules.** The fraud checks in `index.js` are intentionally simple. Swap
  them for your own logic, or for the output of a model.
- **Change the workflow.** The review actions are acknowledge and escalate. Swap them
  for your own, and write each decision to a database instead of in-memory state if you
  need it to persist.
- **Restyle the dashboard.** Edit `public/` to change the columns, the tiles, or the
  look. The colors and layout use accessible defaults that adapt to light and dark.

## Deploy it

Deploy it straight from the Connect Gallery to get a copy running and try it as-is. Two
content settings make it work well:

- **Set Max processes to 1** (content settings, **Runtime**). The feed, review queue,
  and totals are shared in one process's memory, so more than one process would give
  different viewers different state. Setting Min processes to 1 as well keeps the feed
  running between visits.
- **Add the Connect Visitor API Key integration** (content settings, **Access**) to
  show viewer names on review actions. Without it the app still runs and attributes
  actions to "Anonymous analyst".

To run a customized version, get the
[example source](https://github.com/posit-dev/connect-staging-extensions/tree/main/extensions/express-transaction-monitor),
make your changes, and publish it with a
[git-backed deployment](https://docs.posit.co/connect/user/git-backed/) or the
[rsconnect Python CLI](https://docs.posit.co/rsconnect-python/) (`rsconnect deploy
manifest`). Requires Connect 2026.06.0 or later, the release that added Node.js support.

## Learn more

- [Server-Sent Events (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [Express](https://expressjs.com/)
- [Node.js content on Connect](https://docs.posit.co/connect/user/nodejs/)
- [OAuth integrations and viewer identity on Connect](https://docs.posit.co/connect/user/oauth-integrations/)
