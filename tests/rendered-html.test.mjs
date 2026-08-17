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
  assert.match(html, /USD\/CNY · 美元应收 · 同一到期日/);
  assert.match(html, /美元应收金额/);
  assert.match(html, /分析到期日/);
  assert.match(html, /远期结汇交易/);
  assert.match(html, /添加一笔远期/);
  assert.match(html, /远期总金额/);
  assert.match(html, /开始概率分析/);
  assert.match(html, /数据来自 ING、MUFG 与 FRED/);
  assert.doesNotMatch(html, /观察的到期即期汇率/);
  assert.doesNotMatch(html, /自由交易搭建器/);
});

test("serves a compact content security policy", async () => {
  const response = await render();
  const policy = response.headers.get("content-security-policy") ?? "";
  assert.ok(policy.length < 4096);
});
