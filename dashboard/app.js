const cases = [
  {
    id: "L01", group: "local", filter: "matched", hop: "single-hop",
    source: "Token A", target: "Token B", amount: "1,000,000 raw units",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "Token A" },
      { type: "pool", label: "Ordinary pool", sub: "No custom logic" },
      { type: "token", label: "Token B" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "999,000 B", executionStatus: "Completed", executionAmount: "999,000 B", matched: true },
  },
  {
    id: "L02", group: "local", filter: "matched", hop: "multi-hop",
    source: "Token A", target: "Token C", amount: "1,000,000 raw units",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "Token A" }, { type: "pool", label: "Pool 1", sub: "Ordinary" },
      { type: "token", label: "Token B" }, { type: "pool", label: "Pool 2", sub: "Ordinary" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "998,002 C", executionStatus: "Completed", executionAmount: "998,002 C", matched: true },
  },
  {
    id: "L03", group: "local", filter: "matched", hop: "multi-hop",
    source: "Token A", target: "Token C", amount: "Two fee-enabled pools",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "Token A" }, { type: "pool hook", label: "Pool 1", sub: "Custom fee" },
      { type: "token", label: "Token B" }, { type: "pool hook", label: "Pool 2", sub: "Custom fee" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "997,803 C", executionStatus: "Completed", executionAmount: "997,803 C", matched: true },
  },
  {
    id: "L04", group: "local", filter: "mismatch", hop: "multi-hop",
    source: "Token A", target: "Token C", amount: "Tempo-style pool first",
    result: "Issue found", resultTone: "issue", routeWorks: "With preparation", standard: "Fails",
    route: [
      { type: "token", label: "Token A" }, { type: "pool hook", label: "Pool 1", sub: "Tempo-style" },
      { type: "token", label: "Token B" }, { type: "pool", label: "Pool 2", sub: "Ordinary" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Failed", quoteAmount: "No amount", executionStatus: "Completed after prepay", executionAmount: "Output produced", matched: false },
    error: {
      title: "The quote reaches Pool 1 before Token A is available there.",
      body: "The custom pool must move real Token A during its conversion. The quote preview starts the conversion without first supplying that token, so it stops. The diagnostic execution supplies the input first and completes the same route.",
      quoteFlow: ["Start preview", "Enter Pool 1", "Input missing", "Stop"],
      executionFlow: ["Supply input", "Enter Pool 1", "Pool 2", "Complete"],
    },
  },
  {
    id: "L05", group: "local", filter: "matched", hop: "multi-hop",
    source: "Token A", target: "Token C", amount: "Tempo-style pool last",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "Token A" }, { type: "pool", label: "Pool 1", sub: "Ordinary" },
      { type: "token", label: "Token B" }, { type: "pool hook", label: "Pool 2", sub: "Tempo-style" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "Output calculated", executionStatus: "Completed", executionAmount: "Same output", matched: true },
  },
  {
    id: "F01", group: "fork", filter: "mismatch", hop: "single-hop",
    source: "cUSD", target: "PathUSD", amount: "1.000000 cUSD",
    result: "Needs review", resultTone: "issue", routeWorks: "Yes", standard: "Fails net check",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Tempo pool", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "0.999800 PathUSD", executionStatus: "Completed", executionAmount: "0.999479 net PathUSD", matched: false, note: "The gross transfer was 0.999800; the recipient's net balance increased by 0.999479." },
    error: {
      title: "Gross output matches, but the recipient's net balance is 0.000321 lower.",
      body: "This is separate from the missing-quote problem. The recorded test confirms the gross transfer but does not yet isolate the 321-unit net difference into a specific fee or balance effect, so this case remains marked for review.",
      quoteFlow: ["Quote", "0.999800 gross"],
      executionFlow: ["Gross transfer 0.999800", "Net balance 0.999479"],
    },
  },
  {
    id: "F02", group: "fork", filter: "matched", hop: "multi-hop",
    source: "cUSD", target: "USDT0", amount: "1.000000 cUSD",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Pool 1", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" }, { type: "pool hook", label: "Pool 2", sub: "PathUSD / USDT0" },
      { type: "token", label: "USDT0" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "0.999899 USDT0", executionStatus: "Completed", executionAmount: "0.999899 USDT0", matched: true },
  },
  {
    id: "F03", group: "fork", filter: "matched", hop: "multi-hop",
    source: "cUSD", target: "USDC.e", amount: "1.000000 cUSD",
    result: "Good", resultTone: "good", routeWorks: "Yes", standard: "Meets",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Pool 1", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" }, { type: "pool hook", label: "Pool 2", sub: "PathUSD / USDC.e" },
      { type: "token", label: "USDC.e" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "0.999800 USDC.e", executionStatus: "Completed", executionAmount: "0.999800 USDC.e", matched: true },
  },
  {
    id: "F04", group: "fork", filter: "mismatch", hop: "multi-hop",
    source: "cUSD", target: "USDT0", amount: "19.862460 cUSD",
    result: "Issue found", resultTone: "issue", routeWorks: "With preparation", standard: "Fails",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Pool 1", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" }, { type: "pool hook", label: "Pool 2", sub: "PathUSD / USDT0" },
      { type: "token", label: "USDT0" },
    ],
    comparison: { quoteStatus: "Failed", quoteAmount: "No amount", executionStatus: "Completed with prepay", executionAmount: "19.860473 USDT0", matched: false },
    error: {
      title: "The failure starts exactly one raw unit above the available cUSD balance.",
      body: "At this block, the shared PoolManager held 19.862459 cUSD. The standard preview succeeds at that amount and fails at 19.862460. The sharp boundary follows the temporary contract balance, not the amount Tempo can exchange.",
      quoteFlow: ["19.862460 input", "Only 19.862459 available", "Transfer fails", "No quote"],
      executionFlow: ["Prepare 19.862460", "Run Pool 1", "Run Pool 2", "Receive 19.860473"],
    },
  },
  {
    id: "F05", group: "fork", filter: "matched", hop: "multi-hop",
    source: "cUSD", target: "USDT0", amount: "25.000000 cUSD",
    result: "Issue reproduced", resultTone: "issue", routeWorks: "With preparation", standard: "Fails",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Pool 1", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" }, { type: "pool hook", label: "Pool 2", sub: "PathUSD / USDT0" },
      { type: "token", label: "USDT0" },
    ],
    comparison: { quoteStatus: "Candidate quote completed", quoteAmount: "24.997499 USDT0", executionStatus: "Completed with matching plan", executionAmount: "24.997499 USDT0", matched: true, note: "The standard V4Quoter failed, so this row compares the recovered candidate quote with its matching execution plan." },
  },
  {
    id: "F06", group: "fork", filter: "rejected", hop: "multi-hop",
    source: "cUSD", target: "USDT0", amount: "1,000,000 cUSD",
    result: "Correct rejection", resultTone: "reject", routeWorks: "No", standard: "Meets",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Pool 1", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" }, { type: "pool hook", label: "Pool 2", sub: "PathUSD / USDT0" },
      { type: "token", label: "USDT0" },
    ],
    comparison: { quoteStatus: "Rejected", quoteAmount: "Not enough liquidity", executionStatus: "Rejected", executionAmount: "Not executed", matched: true, note: "Both processes agree that the real exchange cannot support this amount." },
  },
];

function routeMarkup(route) {
  return route.map((step, index) => {
    const element = step.type.includes("pool")
      ? `<div class="route-step route-pool ${step.type.includes("hook") ? "is-hook" : ""}"><span>${step.label}</span><small>${step.sub}</small></div>`
      : `<div class="route-step route-token">${step.label}</div>`;
    return index === route.length - 1 ? element : `${element}<div class="route-arrow" aria-hidden="true">→</div>`;
  }).join("");
}

function comparisonMarkup(item) {
  const c = item.comparison;
  return `
    <div class="comparison-table" role="table" aria-label="Quote and execution comparison">
      <div class="comparison-header" role="row">
        <span role="columnheader">Measurement</span><span role="columnheader">Status</span><span role="columnheader">Output</span>
      </div>
      <div class="comparison-row" role="row">
        <strong role="cell">Quote preview</strong><span role="cell" class="status-cell">${c.quoteStatus}</span><span role="cell">${c.quoteAmount}</span>
      </div>
      <div class="comparison-row" role="row">
        <strong role="cell">Completed execution</strong><span role="cell" class="status-cell">${c.executionStatus}</span><span role="cell">${c.executionAmount}</span>
      </div>
      <div class="match-row ${c.matched ? "matched" : "not-matched"}">
        <span>${c.matched ? "✓" : "!"}</span>
        <strong>${c.matched ? "Quote and execution match" : "Quote and execution do not match"}</strong>
      </div>
      ${c.note ? `<p class="comparison-note">${c.note}</p>` : ""}
    </div>`;
}

function flowMarkup(items, tone) {
  return items.map((item, index) => `
    <span class="flow-item ${index === items.length - 1 ? tone : ""}">${item}</span>
    ${index === items.length - 1 ? "" : '<i aria-hidden="true">→</i>'}
  `).join("");
}

function errorMarkup(error) {
  if (!error) return "";
  return `
    <section class="error-analysis">
      <div class="error-heading"><span>3</span><div><small>ERROR ANALYSIS</small><h4>${error.title}</h4></div></div>
      <p>${error.body}</p>
      <div class="flow-compare">
        <div><strong>Quote path</strong><div class="mini-flow">${flowMarkup(error.quoteFlow, "flow-error")}</div></div>
        <div><strong>Execution path</strong><div class="mini-flow">${flowMarkup(error.executionFlow, "flow-success")}</div></div>
      </div>
    </section>`;
}

function caseMarkup(item, number) {
  return `
    <details class="case-card" data-filter="${item.filter}" data-id="${item.id}">
      <summary>
        <span class="case-number">${String(number).padStart(2, "0")}</span>
        <span class="swap-goal"><small>SWAP GOAL</small><strong>${item.source} <i>→</i> ${item.target}</strong><em>${item.amount}</em></span>
        <span class="hop-label">${item.hop}</span>
        <span class="summary-verdict result-verdict"><small>RESULT</small><strong class="${item.resultTone}">${item.result}</strong></span>
        <span class="summary-verdict route-verdict"><small>ROUTE WORKS?</small><strong>${item.routeWorks}</strong></span>
        <span class="summary-verdict standard-verdict"><small>QUOTE STANDARD</small><strong>${item.standard}</strong></span>
        <span class="open-icon" aria-hidden="true">+</span>
      </summary>
      <div class="case-details">
        <section class="detail-section">
          <div class="detail-heading"><span>1</span><div><small>ROUTE</small><h4>Where the input travels</h4></div></div>
          <div class="full-route">${routeMarkup(item.route)}</div>
        </section>
        <section class="detail-section">
          <div class="detail-heading"><span>2</span><div><small>COMPARISON</small><h4>Preview versus completed swap</h4></div></div>
          ${comparisonMarkup(item)}
        </section>
        ${errorMarkup(item.error)}
      </div>
    </details>`;
}

const localRoot = document.querySelector("#local-cases");
const forkRoot = document.querySelector("#fork-cases");
localRoot.innerHTML = cases.filter((item) => item.group === "local").map((item, index) => caseMarkup(item, index + 1)).join("");
forkRoot.innerHTML = cases.filter((item) => item.group === "fork").map((item, index) => caseMarkup(item, index + 6)).join("");

const caseCards = [...document.querySelectorAll(".case-card")];
const filterButtons = [...document.querySelectorAll(".filter")];

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    filterButtons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    const filter = button.dataset.filter;
    caseCards.forEach((card) => {
      const visible = filter === "all" || card.dataset.filter === filter;
      card.hidden = !visible;
      if (!visible) card.open = false;
    });
    document.querySelectorAll(".case-group-label").forEach((label) => {
      const list = label.nextElementSibling;
      label.hidden = [...list.children].every((card) => card.hidden);
    });
  });
});

caseCards.forEach((card) => {
  card.addEventListener("toggle", () => {
    if (!card.open) return;
    caseCards.forEach((other) => {
      if (other !== card) other.open = false;
    });
  });
});

const tabs = [...document.querySelectorAll(".top-tab")];
const panels = [...document.querySelectorAll(".tab-panel")];

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((item) => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-selected", String(active));
    });
    panels.forEach((panel) => {
      const active = panel.id === `${tab.dataset.tab}-panel`;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
});
