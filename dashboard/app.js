const cases = [
  {
    id: "L01", group: "local", filter: "returned", tone: "good", status: "Quote and execution agree",
    question: "Does a normal one-pool swap quote correctly?", hops: 1,
    input: "1,000,000 raw Token A units", balance: "Fixture pool funded; no balance boundary tested.",
    route: [["token","Token A"],["pool","Ordinary pool","A / B"],["token","Token B"]],
    quote: ["Quote returned","999,000 B"], execution: ["Funded execution completed","999,000 B"],
    interpretation: "The basic quote and execution paths agree."
  },
  {
    id: "L02", group: "local", filter: "returned", tone: "good", status: "Quote and execution agree",
    question: "Does adding a second ordinary pool cause the failure?", hops: 2,
    input: "1,000,000 raw Token A units", balance: "Fixture pools funded; no balance boundary tested.",
    route: [["token","Token A"],["pool","Ordinary pool 1","A / B"],["token","Token B"],["pool","Ordinary pool 2","B / C"],["token","Token C"]],
    quote: ["Quote returned","998,002 C"], execution: ["Funded execution completed","998,002 C"],
    interpretation: "Two ordinary hops work. Multi-hop alone is not the cause."
  },
  {
    id: "L03", group: "local", filter: "returned", tone: "good", status: "Both fee hooks run",
    question: "Does quote simulation skip custom hooks?", hops: 2,
    input: "1,000,000 raw Token A units", balance: "Fixture pools funded; each hook charged 100 raw output units.",
    route: [["token","Token A"],["hook","Fee-hook pool 1","A / B"],["token","Token B"],["hook","Fee-hook pool 2","B / C"],["token","Token C"]],
    quote: ["Quote returned","997,803 C"], execution: ["Funded execution completed","997,803 C"],
    interpretation: "Both hooks run in both paths. Hooks are not generally skipped."
  },
  {
    id: "L04", group: "local", filter: "gap", tone: "issue", status: "No quote; funded execution works",
    question: "What happens when the Tempo-style hook is the first pool?", hops: 2,
    input: "1,000,000 raw Token A units", balance: "PoolManager started with 0 Token A.",
    route: [["token","Token A"],["hook","Tempo-style pool","A / B"],["token","Token B"],["pool","Ordinary pool","B / C"],["token","Token C"]],
    quote: ["no quote","Reverted at PoolManager.take(A)","The first hook requested Token A before PoolManager had it."],
    execution: ["Funded execution completed","998,002 C"],
    interpretation: "Preparing Token A before the first hook changes the outcome. This isolates settlement order."
  },
  {
    id: "L05", group: "local", filter: "returned", tone: "good", status: "Quote and execution agree",
    question: "What happens when the Tempo-style hook is the last pool?", hops: 2,
    input: "1,000,000 raw Token C units", balance: "PoolManager held 29,553,011 raw Token A units from the first pool.",
    route: [["token","Token C"],["pool","Ordinary pool","C / A"],["token","Token A"],["hook","Tempo-style pool","A / B"],["token","Token B"]],
    quote: ["Quote returned","998,001 B"], execution: ["Funded execution completed","998,001 B"],
    interpretation: "The earlier pool made Token A available before the hook requested it. Hook position matters."
  },
  {
    id: "F01", group: "fork", filter: "verify", tone: "verify", status: "Raw-log verification required",
    question: "What does the real one-pool Tempo control prove?", hops: 1,
    input: "Disputed: 1.000000 cUSD in one source; 5.249475 cUSD in another.",
    balance: "PoolManager held 19.862459 cUSD at Tempo block 41,183,156.",
    route: [["token","cUSD"],["hook","Tempo pool","cUSD / PathUSD"],["token","PathUSD"]],
    quote: ["Source disagreement","0.999800 PathUSD or 5.248425 PathUSD"],
    execution: ["Source disagreement","0.999800 gross / 0.999479 net, or 5.248425 PathUSD"],
    interpretation: "The PDF and source summary disagree. Keep their values separate and verify the raw transaction and balance logs before citing case 06.",
    warning: true
  },
  {
    id: "F02", group: "fork", filter: "returned", tone: "good", status: "Quote and execution agree",
    question: "Does the real two-pool Tempo route always fail?", hops: 2,
    input: "1.000000 cUSD", balance: "PoolManager held 19.862459 cUSD at block 41,183,156.",
    route: [["token","cUSD"],["hook","Tempo pool 1","cUSD / PathUSD"],["token","PathUSD"],["hook","Tempo pool 2","PathUSD / USDT0"],["token","USDT0"]],
    quote: ["Quote returned","0.999899 USDT0"], execution: ["Funded execution completed","0.999899 USDT0"],
    interpretation: "The small route succeeds in both paths. The failure is conditional, not universal."
  },
  {
    id: "F03", group: "fork", filter: "returned", tone: "good", status: "Quote and execution agree",
    question: "Does changing the final Tempo pool change the small-input result?", hops: 2,
    input: "1.000000 cUSD", balance: "PoolManager held 19.862459 cUSD at block 41,183,156.",
    route: [["token","cUSD"],["hook","Tempo pool 1","cUSD / PathUSD"],["token","PathUSD"],["hook","Tempo pool 2","PathUSD / USDC.e"],["token","USDC.e"]],
    quote: ["Quote returned","0.999800 USDC.e"], execution: ["Funded execution completed","0.999800 USDC.e"],
    interpretation: "A second real target also works at a small input. Tempo multi-hop is not always rejected."
  },
  {
    id: "F04", group: "fork", filter: "gap", tone: "issue", status: "No quote; funded execution works", emphasis: true,
    question: "Does the quote fail exactly above PoolManager's cUSD balance?", hops: 2,
    input: "19.862460 cUSD", balance: "PoolManager held 19.862459 cUSD - one raw unit less than the input.",
    route: [["token","cUSD"],["hook","Tempo pool 1","cUSD / PathUSD"],["token","PathUSD"],["hook","Tempo pool 2","PathUSD / USDT0"],["token","USDT0"]],
    quote: ["no quote","Reverted at PoolManager.take(cUSD)","The hook requested 19.862460 cUSD while PoolManager held 19.862459 cUSD."],
    execution: ["Funded execution completed","19.860473 USDT0"],
    interpretation: "The one-unit boundary follows PoolManager's temporary balance. Funding first lets the route complete."
  },
  {
    id: "F05", group: "fork", filter: "gap", tone: "issue", status: "No quote; funded execution works", emphasis: true,
    question: "Can the same route execute at 25 cUSD even though standard quoting fails?", hops: 2,
    input: "25.000000 cUSD", balance: "PoolManager held 19.862459 cUSD; only the test payer was raised to 30 cUSD.",
    route: [["token","cUSD"],["hook","Tempo pool 1","cUSD / PathUSD"],["token","PathUSD"],["hook","Tempo pool 2","PathUSD / USDT0"],["token","USDT0"]],
    quote: ["no quote","Reverted at PoolManager.take(cUSD)","Input was requested before it was transferred in. Direct hook calls produced a 24.997499 USDT0 candidate, not a standard quote result."],
    execution: ["Funded execution completed","Reported recipient increase: 24.997499 USDT0"],
    interpretation: "This is a missing standard quote for a route that reportedly executes when funded first. It does not prove a better price."
  },
  {
    id: "F06", group: "fork", filter: "reject", tone: "reject", status: "Both paths fail",
    question: "Can the test distinguish the balance-order problem from genuine illiquidity?", hops: 2,
    input: "1,000,000 cUSD", balance: "Test payer funded; PoolManager and Tempo Exchange not artificially funded.",
    route: [["token","cUSD"],["hook","Tempo pool 1","cUSD / PathUSD"],["token","PathUSD"],["hook","Tempo pool 2","PathUSD / USDT0"],["token","USDT0"]],
    quote: ["no quote","InsufficientLiquidity() at Tempo Exchange","The first direct Tempo quote rejected the amount because the exchange lacked liquidity."],
    execution: ["Funded execution failed","InsufficientLiquidity() at Tempo Exchange"],
    interpretation: "Funding order cannot rescue this input. Both paths fail for the same real liquidity reason."
  }
];

function routeMarkup(route) {
  return route.map((step, index) => {
    const [type, label, sub] = step;
    const node = type === "token"
      ? `<div class="route-node token-node">${label}</div>`
      : `<div class="route-node pool-node ${type === "hook" ? "hook-node" : ""}"><strong>${label}</strong><small>${sub}</small></div>`;
    return index === route.length - 1 ? node : `${node}<span class="route-arrow" aria-hidden="true">&rarr;</span>`;
  }).join("");
}

function resultPanel(title, result, tone) {
  return `<article class="result-panel ${tone}">
    <h4>${title}</h4><strong>${result[0]}</strong><p>${result[1]}</p>
    ${result[2] ? `<div class="failure-step"><span>Failing step</span>${result[2]}</div>` : ""}
  </article>`;
}

function caseMarkup(item, number) {
  const quoteTone = item.filter === "returned" ? "good" : item.filter === "verify" ? "warning" : "bad";
  const executionTone = item.filter === "reject" ? "bad" : item.filter === "verify" ? "warning" : "good";
  return `<details class="case-card ${item.emphasis ? "emphasis" : ""}" data-filter="${item.filter}">
    <summary>
      <span class="case-number">${String(number).padStart(2, "0")}</span>
      <span class="case-question"><small>Question</small><strong>${item.question}</strong></span>
      <span class="hop-count">${item.hops} ${item.hops === 1 ? "hop" : "hops"}</span>
      <span class="case-status ${item.tone}">${item.status}</span>
      <span class="open-icon" aria-hidden="true">+</span>
    </summary>
    <div class="case-details">
      ${item.warning ? '<div class="verification-warning"><strong>Verify before citing:</strong> the PDF and source summary disagree. Keep the values separate.</div>' : ""}
      <section class="case-field"><h3>Complete path</h3><div class="full-route">${routeMarkup(item.route)}</div></section>
      <section class="case-field facts-grid">
        <div><span>Number of hops</span><strong>${item.hops}</strong></div>
        <div><span>Input</span><strong>${item.input}</strong></div>
        <div><span>Relevant starting balance</span><strong>${item.balance}</strong></div>
      </section>
      <section class="case-field"><h3>Quote and funded execution</h3><div class="result-comparison">
        ${resultPanel("Quote result", item.quote, quoteTone)}
        ${resultPanel("Funded execution result", item.execution, executionTone)}
      </div></section>
      <section class="interpretation"><strong>Interpretation</strong><p>${item.interpretation}</p></section>
    </div>
  </details>`;
}

document.querySelector("#local-cases").innerHTML = cases.filter((item) => item.group === "local").map((item, index) => caseMarkup(item, index + 1)).join("");
document.querySelector("#fork-cases").innerHTML = cases.filter((item) => item.group === "fork").map((item, index) => caseMarkup(item, index + 6)).join("");

const caseCards = [...document.querySelectorAll(".case-card")];
const filterButtons = [...document.querySelectorAll(".filter")];

filterButtons.forEach((button) => button.addEventListener("click", () => {
  filterButtons.forEach((item) => item.classList.toggle("active", item === button));
  caseCards.forEach((card) => {
    card.hidden = button.dataset.filter !== "all" && card.dataset.filter !== button.dataset.filter;
    if (card.hidden) card.open = false;
  });
  document.querySelectorAll(".case-group-label").forEach((label) => {
    label.hidden = [...label.nextElementSibling.children].every((card) => card.hidden);
  });
}));

caseCards.forEach((card) => card.addEventListener("toggle", () => {
  if (card.open) caseCards.forEach((other) => { if (other !== card) other.open = false; });
}));

const tabs = [...document.querySelectorAll(".top-tab")];
const panels = [...document.querySelectorAll(".tab-panel")];
tabs.forEach((tab) => tab.addEventListener("click", () => {
  tabs.forEach((item) => {
    const active = item === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
  });
  panels.forEach((panel) => { panel.hidden = panel.id !== `${tab.dataset.tab}-panel`; });
  window.scrollTo({ top: 0, behavior: "smooth" });
}));
