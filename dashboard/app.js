const cases = [
  {
    id: "L01", group: "local", filter: "matched", hop: "single-hop",
    source: "Token A", target: "Token B", amount: "1,000,000 raw units",
    description: "Single ordinary-pool baseline with a fixed input and no custom hook.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
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
    description: "Two ordinary pools isolate multi-hop behavior without custom hook logic.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
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
    description: "Two independent output-fee hooks verify that both hops run and both fees reach their hooks.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
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
    description: "The Tempo-style hook runs first while PoolManager holds no Token A; prepayment isolates settlement order.",
    result: "Quote gap", resultTone: "issue", routeWorks: "With prepay", standard: "V4Quoter fails",
    route: [
      { type: "token", label: "Token A" }, { type: "pool hook", label: "Pool 1", sub: "Tempo-style" },
      { type: "token", label: "Token B" }, { type: "pool", label: "Pool 2", sub: "Ordinary" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Failed", quoteAmount: "No amount", executionStatus: "Completed after prepay", executionAmount: "998,002 C", matched: false },
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
    description: "An ordinary first pool supplies the intermediate token before the Tempo-style final hop.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
    route: [
      { type: "token", label: "Token A" }, { type: "pool", label: "Pool 1", sub: "Ordinary" },
      { type: "token", label: "Token B" }, { type: "pool hook", label: "Pool 2", sub: "Tempo-style" },
      { type: "token", label: "Token C" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "998,001 C", executionStatus: "Completed", executionAmount: "998,001 C", matched: true },
  },
  {
    id: "F01", group: "fork", filter: "matched", hop: "single-hop",
    source: "cUSD", target: "PathUSD", amount: "1.000000 cUSD",
    description: "The hook quote matches the gross transfer; the payer-recipient also pays gas in PathUSD.",
    result: "Gross matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
    route: [
      { type: "token", label: "cUSD" }, { type: "pool hook", label: "Tempo pool", sub: "cUSD / PathUSD" },
      { type: "token", label: "PathUSD" },
    ],
    comparison: { quoteStatus: "Completed", quoteAmount: "0.999800 PathUSD gross", executionStatus: "Completed", executionAmount: "0.999800 PathUSD gross", matched: true, note: "The payer-recipient's wallet rises by 0.999479 PathUSD because the receipt charges it 0.000321 PathUSD for gas. A separate recipient receives the full 0.999800. The conservative validator excludes this candidate until ranking accounts for gas exactly once." },
  },
  {
    id: "F02", group: "fork", filter: "matched", hop: "multi-hop",
    source: "cUSD", target: "USDT0", amount: "1.000000 cUSD",
    description: "Small-input two-pool control on the pinned fork checks the standard quote against full execution.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
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
    description: "The same small input uses a different final Tempo pool to control for the target token.",
    result: "Matched", resultTone: "good", routeWorks: "Yes", standard: "Quote succeeds",
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
    description: "Input is set one raw unit above PoolManager's cUSD balance to locate the exact quote-failure boundary.",
    result: "Quote gap", resultTone: "issue", routeWorks: "With prepay", standard: "V4Quoter fails",
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
    description: "Only the payer is funded; the recovered candidate is checked against a settle-before-swap transaction.",
    result: "Recovered", resultTone: "issue", routeWorks: "With prepay", standard: "V4Quoter fails",
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
    description: "Extreme input is a negative control: both direct quoting and prepay execution face real exchange illiquidity.",
    result: "Valid rejection", resultTone: "reject", routeWorks: "No", standard: "Liquidity revert",
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
        <span class="swap-goal"><small>EXPERIMENT</small><strong>${item.source} <i>→</i> ${item.target}</strong><em>${item.amount}</em><span>${item.description}</span></span>
        <span class="hop-label">${item.hop}</span>
        <span class="summary-verdict result-verdict"><small>RESULT</small><strong class="${item.resultTone}">${item.result}</strong></span>
        <span class="summary-verdict route-verdict"><small>ROUTE VIABILITY</small><strong>${item.routeWorks}</strong></span>
        <span class="summary-verdict standard-verdict"><small>QUOTE BEHAVIOR</small><strong>${item.standard}</strong></span>
        <span class="open-icon" aria-hidden="true">+</span>
      </summary>
      <div class="case-details">
        <section class="detail-section">
          <div class="detail-heading"><span>1</span><div><small>ROUTE</small><h4>Pool sequence</h4></div></div>
          <div class="full-route">${routeMarkup(item.route)}</div>
        </section>
        <section class="detail-section">
          <div class="detail-heading"><span>2</span><div><small>COMPARISON</small><h4>Quote and execution</h4></div></div>
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
