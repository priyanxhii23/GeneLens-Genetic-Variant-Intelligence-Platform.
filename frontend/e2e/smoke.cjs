/**
 * GeneLens end-to-end acceptance checks (Part 14 of the upgrade brief).
 * Requires both servers running (backend :8000, frontend :5173) and at least
 * one completed analysis (HBB) plus one synthetic job linked to it, and a
 * second completed gnomAD v4 analysis (CFTR) for the comparison lab.
 *
 *   node e2e/smoke.cjs <analysisId> [screenshotDir] [customDatasetFile]
 *
 * Uses Playwright (npm i -D playwright && npx playwright install chromium).
 */
const { chromium } = require("playwright");

const BASE = process.env.GENELENS_URL || "http://localhost:5173";
const AID = process.argv[2];
const SHOTS = process.argv[3];
const CUSTOM_FILE = process.argv[4];
const results = [];
const check = (name, ok, detail = "") => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? ` – ${detail}` : ""}`); };

(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await ctx.addInitScript((a) => { if (!sessionStorage.getItem("init")) { localStorage.clear(); localStorage.setItem("genelens-analysis", a); localStorage.setItem("genelens-theme", "dark"); sessionStorage.setItem("init", "1"); } }, AID);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  const shot = async (name) => { if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` }); };
  const go = async (path) => { await page.goto(BASE + path, { waitUntil: "networkidle" }); await page.waitForTimeout(1200); };

  // ---------- landing + branding
  await go("/");
  await shot("landing");
  await go("/workspace");
  const logo = await page.locator("aside a[title='GeneLens home'] > span").first().boundingBox();
  check("Logo enlarged (≥ 46 px)", logo && logo.width >= 46, `${logo && logo.width}px`);
  const nav = await page.locator("aside nav").innerText();
  check("Nav has Gene Comparison Lab", nav.includes("Gene Comparison Lab"));
  check("Nav has Source Manager", nav.includes("Source Manager"));
  check("Standalone History removed from nav", !/History/.test(nav));
  const fonts = await page.evaluate(() => [getComputedStyle(document.querySelector("h1")).fontFamily, getComputedStyle(document.body).fontFamily]);
  check("Typography: DM Serif Display headings + Manrope body", fonts[0].includes("DM Serif Display") && fonts[1].includes("Manrope"), fonts.join(" | "));

  // ---------- gene search
  const input = page.getByRole("combobox", { name: "Gene symbol" });
  await input.click();
  await page.waitForTimeout(800);
  const opts = await page.locator("#gene-listbox [role=option]").allInnerTexts();
  const starters = ["HBB", "CFTR", "BRCA1", "BRCA2", "TP53", "LDLR", "G6PD", "PAH"];
  check("Suggestions appear before typing (all 8 starters)", starters.every((g) => opts.some((o) => o.startsWith(g))), `${opts.length} options`);
  check("Suggestions show full names + descriptions", opts.some((o) => o.includes("Hemoglobin subunit beta") && o.includes("sickle")));
  await shot("gene-search-open");
  await input.fill("brc");
  await page.waitForTimeout(900);
  const filtered = await page.locator("#gene-listbox [role=option]").allInnerTexts();
  check("Typing filters suggestions", filtered.some((o) => o.startsWith("BRCA1")) && filtered.some((o) => o.startsWith("BRCA2")) && !filtered.some((o) => o.startsWith("HBB")));
  await input.press("ArrowDown"); await input.press("ArrowUp"); await input.press("Enter");
  check("Keyboard selection populates input", /^BRCA[12]$/.test(await input.inputValue()), await input.inputValue());
  await input.click(); await page.waitForTimeout(400); await input.press("Escape");
  await page.waitForTimeout(500); // exit animation
  check("Escape closes dropdown", (await page.locator("#gene-listbox").count()) === 0);

  // ---------- datasets
  await page.getByRole("button", { name: /gnomAD v4 – Exomes \+ Genomes/ }).click();
  await page.waitForTimeout(400);
  const dsOpts = await page.locator("[role=listbox] [role=option]").allInnerTexts();
  check("Dataset picker lists 10 datasets", dsOpts.length === 10, `${dsOpts.length}`);
  check("Dataset entries show provider, assembly, release, status", dsOpts.every((o) => /GRCh3[78]/.test(o) && /(available|unavailable)/.test(o)));
  await shot("dataset-picker");
  await page.locator("[role=option]", { hasText: "1000 Genomes Project – Phase 3" }).click();
  const desc = await page.locator("form").innerText();
  check("Selected dataset shows description", desc.includes("2,504 individuals"));

  // ---------- real / synthetic modes in Variant Explorer
  const setMode = async (label) => { await page.getByRole("radio", { name: label }).click(); await page.waitForTimeout(1500); };
  await go("/workspace/variants");
  const rowsInfo = () => page.evaluate(() => {
    const rows = [...document.querySelectorAll("tbody tr")].filter((r) => r.querySelectorAll("td").length > 5);
    return {
      n: rows.length,
      badges: [...new Set(rows.map((r) => (r.innerText.match(/\b(REAL|SYNTHETIC)\b/) || [""])[0]))],
      real: rows.filter((r) => r.classList.contains("prov-real")).length,
      syn: rows.filter((r) => r.classList.contains("prov-synthetic")).length,
      stripes: rows.some((r) => getComputedStyle(r).backgroundImage.includes("gradient")),
      synId: document.querySelectorAll("tbody .syn-id").length,
      outline: rows[0] ? getComputedStyle(rows[0]).outlineColor : "",
      count: document.body.innerText.match(/([\d,]+) records · page/)?.[1],
    };
  });
  await setMode("Real");
  let r = await rowsInfo();
  check("REAL mode shows only real records", r.n > 0 && r.badges.join() === "REAL", JSON.stringify(r.badges));
  check("REAL mode has no outlines or stripes", r.real === 0 && r.syn === 0 && !r.stripes);
  const realCount = r.count;
  await shot("explorer-real");
  await setMode("Synthetic");
  r = await rowsInfo();
  check("SYNTHETIC mode shows only synthetic records", r.n > 0 && r.badges.join() === "SYNTHETIC", JSON.stringify(r.badges));
  check("SYNTHETIC mode: pink identifier accent, no stripes, no row outlines", r.synId > 0 && !r.stripes && r.real === 0 && r.syn === 0);
  check("Record count changes with mode", r.count && r.count !== realCount, `${realCount} → ${r.count}`);
  await shot("explorer-synthetic");
  await setMode("Both");
  await page.getByRole("button", { name: "Sort by AF" }).click(); await page.waitForTimeout(1500);
  r = await rowsInfo();
  check("BOTH mode shows real and synthetic", r.real > 0 && r.syn > 0, `real ${r.real}, syn ${r.syn}`);
  const outlines = await page.evaluate(() => {
    const css = (sel) => { const el = document.querySelector(sel); return el ? getComputedStyle(el).outlineColor : null; };
    const v = (n) => getComputedStyle(document.documentElement).getPropertyValue(`--${n}`).trim().split(/\s+/).join(", ");
    return { real: css("tr.prov-real"), syn: css("tr.prov-synthetic"), gold: v("gold"), pink: v("pink") };
  });
  check("BOTH: real rows gold outline, synthetic rows pink outline", outlines.real?.includes(outlines.gold) && outlines.syn?.includes(outlines.pink), JSON.stringify(outlines));
  check("BOTH: no diagonal stripes", !r.stripes);
  await shot("explorer-both");

  // metrics respond to mode
  await go("/workspace");
  const metric = async () => page.locator("text=Pathogenic / LP").locator("xpath=../..").innerText();
  await setMode("Real"); const mReal = await metric();
  await setMode("Synthetic"); const mSyn = await metric();
  check("Command Center metrics respond to mode", mReal !== mSyn, `${mReal.replace(/\s+/g, " ")} | ${mSyn.replace(/\s+/g, " ")}`);
  await setMode("Real");
  await shot("command-center");

  // ---------- explanations
  await go("/workspace/pathogenicity");
  const reasonSize = await page.evaluate(() => parseFloat(getComputedStyle(document.querySelector(".insight-reason")).fontSize));
  const detailSize = await page.evaluate(() => parseFloat(getComputedStyle(document.querySelector(".insight-detail")).fontSize));
  check("Main reason is prominent (17–19px)", reasonSize >= 17 && reasonSize <= 19, `${reasonSize}px`);
  check("Detailed explanation readable (15–16px)", detailSize >= 15 && detailSize <= 16, `${detailSize}px`);
  check("Guide uses bold scientific terms", (await page.locator(".guide b").count()) > 5);
  await shot("pathogenicity");
  await go("/workspace/populations");
  const popText = await page.locator("main").innerText();
  check("Population guide explains missing ≠ zero", popText.includes("does NOT mean the allele frequency is zero"));
  await shot("populations");
  await go("/workspace/constraint");
  check("Constraint guide explains LOEUF", (await page.locator("main").innerText()).includes("Lower LOEUF = stronger constraint"));
  await shot("constraint");

  // ---------- anomaly cards
  await go("/workspace/anomalies");
  const an = await page.locator("main").innerText();
  check("No 'triggering evidence' on anomaly cards", !/triggering evidence/i.test(an));
  check("No raw JSON on anomaly page", (await page.locator("main pre").count()) === 0);
  const firstCard = page.locator("main li.panel").first();
  const expanded = await firstCard.getAttribute("class");
  if (!(await firstCard.innerText()).includes("Why this matters")) await firstCard.locator("button").first().click();
  await page.waitForTimeout(500);
  const card = await firstCard.innerText();
  const cardL = card.toLowerCase();  // eyebrow labels are CSS-uppercased in innerText
  check("Anomaly card: reason, why it matters, recommendation", cardL.includes("reason") && cardL.includes("why this matters") && cardL.includes("recommended investigation") && cardL.includes("priority"), expanded ? "" : "");
  await shot("anomalies");
  await firstCard.getByRole("button", { name: /Full variant details/ }).click();
  await page.waitForTimeout(1500);
  const drawer = await page.locator("[role=dialog]").innerText();
  check("Variant details are structured, without raw technical evidence", !drawer.includes("Technical evidence") && (await page.locator("[role=dialog] pre").count()) === 0 && /Population frequency/i.test(drawer) && /Clinical classification/i.test(drawer));
  await page.keyboard.press("Escape");

  // ---------- statistics + synthetic lab
  await go("/workspace/statistics"); await shot("statistics");
  await go("/workspace/synthetic"); await shot("synthetic");
  const synStripes = await page.evaluate(() => [...document.querySelectorAll("*")].some((e) => getComputedStyle(e).backgroundImage.includes("repeating-linear-gradient")));
  check("No diagonal stripes anywhere in Synthetic Lab", !synStripes);

  // ---------- sources
  await go("/workspace/sources");
  await page.waitForTimeout(2500);
  check("Source Manager shows 7 sources", (await page.locator("article.panel").count()) === 7);
  const srcText = await page.locator("main").innerText();
  check("Sources show method, last connection, records, refresh", ["integration method", "last successful connection", "records retrieved", "refresh"].every((t) => srcText.toLowerCase().includes(t)));
  await shot("sources");

  // ---------- population observatory content
  await go("/workspace/populations");
  await page.waitForSelector("text=Variants with population data", { timeout: 20000 }).catch(() => {});
  const pop = (await page.locator("main").innerText()).toLowerCase();  // labels are CSS-uppercased
  check("Population Observatory loads metrics and highest AF per group", pop.includes("variants with population data") && pop.includes("highest af in group"));

  // ---------- comparison lab
  await go("/workspace/compare");
  await page.waitForTimeout(3000);
  // gene dropdown must render above every panel (portal) – hit-test each visible option
  const combo = page.locator("main input[role=combobox]").first();
  if (await combo.count()) {
    await combo.click(); await page.waitForTimeout(600);
    const hit = await page.evaluate(() => {
      const opts = [...document.querySelectorAll("[role=option]")].filter((o) => { const r = o.getBoundingClientRect(); return r.height > 0 && r.top >= 0 && r.bottom <= innerHeight; });
      return { n: opts.length, ok: opts.every((o) => { const r = o.getBoundingClientRect(); const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return o.contains(el); }) };
    });
    check("Comparison gene dropdown is on top of all panels", hit.n > 0 && hit.ok, `${hit.n} visible options`);
    await page.keyboard.press("Escape");
  }
  const cmp = await page.locator("main").innerText();
  check("Comparison shows HBB and CFTR side by side", (await page.locator("main .font-display", { hasText: /^HBB$/ }).count()) > 0 && (await page.locator("main .font-display", { hasText: /^CFTR$/ }).count()) > 0);
  check("What-if shows previous/updated/difference/% change", ["previous result", "updated result", "difference", "% change"].every((t) => cmp.toLowerCase().includes(t)));
  const updated = page.locator("text=Updated result").locator("xpath=..");
  await updated.scrollIntoViewIfNeeded();
  await page.waitForTimeout(1800); // counters animate once visible
  const before = await updated.innerText();
  const resp = page.waitForResponse((r) => r.url().includes("/compare/whatif") && r.request().postData().includes('"rare_benign_af":0.000001'));
  await page.getByRole("slider", { name: "Rare-benign threshold" }).nth(1).fill("-6");
  await resp;
  await updated.scrollIntoViewIfNeeded();
  await page.waitForTimeout(2600); // counter animation (1.1 s) + render
  const after = await updated.innerText();
  const num = (t) => Number((t.match(/[\d,]+/) || ["NaN"])[0].replace(/,/g, ""));
  check("Changing a scenario parameter updates the what-if result", num(before) > 0 && num(after) < num(before), `${before.replace(/\s+/g, " ")} → ${after.replace(/\s+/g, " ")}`);
  await page.getByPlaceholder("Name this comparison").fill("e2e HBB vs CFTR");
  await page.getByRole("button", { name: "Save comparison" }).click();
  await page.waitForTimeout(1500);
  check("Comparison saved and listed", (await page.locator("main").innerText()).includes("e2e HBB vs CFTR"));
  await shot("compare");

  // ---------- reports with provenance history
  await go("/workspace/reports");
  check("Provenance history preserved in Report Generator", (await page.locator("main").innerText()).includes("Analysis history & provenance"));
  await shot("reports");

  // ---------- custom dataset lab
  if (CUSTOM_FILE) {
    await go("/workspace/custom");
    await page.getByTestId("add-dataset").click();
    await page.setInputFiles("[data-testid=file-input]", CUSTOM_FILE);
    await page.getByRole("button", { name: "Upload & inspect" }).click();
    await page.waitForSelector("[data-testid=preview-table]", { timeout: 30000 });
    const rows = await page.locator("[data-testid=preview-table] tbody tr").count();
    check("Custom upload shows a 10–20 row preview before processing", rows >= 10 && rows <= 20, `${rows} rows`);
    check("Custom data labelled CUSTOM DATA", (await page.locator("text=CUSTOM DATA").count()) > 0);
    await page.getByRole("radio", { name: "GRCh38" }).click();
    await page.getByTestId("run-analysis").click();
    await page.waitForSelector("text=Where each result comes from", { timeout: 120000 });
    const dash = (await page.locator("main").innerText()).toLowerCase();
    check("Custom dashboard shows totals, provenance of values and quality", ["total records", "valid", "duplicates", "quality checks", "clinvar matching"].every((t) => dash.includes(t)));
    await shot("custom-dataset");
  }

  // ---------- no raw JSON / stack traces anywhere
  for (const p of ["/workspace", "/workspace/variants", "/workspace/pathogenicity", "/workspace/populations", "/workspace/constraint", "/workspace/anomalies", "/workspace/statistics", "/workspace/synthetic", "/workspace/compare", "/workspace/reports", "/workspace/sources", "/workspace/custom"]) {
    await go(p);
    const t = await page.locator("main").innerText();
    check(`No raw JSON or traceback on ${p}`, (await page.locator("main pre").count()) === 0 && !/Traceback|\bat Object\.|\{"detail"/.test(t));
  }

  // ---------- theme persistence
  await page.getByRole("button", { name: /Switch to light theme/ }).click();
  await page.reload({ waitUntil: "networkidle" });
  check("Light theme persists across reload", (await page.evaluate(() => document.documentElement.dataset.theme)) === "light");
  await go("/workspace"); await shot("command-center-light");
  await go("/workspace/variants"); await setMode("Both"); await shot("explorer-both-light");
  await setMode("Real");

  // ---------- responsiveness
  for (const w of [1280, 1024, 768]) {
    await page.setViewportSize({ width: w, height: 900 });
    for (const p of ["/workspace", "/workspace/variants", "/workspace/pathogenicity", "/workspace/populations", "/workspace/constraint", "/workspace/anomalies", "/workspace/statistics", "/workspace/synthetic", "/workspace/compare", "/workspace/reports", "/workspace/sources", "/workspace/custom"]) {
      await go(p);
      const sw = await page.evaluate(() => document.documentElement.scrollWidth);
      check(`No horizontal page overflow at ${w}px (light) on ${p}`, sw <= w, `${sw}px`);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  check("No console errors", errors.length === 0, errors.slice(0, 5).join(" ‖ "));
  const failed = results.filter((x) => !x.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  await browser.close();
  process.exit(failed.length ? 1 : 0);
})();
