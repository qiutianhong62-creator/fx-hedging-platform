# 企业外汇套保与风险分析平台

完整的产品定位、跨产品策略比较和开发路线请参阅：[项目产品设计说明](docs/项目产品设计说明.md)。期权的四类头寸、企业敞口对应关系和到期收益公式请参阅：[外汇期权模块设计](docs/期权模块设计.md)。

面向出口企业的 USD/CNY 外汇套保与风险分析项目。当前网页版本聚焦“美元应收 + 同一到期日 + 一笔或多笔远期结汇”：用户输入真实银行报价，系统连接 ING、MUFG 与 FRED 数据，比较不套保和远期策略的到期人民币收款概率。

## 当前功能

- 远期结汇收益计算
- 一笔或多笔真实远期结汇报价
- 套保覆盖比例、未套保金额和过度套保提醒
- 不套保与远期策略的预计收款及 50%/90% 金额范围
- 20 个核心汇率区间与两个极端尾部的概率表
- 自定义目标人民币金额及两种方案的达标概率
- 机构预测、历史波动率、权重、缓存与降级状态说明
- ING 与 MUFG 的 USD/CNY 到期汇率综合预测
- 不套保与远期策略的自动概率分析
- Python 计算引擎及单元测试
- 为期权、期货、掉期和货币市场套保预留产品接口

## 核心公式

```text
最终人民币收入
= 美元敞口 × 套保比例 × 远期汇率
+ 美元敞口 × (1 - 套保比例) × 到期即期汇率
```

## 目录

```text
app/                    网页界面
components/             输入、概率结果和图表组件
lib/api/                前端到 Python 后端的统一连接层
lib/analysis/           前端输入校验和展示转换
python/backend/         Python API、市场数据与概率计算
python/tests/            Python 单元测试
```

## 组合策略结构

```text
企业敞口
  └─ 套保策略
       ├─ 远期组成项（比例、远期价、期限）
       ├─ 期权组成项（未来接入）
       ├─ 掉期组成项（未来接入）
       └─ 未覆盖部分（按到期即期价结算）
```

## 后续产品

外汇期权、外汇掉期、货币市场套保、区间远期、参与式远期和多产品组合。

## 第一阶段 Python 后端

创建独立 Python 3.12 环境并安装依赖：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r python/requirements.txt
```

启动后端：

```bash
.venv/bin/python -m uvicorn backend.main:app --app-dir python --reload
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- 交互式接口说明：`http://127.0.0.1:8000/docs`

运行全部 Python 测试：

```bash
PYTHONPATH=python .venv/bin/python -m pytest python/tests -v
```

### 第二阶段：不套保单一情景

启动后端并打开 `http://127.0.0.1:8000/docs`，展开：

```text
POST /api/v1/analysis/no-hedge/scenario
```

点击 `Try it out`，输入：

```json
{
  "currency_pair": "USD/CNY",
  "exposure_type": "usd_receivable",
  "notional_usd": 1000000,
  "maturity_date": "2030-12-31",
  "target_cny": 6800000,
  "assumed_maturity_spot": 6.75
}
```

返回结果应显示不套保金额为 `6750000.0`、未达标、距离目标 `50000.0`，并明确标记该汇率是假设而不是预测。

### 第八阶段：远期策略自动概率比较

启动后端并打开 `http://127.0.0.1:8000/docs`，展开：

```text
POST /api/v1/analysis/forward-strategy/automatic-probability
```

输入示例：

```json
{
  "currency_pair": "USD/CNY",
  "exposure_type": "usd_receivable",
  "notional_usd": 1000000,
  "maturity_date": "2026-12-31",
  "target_cny": 6800000,
  "forward_legs": [
    {
      "notional_usd": 500000,
      "forward_rate": 6.8
    }
  ]
}
```

实际测试时，请把 `maturity_date` 替换为当天之后、365天以内，并且不超过当前机构预测最远日期的有效日期。

用户只输入敞口、到期日、可选目标金额和真实远期报价。系统自动读取当前接入的机构预测与历史波动率，并在同一概率分布下返回不套保和远期策略的预计金额、50%与90%金额范围、目标达标概率、策略更优概率和范围变化。

### 第九阶段：ING + MUFG 综合预测

系统分别读取 ING 与 MUFG 的公开 USD/CNY 季度预测，分别换算到用户到期日，再以 50%/50% 等权生成预计到期汇率。若只有一家来源可用，系统会返回 `single_source_fallback`、100% 权重和另一来源的失败原因；两家都不可用时不会编造预测。

启动后端后，在 `http://127.0.0.1:8000/docs` 测试：

```text
GET /api/v1/forecasts/usd-cny/maturity-estimate
```

把 `maturity_date` 填为当前日期之后 365 天以内，并且不超过机构最远预测日期的日期。正常综合结果应看到：

```text
aggregation_status = equal_weight_consensus
source_count = 2
ING weight = 0.5
MUFG weight = 0.5
```

机构预测和概率模型都可能与实际结果明显不同，结果不构成交易或套保建议。

### 第十阶段：完整汇率概率剖面

现有概率响应新增 `probability_profile`，不需要用户增加输入。该字段包含 P1–P99 之间的 20 个等宽汇率区间、P1 以下的左尾风险和 P99 以上的右尾风险。

每个主要区间返回：

- 区间自身的发生概率；
- 低于和高于区间上边界的累计概率；
- 不套保人民币金额范围；
- 远期策略接口中的远期金额范围。

启动后端并在 `http://127.0.0.1:8000/docs` 中测试：

```text
POST /api/v1/analysis/no-hedge/probability
POST /api/v1/analysis/no-hedge/automatic-probability
POST /api/v1/analysis/forward-strategy/automatic-probability
```

检查 `bucket_count = 20`，`intervals` 长度为 20，且 20 个区间加左右尾部的概率合计约为 1。左右尾部是开放区间，因此只提供边界汇率、尾部概率和边界金额。

精确某一个汇率点在连续分布中的概率为零，因此系统展示“某个汇率区间的概率”，不将概率密度误称为点概率。概率剖面是对现有模型的更细展示，不代表机构预测或历史波动率本身因为区间增多而变得更准确。

### 第十一阶段：本地概率分析网页

这一阶段把网页直接连接到真实 Python 后端，仅用于本机运行，暂不部署线上版本。

第一次使用时，分别打开两个终端窗口。

终端 1：启动 Python 后端：

```bash
cd python
../.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

终端 2：启动前端：

```bash
pnpm dev
```

然后打开前端打印出的本地网址，并按以下顺序操作：

1. 输入美元应收金额和未来到期日。
2. 输入一笔或多笔银行提供的真实远期结汇报价。
3. 点击“开始概率分析”，检查 ING、MUFG、FRED 数据来源和默认显示的 8 个高概率区间。
4. 点击“查看完整分布”，查看 20 个核心区间和两个极端尾部。
5. 输入目标人民币金额，比较不套保和远期策略的目标达标概率。

前端默认请求 `http://127.0.0.1:8000`。如需使用其他本地后端地址，可在启动前设置：

```bash
NEXT_PUBLIC_FX_API_BASE_URL=http://127.0.0.1:8000 pnpm dev
```

远期总金额可以超过美元应收金额，系统不会阻止分析，但会明确显示过度套保金额和风险提示。ING 或 MUFG 只有一家可用时，系统会显示 `single_source_fallback` 和未参与机构的原因，不把单一来源伪装成完整共识；两家都不可用时不会编造预测。

机构预测可能与实际汇率明显不同，历史波动率也不保证代表未来波动。所有结果仅用于风险情景分析，不构成银行报价、交易建议或收益保证。
