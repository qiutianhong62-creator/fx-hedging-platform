# Phase 12 Payable Dashboard Implementation Plan

**Goal:** 同一网页支持美元应收与应付，正确比较收入、成本及目标概率。

**Architecture:** 复用后端自动概率 API；扩展前端方向类型、文案与显示转换。使用请求版本阻止已失效请求覆盖界面。

**Tech Stack:** React、TypeScript、FastAPI、pytest、Node test。

## Global Constraints

USD/CNY；同一到期日；银行真实远期报价；切换保留敞口金额/日期，重置交易/目标/结果；收益和成本解释反向；后端概率为唯一计算来源。

## Tasks

- [x] 1. 在 tests/probability-dashboard.test.ts 增加美元应付请求和双向清空案例；扩展 lib/api/forwardProbability.ts 的 ExposureType、ResultKind，lib/analysis/probabilityDashboard.ts 的草稿与 switchExposure。
  - 请求使用 exposure_type: draft.exposureType。
  - 切换返回 { ...createInitialDraft(), exposureType, notionalUsd: draft.notionalUsd, maturityDate: draft.maturityDate }。
  - 运行 Node 单测观察缺失行为失败后实现，保留原收款测试。
- [x] 2. 新增 lib/analysis/exposurePresentation.ts，集中收款/付款文案和差额转换；对负值、跨零、零及倒序区间建立测试。
  - 付款差额 [min, max] 转为 [-max, -min]；显示保留正负号与单位。
  - 更新 AnalysisInputPanel、ForwardLegEditor、AnalysisSummary、ProbabilityComparisonTable、TargetAnalysisPanel、RiskNotices。
- [x] 3. ProbabilityDashboard 增加方向选择与重置，并用请求序号拒绝旧响应。
  - 每次输入变更、方向切换或新请求递增序号；await 后仅接收匹配序号的成功与错误。
  - 目标变更清空旧目标概率；过期结果禁用目标提交。
- [x] 4. python/tests/backend/test_automatic_forward_strategy_probability_api.py 增加付款预算完整/部分/超额套保案例及边界相等。
  - 固定数据源通过既有依赖覆盖提供，不依赖实时网络；确认成本标签、预算概率及现金流。
- [x] 5. 更新 README、页面描述，运行 Python 和 Node 测试、类型检查、源码 lint、两种构建及页面交互检查。
  - Python: PYTHONPATH=python .venv/bin/python -m pytest python/tests -q
  - Node: node --experimental-strip-types --test tests/*.test.ts
  - 类型/构建使用现有 node_modules 中 tsc、vinext、vite，避免自动安装改变依赖。
  - 手工验收付款提交、预算、切换清空、在途切换、原收款、超额套保和窄屏。

## 验证结果

后端 283 项、前端单测 19 项、服务端渲染 2 项通过；类型检查、源码 ESLint、vinext 与静态构建通过。
Playwright 使用真实 Python API 加固定市场数据验证了付款预算、全额/超额套保、8/22 行、切换清空、在途请求失效、收款回归和 390px 布局。
浏览器脚本为 tests/payable-dashboard.browser.mjs；PLAYWRIGHT_PACKAGE 指向本机 Playwright，CHROME_PATH 指向本机 Chrome，PREVIEW_URL 默认为 http://127.0.0.1:3012。
固定测试数据不是最新机构预测。保留既有 Starlette 弃用警告；未修改依赖。
