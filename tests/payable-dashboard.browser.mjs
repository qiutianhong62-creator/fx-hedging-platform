// Run against a local preview. API replies use the real Python endpoint with fixed test data.
// PLAYWRIGHT_PACKAGE must point to an installed playwright entry; no extra dependency is installed.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import test from "node:test";

const { chromium } = await import(process.env.PLAYWRIGHT_PACKAGE ?? "playwright");
const apiPath = "/api/v1/analysis/forward-strategy/automatic-probability";
const pythonCode = `
import json, sys
from tests.backend.test_automatic_forward_strategy_probability_api import client, automatic_service
from backend.main import app
from backend.routes.forward_strategy import get_automatic_forward_strategy_probability_service
app.dependency_overrides[get_automatic_forward_strategy_probability_service] = automatic_service
response = client.post("/api/v1/analysis/forward-strategy/automatic-probability", json=json.loads(sys.argv[1]))
assert response.status_code == 200, response.text
print(response.text)
`;

test("payable workflow, budget, reset, delayed responses and receivable regression", async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH,
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const requests = [];
    let holdNext = false;
    let release;
    let started;
    await page.route(`**${apiPath}`, async (route) => {
      if (route.request().method() === "OPTIONS") {
        return route.fulfill({ status: 204, headers: {
          "access-control-allow-origin": "*",
          "access-control-allow-headers": "content-type",
          "access-control-allow-methods": "POST, OPTIONS",
        } });
      }
      const payload = route.request().postDataJSON();
      requests.push(payload);
      if (holdNext) {
        holdNext = false;
        await new Promise((resolve) => { release = resolve; started(); });
      }
      const body = execFileSync(".venv/bin/python", ["-c", pythonCode, JSON.stringify(payload)], {
        env: { ...process.env, PYTHONPATH: "python", PYTHONWARNINGS: "ignore" },
        encoding: "utf8",
      });
      await route.fulfill({ status: 200, contentType: "application/json", body,
        headers: { "access-control-allow-origin": "*" } });
    });
    await page.goto(process.env.PREVIEW_URL ?? "http://127.0.0.1:3012");
    await page.waitForLoadState("networkidle");
    const receive = page.getByRole("radio", { name: "未来收到美元（出口收款）" });
    const pay = page.getByRole("radio", { name: "未来支付美元（进口付款）" });
    const submit = page.getByRole("button", { name: "开始概率分析", exact: true });
    await pay.check();
    await page.getByText("美元应付金额", { exact: true }).waitFor();
    await page.getByLabel("美元应付金额").fill("1000000");
    const date = new Date(); date.setDate(date.getDate() + 180);
    const maturity = date.toISOString().slice(0, 10);
    await page.getByLabel("分析到期日").fill(maturity);
    await page.getByLabel("第 1 笔远期美元金额").fill("500000");
    await page.getByLabel("第 1 笔远期购汇报价").fill("6.8");
    await submit.click();
    await page.getByText("远期策略预计成本", { exact: true }).waitFor();
    assert.equal(requests.at(-1).exposure_type, "usd_payable");
    assert.match(await page.locator(".analysis-summary-grid").innerText(), /672.50/);
    assert.equal(await page.locator(".probability-table tbody tr").count(), 8);
    assert.equal(await page.getByRole("columnheader", { name: "节省成本" }).count(), 1);
    await page.getByRole("button", { name: "查看完整分布" }).click();
    assert.equal(await page.locator(".probability-table tbody tr").count(), 22);
    await page.getByLabel("人民币预算上限").fill("7000000");
    await page.getByRole("button", { name: "计算达标概率", exact: true }).click();
    await page.getByText("远期策略不超过预算", { exact: true }).waitFor();
    assert.equal(requests.at(-1).target_cny, 7000000);
    assert.match(await page.locator(".target-result-grid").innerText(), /超出预算/);
    if (process.env.SCREENSHOT_PATH) {
      await page.screenshot({ path: process.env.SCREENSHOT_PATH, fullPage: true });
    }
    // Target edits cannot leave old probabilities alongside a new budget.
    await page.getByLabel("人民币预算上限").fill("6800000");
    assert.equal(await page.locator(".target-result-grid").count(), 0);
    // Full coverage at exactly the budget is always within budget in this model.
    await page.getByLabel("第 1 笔远期美元金额").fill("1000000");
    assert.ok(await page.getByRole("button", { name: "计算达标概率", exact: true }).isDisabled());
    await submit.click();
    await submit.waitFor();
    await page.getByRole("button", { name: "计算达标概率", exact: true }).click();
    await page.getByText("远期策略不超过预算", { exact: true }).waitFor();
    assert.match(await page.locator(".target-result-grid article").nth(1).innerText(), /100.0%/);
    await page.getByLabel("第 1 笔远期美元金额").fill("1200000");
    assert.match(await page.locator(".overhedge-warning").innerText(), /美元应付/);
    await submit.click();
    await submit.waitFor();
    // Switching clears quote/target/results but preserves amount/date.
    await receive.check();
    assert.equal(await page.getByLabel("美元应收金额").inputValue(), "1000000");
    assert.equal(await page.getByLabel("分析到期日").inputValue(), maturity);
    assert.equal(await page.getByLabel("第 1 笔远期结汇报价").inputValue(), "");
    assert.equal(await page.locator(".results-stack").count(), 0);
    await page.getByLabel("第 1 笔远期美元金额").fill("500000");
    await page.getByLabel("第 1 笔远期结汇报价").fill("6.8");
    await submit.click();
    await page.getByText("远期策略预计收款", { exact: true }).waitFor();
    assert.equal(requests.at(-1).exposure_type, "usd_receivable");
    assert.equal(await page.getByLabel("目标人民币金额").inputValue(), "");
    // A response from the old direction must not resurrect old results.
    holdNext = true;
    const pending = new Promise((resolve) => { started = resolve; });
    await submit.click();
    await pending;
    await pay.check();
    const returned = page.waitForResponse((response) => response.url().endsWith(apiPath) && response.request().method() === "POST");
    release();
    await returned;
    await page.waitForLoadState("networkidle");
    assert.equal(await page.locator(".results-stack").count(), 0);
    assert.equal(await page.getByLabel("第 1 笔远期购汇报价").inputValue(), "");
    assert.doesNotMatch(await page.locator(".coverage-strip").innerText(), /NaN/);
    // Narrow screen keeps the input layout inside the viewport.
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    assert.deepEqual(errors, []);
    console.log("Passed: payable costs/budget, 8/22 rows, full and overhedge, reset, stale request, receivable, 390px.");
  } finally {
    await browser.close();
  }
});
