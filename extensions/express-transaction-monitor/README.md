# Express: Real-Time Transaction Monitor

An Express app that streams a live feed of card transactions to the browser over
Server-Sent Events (SSE), flagging suspicious ones and keeping running totals up to
date with no page refresh. It's themed as a bank fraud monitor, but the pattern fits
any live event feed. Deploy it as a starting point for streaming your own data to a
dashboard on Connect.

## About this example

The server generates a simulated stream of transactions (about one per second),
applies a few simple fraud rules, and pushes each one to every connected browser.
The page subscribes once and updates in place: new transactions appear at the top of
the feed, flagged ones are highlighted, and the tiles track total volume, transaction
count, and how many were flagged.

Because the data is simulated in the app, it runs the moment you deploy it, with no
database or external service to configure. It's for anyone who wants to serve
live-updating content from Node.js on Connect and see the end-to-end pattern.

## How it works

- **`index.js`** is the Express entrypoint. It serves the dashboard from `public/`
  and exposes `GET /events`, which holds the connection open and writes one
  `text/event-stream` message per second. The response sets `Cache-Control: no-cache`
  and `X-Accel-Buffering: no` so proxies (including Connect's) forward each event
  immediately instead of buffering the stream, and it sends periodic heartbeat
  comments to keep idle connections alive.
- **`public/`** is the browser side, plain HTML, CSS, and JavaScript with no build
  step. `app.js` opens an `EventSource`, then aggregates the running totals and
  renders each transaction as it arrives. All URLs are relative so the app works
  under the content path Connect serves it from.
- **`package.json`** declares `engines.node` (`>=22`), which Connect reads at deploy
  time to pick a matching Node.js version. `package-lock.json` pins the one
  dependency, Express, to the version this was tested with.

## Customize it

- **Use your own data.** Replace `makeTransaction()` in `index.js` with a read from
  your real source: a message queue, a database change feed, or a webhook. Keep
  writing each item to the stream the same way and the dashboard needs no changes.
- **Change the rules.** The fraud checks in `index.js` are intentionally simple. Swap
  them for your own logic, or for the output of a model.
- **Restyle the dashboard.** Edit `public/` to change the columns, the tiles, or the
  look. The colors and layout use accessible defaults that adapt to light and dark.

## Deploy it

Deploy it straight from the Connect Gallery to get a copy running and try it as-is. To
run a customized version, get the
[example source](https://github.com/posit-dev/connect-staging-extensions/tree/main/extensions/express-transaction-monitor),
make your changes, and publish it with a
[git-backed deployment](https://docs.posit.co/connect/user/git-backed/) or the
[`rsconnect` CLI](https://docs.posit.co/connect/user/publishing-cli-notebook/). This
example requires Connect 2026.06.0 or later, the release that added Node.js support.

## Learn more

- [Server-Sent Events (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- [Express](https://expressjs.com/)
- [Node.js content on Connect](https://docs.posit.co/connect/user/nodejs/)
