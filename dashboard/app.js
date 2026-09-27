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
    id: "F01", group: "fork", filter: "returned", tone: "good", status: "Gross quote and execution agree",
    question: "Why is the wallet increase smaller than the quoted PathUSD output?", hops: 1,
    input: "1.000000 cUSD", balance: "The payer-recipient started with 0.039805 PathUSD at block 41,183,156.",
    route: [["token","cUSD"],["hook","Tempo pool","cUSD / PathUSD"],["token","PathUSD"]],
    quote: ["Quote returned","0.999800 PathUSD gross"],
    execution: ["Funded execution completed","0.999800 gross transfer; 0.999479 wallet increase"],
    interpretation: "The receipt proves a separate 0.000321 PathUSD gas charge to the Tempo fee collector. Gross swap output matches the quote; the smaller wallet increase already includes gas. A separate-recipient control receives the full 0.999800.",
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
    execution: ["Validated full Router execution","Recipient receives 24.997499 USDT0; receipt gas is 316,216"],
    interpretation: "The recovered candidate matches the complete settle-before-swap execution and is admitted to comparison. This proves quote recovery for the supported route, not a better price than another route."
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
  const quoteTone = item.filter === "returned" ? "good" : "bad";
  const executionTone = item.filter === "reject" ? "bad" : "good";
  return `<details class="case-card ${item.emphasis ? "emphasis" : ""}" data-filter="${item.filter}">
    <summary>
      <span class="case-number">${String(number).padStart(2, "0")}</span>
      <span class="case-question"><small>Question</small><strong>${item.question}</strong></span>
      <span class="hop-count">${item.hops} ${item.hops === 1 ? "hop" : "hops"}</span>
      <span class="case-status ${item.tone}">${item.status}</span>
      <span class="open-icon" aria-hidden="true">+</span>
    </summary>
    <div class="case-details">
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

const recordedEvidence = window.quoteBridgeEvidence;
const runnerCases = [...document.querySelectorAll(".runner-case")];
const caseAmounts = { gap: "25 cUSD", small: "1 cUSD", illiquid: "1,000,000 cUSD" };
let selectedCase = "gap";

function formatTokenAmount(rawAmount, token = "USDT0") {
  return `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 6, maximumFractionDigits: 6 }).format(rawAmount / 1_000_000)} ${token}`;
}

function setStage(name, state, label) {
  const stage = document.querySelector(`#${name}-stage`);
  stage.dataset.state = state;
  const badge = document.querySelector(`#${name}-state`);
  badge.className = `step-state ${state}`;
  badge.textContent = label;
}

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function resetRecordView() {
  for (const id of ["baseline-value", "bridge-value", "execution-value", "execution-received", "execution-gas", "compare-quote", "compare-actual", "compare-delta"]) setText(id, "—");
  document.querySelector("#bridge-hops").hidden = true;
  document.querySelector("#bridge-hops").replaceChildren();
  document.querySelector("#plan-order").hidden = true;
  setText("plan-label", "Funded plan");
  setText("plan-description", "Prepare input → swap → deliver output");
  document.querySelector("#why-matters").hidden = true;
}

runnerCases.forEach((button) => button.addEventListener("click", () => {
  selectedCase = button.dataset.caseId;
  runnerCases.forEach((item) => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  });
  setText("selected-input", caseAmounts[selectedCase]);
  if (recordedEvidence?.cases?.[selectedCase]) renderRecord(recordedEvidence.cases[selectedCase]);
}));

function renderRecord(record) {
  if (record.caseId !== selectedCase || record.amountInRaw !== ({ gap: 25_000_000, small: 1_000_000, illiquid: 1_000_000_000_000 })[selectedCase]) {
    throw new Error("The recorded result does not match the selected case");
  }
  if (record.chainId !== recordedEvidence.provenance.chainId || record.blockHash !== recordedEvidence.provenance.blockHash || !record.snapshotReverted) {
    throw new Error("The recorded result is not bound to the verified fork state");
  }
  resetRecordView();
  const { baseline, quoteBridge, plan, execution, comparison } = record;
  if (baseline.status === "success") {
    setStage("baseline", "good", "Quote returned");
    setText("baseline-value", formatTokenAmount(baseline.amountOutRaw));
    setText("baseline-detail", "V4Quoter returned an amount for this input. The standard path works at this size.");
  } else {
    setStage("baseline", "bad", "No quote");
    setText("baseline-value", "No quote");
    setText("baseline-detail", record.caseId === "gap"
      ? `V4Quoter stopped before returning an amount. The trace-identified step is ${baseline.errorStage}; PoolManager held ${formatTokenAmount(record.poolManagerInputBalanceRaw, "cUSD")} while the hook requested ${formatTokenAmount(record.amountInRaw, "cUSD")}.`
      : `${baseline.errorStage}: ${baseline.error}. V4Quoter did not return an amount.`);
  }

  if (quoteBridge.status === "candidate") {
    setStage("bridge", "good", "Candidate recovered");
    setText("bridge-value", formatTokenAmount(quoteBridge.amountOutRaw));
    setText("bridge-detail", `${quoteBridge.hops.length} Tempo hooks quoted in order at block ${record.blockNumber.toLocaleString()}.`);
    const hops = document.querySelector("#bridge-hops");
    quoteBridge.hops.forEach((hop, index) => {
      const item = document.createElement("span");
      item.textContent = `Pool ${index + 1}: ${hop.source} → ${hop.target} · ${formatTokenAmount(hop.amountOutRaw, hop.target)}`;
      hops.append(item);
    });
    hops.hidden = false;
    document.querySelector("#plan-order").hidden = plan.status !== "built";
  } else {
    setStage("bridge", "bad", "No candidate");
    setText("bridge-value", "No recovered quote");
    setText("bridge-detail", `${quoteBridge.errorStage}: ${quoteBridge.error}. No usable quote is available for comparison.`);
    if (plan.status === "diagnostic") {
      setText("plan-label", "Diagnostic only");
      setText("plan-description", "A zero-minimum-output plan probes the real liquidity failure on this local fork.");
      document.querySelector("#plan-order").hidden = false;
    }
  }

  if (execution.status === "success") {
    setStage("execution", "good", "Receipt success");
    setText("execution-value", "Success · status 1");
    setText("execution-received", formatTokenAmount(execution.recipientDeltaRaw));
    setText("execution-gas", `${execution.gasUsed.toLocaleString()} units`);
    setText("execution-detail", `${execution.hookCalls} hook calls; the recipient balance change and transaction receipt were measured on Anvil.`);
  } else {
    const reverted = execution.status === "revert";
    setStage("execution", reverted ? "bad" : "neutral", reverted ? "Reverted" : execution.status === "indeterminate" ? "Indeterminate" : "Not attempted");
    setText("execution-value", reverted ? (execution.receiptStatus === 0 ? "Reverted · status 0" : "Reverted before receipt") : execution.status === "indeterminate" ? "Indeterminate" : "Not attempted");
    if (execution.recipientDeltaRaw != null) setText("execution-received", formatTokenAmount(execution.recipientDeltaRaw));
    if (execution.gasUsed != null) setText("execution-gas", `${execution.gasUsed.toLocaleString()} units`);
    setText("execution-detail", execution.status === "not-attempted" ? "The hook could not quote this input, so no transaction was sent." : `${execution.errorStage || "Router transaction"}: ${execution.error || "execution did not complete"}. The funded diagnostic transaction produced receipt status ${execution.receiptStatus ?? "unknown"}.`);
  }

  if (quoteBridge.amountOutRaw != null) setText("compare-quote", formatTokenAmount(quoteBridge.amountOutRaw));
  if (execution.recipientDeltaRaw != null) setText("compare-actual", formatTokenAmount(execution.recipientDeltaRaw));
  if (comparison.deltaRaw != null) setText("compare-delta", formatTokenAmount(comparison.deltaRaw));
  if (comparison.status === "matched") {
    setStage("compare", "good", "Matches within tolerance");
    setText("compare-verdict", `Matches within tolerance: ${comparison.reason}. Tolerance is ${comparison.toleranceRaw} raw USDT0 units.`);
  } else {
    setStage("compare", comparison.status === "mismatch" ? "bad" : "neutral", comparison.status === "mismatch" ? "Does not match" : "Not comparable");
    setText("compare-verdict", comparison.reason);
  }

  const beforeAmount = baseline.amountOutRaw == null ? "No quote" : formatTokenAmount(baseline.amountOutRaw);
  const afterAmount = quoteBridge.amountOutRaw == null ? "No usable quote" : formatTokenAmount(quoteBridge.amountOutRaw);
  setText("before-summary", beforeAmount);
  setText("before-summary-note", baseline.status === "success"
    ? "V4Quoter returned the same amount as the verified route."
    : record.caseId === "gap" ? "Simulation stopped at the first hook's input transfer." : "V4Quoter did not produce a quote for this large input.");
  setText("after-summary", afterAmount);
  setText("after-summary-note", execution.status === "success"
    ? `Funded Router receipt: status 1. Recipient gained ${formatTokenAmount(execution.recipientDeltaRaw)}.`
    : `Tempo quote: ${quoteBridge.error}. Funded Router receipt: status ${execution.receiptStatus}; recipient gained ${formatTokenAmount(execution.recipientDeltaRaw)}.`);
  document.querySelector("#before-card").dataset.state = baseline.status === "success" ? "good" : "bad";
  document.querySelector("#after-card").dataset.state = comparison.status === "matched" ? "good" : "bad";
  document.querySelector("#why-matters").hidden = !record.whyThisMatters;
  setText("record-summary", `Case ${record.caseId} · ${formatTokenAmount(record.amountInRaw, "cUSD")} · PoolManager held ${formatTokenAmount(record.poolManagerInputBalanceRaw, "cUSD")} · baseline ${baseline.status} · QuoteBridge ${quoteBridge.status} · transaction ${execution.status} · receipt gas ${execution.gasUsed ?? "n/a"} · ${record.rpcCalls} RPC calls · ${record.elapsedMs.toLocaleString()} ms`);
  setText("record-identifiers", `Block ${record.blockNumber.toLocaleString()} · ${record.blockHash} · plan ${plan.planDigest || "not built"} · local fork tx ${execution.localForkTxHash || "not sent"}`);
}

if (recordedEvidence?.cases?.gap) renderRecord(recordedEvidence.cases.gap);

const pipelineStages = {
  classify: {
    step: "STEP 1",
    title: "Accept only a verified route shape.",
    body: "The dispatcher checks the Tempo hook deployment, pool IDs, token direction, fee, tick spacing, chain, and pinned block before using the specialized path.",
    proof: "Unknown hooks and unsupported route shapes never fall through to this quote path."
  },
  quote: {
    step: "STEP 2",
    title: "Compose one candidate at one block.",
    body: "Each Tempo hook is quoted in route order. The first output becomes the second input, and every RPC read uses the same pinned block context.",
    proof: "A positive number is recorded as a candidate only. It is not eligible yet."
  },
  plan: {
    step: "STEP 3",
    title: "Build the transaction the user can actually execute.",
    body: "The plan uses SETTLE, then SWAP_EXACT_IN, then TAKE, with explicit payer, recipient, deadline, minimum output, and complete Router calldata.",
    proof: "The plan digest binds validation to these exact execution instructions."
  },
  execute: {
    step: "STEP 4",
    title: "Run the complete Universal Router transaction.",
    body: "A fresh fork snapshot executes the funded plan against the deployed hook, Tempo Exchange, PoolManager, and Universal Router, then reverts the snapshot.",
    proof: "A direct hook read cannot substitute for complete transaction evidence."
  },
  reconcile: {
    step: "STEP 5",
    title: "Separate swap output from transaction gas.",
    body: "The validator reads the receipt's output transfer, wallet delta, fee token, fee payer, and fee-collector transfer before explaining any difference.",
    proof: "Missing or ambiguous token-flow evidence remains indeterminate and stays out."
  },
  admit: {
    step: "STEP 6",
    title: "Admit only evidence bound to the same request.",
    body: "Quote and execution must match, and validation must bind the route key, raw input, chain, block number and hash, full execution plan, and recipient output.",
    proof: "Only then is the route added to comparisonInput."
  }
};

const pipelineButtons = [...document.querySelectorAll(".pipeline-step")];
const pipelineLabel = document.querySelector("#pipeline-step-label");
const pipelineTitle = document.querySelector("#pipeline-detail-title");
const pipelineBody = document.querySelector("#pipeline-detail-body");
const pipelineProof = document.querySelector("#pipeline-detail-proof");

pipelineButtons.forEach((button) => button.addEventListener("click", () => {
  const stage = pipelineStages[button.dataset.stage];
  pipelineButtons.forEach((item) => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
  });
  pipelineLabel.textContent = stage.step;
  pipelineTitle.textContent = stage.title;
  pipelineBody.textContent = stage.body;
  pipelineProof.innerHTML = `<strong>Guard</strong> ${stage.proof}`;
}));

const evidenceToggles = [...document.querySelectorAll(".evidence-toggle")];
const evidencePanels = [...document.querySelectorAll("[data-evidence-panel]")];
evidenceToggles.forEach((button) => button.addEventListener("click", () => {
  evidenceToggles.forEach((item) => item.classList.toggle("active", item === button));
  evidencePanels.forEach((panel) => {
    const active = panel.dataset.evidencePanel === button.dataset.evidence;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}));

const tabs = [...document.querySelectorAll(".top-tab")];
const panels = [...document.querySelectorAll(".tab-panel")];
tabs.forEach((tab) => tab.addEventListener("click", (event) => {
  tabs.forEach((item) => {
    const active = item === tab;
    item.classList.toggle("active", active);
    item.setAttribute("aria-selected", String(active));
  });
  panels.forEach((panel) => { panel.hidden = panel.id !== `${tab.dataset.tab}-panel`; });
  if (event.isTrusted) window.scrollTo({ top: 0, behavior: "smooth" });
}));

const initialHash = window.location.hash;
const initialTarget = initialHash ? document.querySelector(initialHash) : null;
if (initialHash === "#solution" || initialTarget?.closest("#solution-panel")) {
  document.querySelector("#solution-tab").click();
  if (initialTarget) window.setTimeout(() => initialTarget.scrollIntoView(), 0);
}
