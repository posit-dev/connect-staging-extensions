const express = require("express");
const path = require("path");

const app = express();

// Connect assigns the port through the PORT environment variable; fall back to a
// fixed port for local development.
const PORT = process.env.PORT || 3000;

app.use(express.static(path.join(__dirname, "public")));

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

  const tick = setInterval(() => {
    res.write(`data: ${JSON.stringify(makeTransaction())}\n\n`);
  }, 1000);

  // Comment lines act as heartbeats that keep idle proxies from closing the stream.
  const heartbeat = setInterval(() => res.write(": keep-alive\n\n"), 15000);

  // Stop generating events once the browser disconnects.
  req.on("close", () => {
    clearInterval(tick);
    clearInterval(heartbeat);
  });
});

app.listen(PORT, () => {
  console.log(`Transaction monitor listening on port ${PORT}`);
});
