# 企业外汇套保与风险分析平台

完整的产品定位、跨产品策略比较和开发路线请参阅：[项目产品设计说明](docs/项目产品设计说明.md)。期权的四类头寸、企业敞口对应关系和到期收益公式请参阅：[外汇期权模块设计](docs/期权模块设计.md)。

面向出口企业的交互式外汇套保产品与风险分析项目。当前版本接入远期结汇，并提供可扩展的组合策略计算框架：每个策略可以由多个产品组成项构成，系统分别计算现金流、成本和风险后再汇总。

## 当前功能

- 远期结汇收益计算
- 0%—100% 自定义套保比例
- 套保与不套保收益曲线对比
- 不套保、50%、80%、100%与自定义策略的五线对比
- 最差情景收入、最好情景收入和收入波动区间
- 组合策略组成项、覆盖比例与未覆盖敞口
- 重复覆盖和过度套保检查
- 到期汇率情景分析
- 人民币收入保护与机会成本解释
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
components/             交互图表组件
lib/strategies/         网页端产品计算模块
python/hedging/          Python 产品计算引擎
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
