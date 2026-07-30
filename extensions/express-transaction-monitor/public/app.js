const queueEl = document.getElementById("queue");
const escalatedEl = document.getElementById("escalated");
const feedRowsEl = document.getElementById("rows");
const viewerEl = document.getElementById("viewer");
const statusEl = document.getElementById("status");
const statusTextEl = document.getElementById("status-text");

const MAX_ROWS = 50; // Keep the live feed short; older rows drop off the bottom.
const MAX_ESCALATED_ROWS = 50; // Matches the server's escalatedLog cap.
const RESOLVED_LINGER_MS = 5000; // How long a reviewed item stays, so its outcome is seen.

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});
const compactMoney = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  notation: "compact",
  maximumFractionDigits: 1,
});

function setStatus(state, text) {
  statusEl.dataset.state = state;
  statusTextEl.textContent = text;
}

// The server is the source of truth for the totals; the tiles just render what it sends.
function renderStats(stats) {
  document.getElementById("stat-volume").textContent = compactMoney.format(stats.volume);
  document.getElementById("stat-count").textContent = stats.count.toLocaleString();

  const pendingEl = document.getElementById("stat-pending");
  pendingEl.textContent = stats.pending.toLocaleString();
  pendingEl.classList.toggle("alert", stats.pending > 0);

  document.getElementById("stat-escalated").textContent = stats.escalated.toLocaleString();
}

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text;
  if (className) td.className = className;
  return td;
}

function statusCell(tx) {
  const td = document.createElement("td");
  const pill = document.createElement("span");
  pill.className = `pill ${tx.status}`;
  // Icon plus label, so the status is never signaled by color alone.
  pill.textContent = tx.status === "flagged" ? "⚠ Flagged" : "✓ Approved";
  td.appendChild(pill);
  return td;
}

// --- Review queue: the shared, collaborative part ---

async function review(id, action, buttons) {
  // Disable both buttons immediately so a double-click can't send the action twice.
  buttons.forEach((b) => (b.disabled = true));
  try {
    const res = await fetch("review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, action }),
    });
    // 409 means another analyst got there first; the "review" event will resolve the row.
    if (!res.ok && res.status !== 409) throw new Error(`review failed: ${res.status}`);
  } catch (err) {
    console.error(err);
    buttons.forEach((b) => (b.disabled = false));
  }
}

function addQueueItem(tx) {
  const placeholder = queueEl.querySelector(".empty");
  if (placeholder) placeholder.remove();

  const row = document.createElement("div");
  row.className = "queue-item new";
  row.dataset.id = tx.id;

  const info = document.createElement("div");
  info.className = "queue-info";
  const title = document.createElement("div");
  title.className = "queue-title";
  title.textContent = `${money.format(tx.amount)} · ${tx.merchant}`;
  const meta = document.createElement("div");
  meta.className = "queue-meta";
  meta.textContent = `${tx.city}, ${tx.country} · card ••${tx.cardLast4} · ${tx.flagReason}`;
  info.append(title, meta);

  const actions = document.createElement("div");
  actions.className = "queue-actions";
  const ack = document.createElement("button");
  ack.className = "btn btn-ack";
  ack.textContent = "Acknowledge";
  const esc = document.createElement("button");
  esc.className = "btn btn-escalate";
  esc.textContent = "Escalate";
  const buttons = [ack, esc];
  ack.addEventListener("click", () => review(tx.id, "acknowledge", buttons));
  esc.addEventListener("click", () => review(tx.id, "escalate", buttons));
  actions.append(ack, esc);

  row.append(info, actions);
  queueEl.prepend(row);
}

function resolveQueueItem(id, action, by) {
  const row = queueEl.querySelector(`.queue-item[data-id="${id}"]`);
  if (!row) return; // Already gone from this browser.

  row.classList.add("resolved", action);
  const actions = row.querySelector(".queue-actions");
  const outcome = document.createElement("div");
  outcome.className = "queue-outcome";
  // Show who did it, so the attribution from the viewer's Connect identity is visible.
  outcome.textContent =
    action === "escalate" ? `⚠ Escalated by ${by}` : `✓ Acknowledged by ${by}`;
  actions.replaceWith(outcome);

  // Let everyone read the outcome for a moment, then drop it from the queue.
  setTimeout(() => {
    row.remove();
    if (!queueEl.querySelector(".queue-item")) showQueueEmpty();
  }, RESOLVED_LINGER_MS);
}

function showQueueEmpty() {
  if (queueEl.querySelector(".empty")) return;
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = "Nothing awaiting review.";
  queueEl.append(empty);
}

// --- Escalated log: a durable record of confirmed fraud, for follow-up ---

function addEscalatedItem(tx) {
  const placeholder = escalatedEl.querySelector(".empty");
  if (placeholder) placeholder.remove();

  const row = document.createElement("div");
  row.className = "escalated-item new";

  const info = document.createElement("div");
  info.className = "queue-info";
  const title = document.createElement("div");
  title.className = "queue-title";
  title.textContent = `${money.format(tx.amount)} · ${tx.merchant}`;
  const meta = document.createElement("div");
  meta.className = "escalated-meta";
  meta.textContent = `${tx.city}, ${tx.country} · card ••${tx.cardLast4} · ${tx.flagReason}`;
  info.append(title, meta);

  const by = document.createElement("div");
  by.className = "escalated-by";
  by.textContent = `Escalated by ${tx.reviewedBy} · ${new Date(tx.reviewedAt).toLocaleTimeString()}`;

  row.append(info, by);
  escalatedEl.prepend(row);

  while (escalatedEl.children.length > MAX_ESCALATED_ROWS) {
    escalatedEl.lastElementChild.remove();
  }
}

function showEscalatedEmpty() {
  if (escalatedEl.querySelector(".empty")) return;
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = "No escalations yet.";
  escalatedEl.append(empty);
}

// --- Live feed: the raw stream of every transaction ---

function addFeedRow(tx) {
  const placeholder = feedRowsEl.querySelector(".empty");
  if (placeholder) placeholder.remove();

  const tr = document.createElement("tr");
  tr.className = tx.status === "flagged" ? "flagged new" : "new";
  const time = new Date(tx.time).toLocaleTimeString();
  tr.append(
    cell(time),
    cell(tx.merchant),
    cell(tx.category),
    cell(`${tx.city}, ${tx.country}`),
    cell(money.format(tx.amount), "num"),
    statusCell(tx),
  );
  feedRowsEl.prepend(tr);

  while (feedRowsEl.children.length > MAX_ROWS) {
    feedRowsEl.lastElementChild.remove();
  }
}

// --- Wire up the stream ---

// Relative URL so the subscription works behind Connect's content path prefix.
const source = new EventSource("events");
source.onopen = () => setStatus("open", "Live");
// EventSource reconnects on its own; reflect the dropped connection meanwhile.
source.onerror = () => setStatus("closed", "Reconnecting…");

source.addEventListener("snapshot", (event) => {
  const { stats, queue, escalated } = JSON.parse(event.data);
  renderStats(stats);
  // Rebuild the queue from the shared state (oldest first, so unshift-order matches).
  queueEl.replaceChildren();
  queue.slice().reverse().forEach(addQueueItem);
  if (queue.length === 0) showQueueEmpty();

  escalatedEl.replaceChildren();
  escalated.slice().reverse().forEach(addEscalatedItem);
  if (escalated.length === 0) showEscalatedEmpty();
});

source.addEventListener("transaction", (event) => {
  const { tx, stats } = JSON.parse(event.data);
  renderStats(stats);
  addFeedRow(tx);
  if (tx.status === "flagged") addQueueItem(tx);
});

source.addEventListener("review", (event) => {
  const { id, action, by, at, tx, stats } = JSON.parse(event.data);
  renderStats(stats);
  resolveQueueItem(id, action, by);
  if (action === "escalate") {
    addEscalatedItem({ ...tx, reviewedBy: by, reviewedAt: at });
  }
});

// Show the signed-in analyst's Connect identity in the header. A missing Visitor API
// Key integration is handled server-side, by serving the setup screen instead of this
// page, so the only real case left here is the signed-in name.
fetch("whoami")
  .then((res) => res.json())
  .then(({ name, status }) => {
    if (status === "signed-in") viewerEl.textContent = `Signed in as ${name}`;
  })
  .catch(() => {}); // Non-fatal: the header just stays blank.
