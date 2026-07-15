const rowsEl = document.getElementById("rows");
const statusEl = document.getElementById("status");
const statusTextEl = document.getElementById("status-text");

const MAX_ROWS = 50; // Keep the table short; older rows drop off the bottom.

// Running totals, accumulated on the client from the stream.
let count = 0;
let flagged = 0;
let volume = 0;

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

function updateTotals() {
  document.getElementById("stat-volume").textContent = compactMoney.format(volume);
  document.getElementById("stat-count").textContent = count.toLocaleString();

  const flaggedEl = document.getElementById("stat-flagged");
  flaggedEl.textContent = flagged.toLocaleString();
  flaggedEl.classList.toggle("alert", flagged > 0);

  const rate = count ? (flagged / count) * 100 : 0;
  document.getElementById("stat-rate").textContent = `${rate.toFixed(1)}%`;
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
  if (tx.flagReason) {
    const reason = document.createElement("span");
    reason.className = "flag-reason";
    reason.textContent = ` — ${tx.flagReason}`;
    td.appendChild(reason);
  }
  return td;
}

function addTransaction(tx) {
  count += 1;
  volume += tx.amount;
  if (tx.status === "flagged") flagged += 1;
  updateTotals();

  const placeholder = rowsEl.querySelector(".empty");
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
  rowsEl.prepend(tr);

  while (rowsEl.children.length > MAX_ROWS) {
    rowsEl.lastElementChild.remove();
  }
}

// Relative URL so the subscription works behind Connect's content path prefix.
const source = new EventSource("events");
source.onopen = () => setStatus("open", "Live");
source.onmessage = (event) => addTransaction(JSON.parse(event.data));
// EventSource reconnects on its own; reflect the dropped connection meanwhile.
source.onerror = () => setStatus("closed", "Reconnecting…");
