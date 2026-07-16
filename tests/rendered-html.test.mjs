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
  assert.match(html, /远期结汇 · 交互式情景分析/);
  assert.match(html, /套保比例/);
  assert.match(html, /预计人民币收入/);
  assert.match(html, /到期汇率对人民币收入的影响/);
  assert.match(html, /不套保/);
});

test("serves a compact content security policy", async () => {
  const response = await render();
  const policy = response.headers.get("content-security-policy") ?? "";
  assert.ok(policy.length < 4096);
});
