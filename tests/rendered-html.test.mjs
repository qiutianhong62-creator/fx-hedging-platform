import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);

  return worker.fetch(
    new Request("http://localhost/", {
      headers: { accept: "text/html" },
    }),
    {
      ASSETS: {
        fetch: async () => new Response("Not found", { status: 404 }),
      },
    },
    {
      waitUntil() {},
      passThroughOnException() {},
    },
  );
}

test("server-renders the Chinese hedge analysis platform", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);

  const html = await response.text();
  assert.match(html, /<html lang="zh-CN">/i);
  assert.match(html, /<title>企业外汇套保与风险分析平台<\/title>/i);
  assert.match(html, /远期 · 掉期 · 期权 · 定存/);
  assert.match(html, /套保比例/);
  assert.match(html, /预计人民币收入/);
  assert.match(html, /到期汇率对人民币收入的影响/);
  assert.match(html, /不套保/);
  assert.match(html, /自由交易搭建器/);
  assert.match(html, /你来选择每一笔交易/);
  assert.match(html, /远期1/);
  assert.match(html, /期权1/);
  assert.match(html, /自动命名/);
  assert.match(html, /你的交易清单/);
  assert.match(html, /组合损益 = Σ 每笔交易损益/);
  assert.match(html, /自选产品组合的到期损益曲线/);
  assert.match(html, /掉期以远端日期作为分析到期日/);
  assert.match(html, /切换产品时，交易名称、金额、币种和日期不会被清空/);
  assert.match(html, /掉期近端与远端方向自动相反/);
  assert.match(html, /自动展示兑换金额、点差、期限和掉期年化收益/);
  assert.match(html, /组合持有期收益率/);
  assert.match(html, /组合年化收益率（参考）/);
  assert.match(html, /收益率口径/);
  assert.match(html, /定存会自动计算税前、税额与税后利息/);
  assert.match(html, /远期还可以直接引用任一定存的税后利息/);
  assert.match(html, /＋(?:<!-- -->)?远期/);
  assert.match(html, /＋(?:<!-- -->)?期权/);
  assert.match(html, /＋(?:<!-- -->)?掉期/);
  assert.match(html, /＋(?:<!-- -->)?定存/);
});

test("serves a compact content security policy", async () => {
  const response = await render();
  const policy = response.headers.get("content-security-policy") ?? "";
  assert.ok(policy.length < 4096);
});
