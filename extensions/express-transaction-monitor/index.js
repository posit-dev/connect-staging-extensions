const express = require("express");
const path = require("path");

const app = express();
app.use(express.json());

// Connect assigns the port through the PORT environment variable; fall back to a
// fixed port for local development.
const PORT = process.env.PORT || 3000;

// The feed is simulated here so the app runs with no external source. Swap
// makeTransaction() for a real one (a queue, a database change feed, a webhook) to
// adapt it.
const MERCHANTS = [
  { name: "Blue Bottle Coffee", category: "Dining" },
  { name: "Whole Foods Market", category: "Groceries" },
  { name: "Shell", category: "Fuel" },
  { name: "Delta Air Lines", category: "Travel" },
  { name: "Apple Store", category: "Electronics" },
  { name: "Steam", category: "Games" },
  { name: "Uber", category: "Transport" },
  { name: "CVS Pharmacy", category: "Health" },
  { name: "Best Buy", category: "Electronics" },
  { name: "Marriott", category: "Travel" },
];

// A few non-US locations so some transactions look cross-border.
const LOCATIONS = [
  { city: "New York", country: "US" },
  { city: "Chicago", country: "US" },
  { city: "Austin", country: "US" },
  { city: "Seattle", country: "US" },
  { city: "London", country: "GB" },
  { city: "Lagos", country: "NG" },
  { city: "Bucharest", country: "RO" },
];

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

let nextId = 1;

// The fraud rules are deliberately simple; this is where you would plug in a real
// model or rules engine.
function makeTransaction() {
  const merchant = pick(MERCHANTS);
  const location = pick(LOCATIONS);
  // Most charges are small; occasionally generate a large one.
  const amount =
    Math.random() < 0.15
      ? Math.round((500 + Math.random() * 4500) * 100) / 100
      : Math.round((2 + Math.random() * 200) * 100) / 100;
  const cardLast4 = String(1000 + Math.floor(Math.random() * 9000));

  let flagReason = null;
  if (amount > 2000) {
    flagReason = "Unusually large amount";
  } else if (location.country !== "US" && amount > 300) {
    flagReason = "High-value charge outside the US";
  } else if (merchant.category === "Electronics" && location.country !== "US") {
    flagReason = "Electronics purchase from a new region";
  }

  return {
    id: nextId++,
    time: new Date().toISOString(),
    amount,
    merchant: merchant.name,
    category: merchant.category,
    city: location.city,
    country: location.country,
    cardLast4,
    status: flagReason ? "flagged" : "approved",
    flagReason,
  };
}

// Shared server-side state, so every connected analyst sees the same feed, the same
// review queue, and the same running totals. This lives in memory in one process, so
// deploy the content with Max processes set to 1 (see the README).
const clients = new Set(); // connected browsers, for broadcasting
const reviewQueue = []; // flagged transactions still awaiting review
const escalatedLog = []; // confirmed-fraud transactions, kept for follow-up
const totals = { count: 0, volume: 0, flagged: 0, escalated: 0 };

const MAX_QUEUE = 50; // cap the pending queue so an unwatched feed can't grow forever
const MAX_ESCALATED = 50; // cap the escalated log the same way

// The pending count is just the queue length; bundle it with the totals the tiles show.
function stats() {
  return { ...totals, pending: reviewQueue.length };
}

// Send one Server-Sent Event to every connected browser.
function broadcast(event, data) {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  for (const res of clients) res.write(payload);
}

// --- Viewer identity (the Connect-flavored part) ---
// Connect injects these into the content's environment at runtime.
const CONNECT_SERVER = process.env.CONNECT_SERVER;
const CONNECT_API_KEY = process.env.CONNECT_API_KEY;
const viewerNames = new Map(); // session token -> resolved name, cached per process

// Resolve who is making a request from their Connect identity, so review actions are
// attributed to the real signed-in analyst instead of something the browser claims.
// Falls back to a generic label off Connect or without the Visitor API Key integration,
// so the app still runs everywhere.
async function resolveViewer(req) {
  const token = req.get("Posit-Connect-User-Session-Token");
  // No token means we are off Connect or nobody is signed in; nothing to prompt for.
  if (!token || !CONNECT_SERVER || !CONNECT_API_KEY) {
    return { name: "Anonymous analyst", status: "anonymous" };
  }
  if (viewerNames.has(token)) {
    return { name: viewerNames.get(token), status: "signed-in" };
  }

  try {
    const base = CONNECT_SERVER.replace(/\/$/, "");
    // Exchange the viewer's session token for a short-lived key scoped to them.
    // A slow or unreachable Connect API shouldn't hang the page load, so bound
    // each call: an unconfigured integration should fail fast, not stall.
    const credRes = await fetch(
      `${base}/__api__/v1/oauth/integrations/credentials`,
      {
        method: "POST",
        headers: {
          Authorization: `Key ${CONNECT_API_KEY}`,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: new URLSearchParams({
          grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
          subject_token_type: "urn:posit:connect:user-session-token",
          subject_token: token,
          requested_token_type: "urn:posit:connect:api-key",
        }),
        signal: AbortSignal.timeout(3000),
      },
    );
    if (!credRes.ok) throw new Error(`credential exchange failed: ${credRes.status}`);
    const { access_token } = await credRes.json();

    // Ask Connect who that key belongs to. Using the viewer's own key means Connect
    // answers with the viewer, not with this app's owner.
    const meRes = await fetch(`${base}/__api__/v1/user`, {
      headers: { Authorization: `Key ${access_token}` },
      signal: AbortSignal.timeout(3000),
    });
    if (!meRes.ok) throw new Error(`whoami failed: ${meRes.status}`);
    const me = await meRes.json();

    const name =
      `${me.first_name || ""} ${me.last_name || ""}`.trim() ||
      me.username ||
      "Analyst";
    viewerNames.set(token, name);
    return { name, status: "signed-in" };
  } catch (err) {
    // On Connect but the exchange failed, most often because the Visitor API Key
    // integration is not configured. Report that so the browser can prompt for it.
    console.error("Viewer identity lookup failed:", err.message);
    return { name: "Anonymous analyst", status: "unconfigured" };
  }
}

// Serve a setup screen instead of the dashboard when the Visitor API Key
// integration isn't configured, so a misconfigured deployment can't be used
// (and silently attribute every review to "Anonymous analyst") before it's fixed.
app.get("/", async (req, res, next) => {
  const { status } = await resolveViewer(req);
  if (status === "unconfigured") {
    return res.sendFile(path.join(__dirname, "public", "setup.html"));
  }
  next();
});

app.use(express.static(path.join(__dirname, "public")));

// Who is viewing, shown in the header (with a setup prompt when identity is off).
app.get("/whoami", async (req, res) => {
  res.json(await resolveViewer(req));
});

app.get("/events", (req, res) => {
  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    // Tell nginx-style proxies (including Connect's) not to buffer the stream, so
    // events reach the browser as they happen instead of in batches.
    "X-Accel-Buffering": "no",
  });
  res.flushHeaders();
  clients.add(res);

  // Seed the new browser with the shared state, so an analyst who joins late sees the
  // current totals and everything still awaiting review, not just what happens next.
  res.write(
    `event: snapshot\ndata: ${JSON.stringify({ stats: stats(), queue: reviewQueue, escalated: escalatedLog })}\n\n`,
  );

  // Comment lines act as heartbeats that keep idle proxies from closing the stream.
  const heartbeat = setInterval(() => res.write(": keep-alive\n\n"), 15000);

  req.on("close", () => {
    clearInterval(heartbeat);
    clients.delete(res);
  });
});

// An analyst acknowledges (looks fine) or escalates (real fraud) a flagged transaction.
app.post("/review", async (req, res) => {
  const { id, action } = req.body || {};
  if (action !== "acknowledge" && action !== "escalate") {
    return res.status(400).json({ error: "Unknown action" });
  }

  const idx = reviewQueue.findIndex((t) => t.id === id);
  if (idx === -1) {
    // Another analyst already reviewed it, or it aged off the queue.
    return res.status(409).json({ error: "Already reviewed" });
  }
  const [tx] = reviewQueue.splice(idx, 1);

  const { name: by } = await resolveViewer(req);
  const at = new Date().toISOString();

  if (action === "escalate") {
    totals.escalated += 1;
    // Escalating should leave a durable trail to follow up on, not just tick a
    // counter, so keep the transaction (not just its id) in a standing log.
    escalatedLog.unshift({ ...tx, reviewedBy: by, reviewedAt: at });
    while (escalatedLog.length > MAX_ESCALATED) escalatedLog.pop();
  }

  // Tell every browser who reviewed it, so the shared queue updates live for everyone.
  broadcast("review", { id, action, by, at, tx, stats: stats() });
  res.json({ ok: true });
});

// One shared feed for the whole server: generate a transaction each second and push it
// to every connected browser. Pause when nobody is watching so the totals only reflect
// activity someone actually saw.
setInterval(() => {
  if (clients.size === 0) return;

  const tx = makeTransaction();
  totals.count += 1;
  totals.volume += tx.amount;
  if (tx.status === "flagged") {
    totals.flagged += 1;
    reviewQueue.unshift(tx);
    while (reviewQueue.length > MAX_QUEUE) reviewQueue.pop();
  }
  broadcast("transaction", { tx, stats: stats() });
}, 1000);

app.listen(PORT, () => {
  console.log(`Transaction monitor listening on port ${PORT}`);
});
