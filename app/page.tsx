"use client";

import { useMemo, useState } from "react";
import { IncomeChart } from "../components/IncomeChart";
import { TradePortfolioLab } from "../components/TradePortfolioLab";
import {
  StrategyComparisonChart,
  type ComparisonSeries,
} from "../components/StrategyComparisonChart";
import {
  compareCompositeStrategy,
  createForwardStrategy,
} from "../lib/strategies/composite";
import {
  buildForwardScenarios,
  calculateForward,
} from "../lib/strategies/forward";

const products = [
  { name: "远期结汇", status: "基础模块", active: true, ready: true },
  { name: "外汇期权", status: "组合区可用", active: false, ready: true },
  { name: "外汇掉期", status: "组合区可用", active: false, ready: true },
  { name: "美元定存", status: "组合区可用", active: false, ready: true },
];

const strategyColors: Record<string, string> = {
  open: "#e5824f",
  half: "#4f86c6",
  eighty: "#8c6bb1",
  full: "#087f73",
  custom: "#17374f",
};

const money = new Intl.NumberFormat("zh-CN", {
  maximumFractionDigits: 0,
});

const wan = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function safeNumber(value: number, fallback: number) {
  return Number.isFinite(value) ? value : fallback;
}

export default function Home() {
  const [exposureUsd, setExposureUsd] = useState(1_000_000);
  const [hedgePercent, setHedgePercent] = useState(49);
  const [forwardRate, setForwardRate] = useState(6.74);
  const [maturitySpot, setMaturitySpot] = useState(6.6);
  const [scenarioMin, setScenarioMin] = useState(6.4);
  const [scenarioMax, setScenarioMax] = useState(7.1);

  const normalized = useMemo(() => {
    const safeMinimum = safeNumber(scenarioMin, 6.4);
    const safeMaximum = safeNumber(scenarioMax, 7.1);
    const minimum = Math.min(safeMinimum, safeMaximum - 0.01);
    const maximum = Math.max(safeMaximum, minimum + 0.01);
    return {
      exposureUsd: Math.max(0, safeNumber(exposureUsd, 0)),
      hedgeRatio: Math.min(1, Math.max(0, safeNumber(hedgePercent, 0) / 100)),
      forwardRate: Math.max(0.0001, safeNumber(forwardRate, 6.74)),
      maturitySpot: Math.min(
        maximum,
        Math.max(minimum, safeNumber(maturitySpot, minimum)),
      ),
      minimum,
      maximum,
    };
  }, [exposureUsd, hedgePercent, forwardRate, maturitySpot, scenarioMin, scenarioMax]);

  const summary = calculateForward(normalized);
  const scenarios = buildForwardScenarios(
    normalized,
    normalized.minimum,
    normalized.maximum,
    15,
  );

  const protectsIncome = summary.differenceCny >= 0;
  const selectedLabel = protectsIncome ? "套保保护" : "机会成本";
  const ratioLabel = `${Math.round(normalized.hedgeRatio * 100)}%`;

  const strategyComparisons = useMemo(() => {
    const strategies = [
      createForwardStrategy("open", "不套保", 0, normalized.forwardRate, "保留全部汇率波动"),
      createForwardStrategy("half", "套保 50%", 0.5, normalized.forwardRate, "稳定与机会之间的基础平衡"),
      createForwardStrategy("eighty", "套保 80%", 0.8, normalized.forwardRate, "以收入稳定为主要目标"),
      createForwardStrategy("full", "套保 100%", 1, normalized.forwardRate, "完全锁定远期结汇收入"),
      createForwardStrategy(
        "custom",
        `自定义 ${Math.round(normalized.hedgeRatio * 100)}%`,
        normalized.hedgeRatio,
        normalized.forwardRate,
        "当前自定义组合策略",
      ),
    ];
    return strategies.map((strategy) =>
      compareCompositeStrategy(
        normalized.exposureUsd,
        normalized.maturitySpot,
        strategy,
        normalized.minimum,
        normalized.maximum,
      ),
    );
  }, [normalized]);

  const comparisonSeries: ComparisonSeries[] = strategyComparisons.map((item) => ({
    id: item.strategy.id,
    label: item.strategy.name,
    color: strategyColors[item.strategy.id],
    points: item.scenarios,
    emphasized: item.strategy.id === "custom",
    dashed: item.strategy.id === "custom",
  }));

  const customComparison = strategyComparisons.find((item) => item.strategy.id === "custom")!;
  const mostStable = strategyComparisons.reduce((best, item) =>
    item.incomeRangeCny < best.incomeRangeCny ? item : best,
  );
  const highestIncome = strategyComparisons.reduce((best, item) =>
    item.selected.totalIncomeCny > best.selected.totalIncomeCny ? item : best,
  );

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="企业外汇套保与风险分析平台首页">
          <span className="brand-mark">FX</span>
          <span>
            <strong>企业外汇套保与风险分析平台</strong>
            <small>Corporate FX Hedge Lab</small>
          </span>
        </a>
        <div className="market-pill">
          <span className="pulse" />
          市场假设截至 2026-07-16
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">远期 · 掉期 · 期权 · 定存</p>
          <h1>把汇率风险，变成一条看得懂的收益曲线。</h1>
          <p className="hero-copy">
            先用基础远期模型理解套保，再逐笔添加你自己的远期、期权、掉期和定存交易，由网站合并生成一条组合损益曲线。
          </p>
          <a className="hero-cta" href="#trade-builder">进入自由交易搭建器 <span>↓</span></a>
        </div>
        <div className="hero-stat">
          <span>当前官方即期参考价</span>
          <strong>6.7909</strong>
          <small>人民币 / 美元 · SAFE 中间价</small>
        </div>
      </section>

      <section className="workspace">
        <aside className="control-panel">
          <div className="section-heading">
            <div>
              <span className="step">01</span>
              <h2>选择产品</h2>
            </div>
            <span className="tag">模块化架构</span>
          </div>

          <div className="product-list" aria-label="套保产品列表">
            {products.map((product) => (
              <button
                type="button"
                className={`product ${product.active ? "active" : ""}`}
                key={product.name}
                disabled={!product.active}
              >
                <span>{product.name}</span>
                <small>{product.status}</small>
              </button>
            ))}
          </div>

          <div className="divider" />

          <div className="section-heading compact">
            <div>
              <span className="step">02</span>
              <h2>设置参数</h2>
            </div>
          </div>

          <label className="field">
            <span>美元应收敞口</span>
            <div className="input-shell">
              <span>$</span>
              <input
                aria-label="美元应收敞口"
                type="number"
                min="0"
                step="10000"
                value={Number.isFinite(exposureUsd) ? exposureUsd : ""}
                onChange={(event) => setExposureUsd(event.target.value === "" ? Number.NaN : Number(event.target.value))}
              />
              <small>USD</small>
            </div>
          </label>

          <label className="field">
            <span>远期结汇汇率</span>
            <div className="input-shell">
              <input
                aria-label="远期结汇汇率"
                type="number"
                min="0.0001"
                step="0.0001"
                value={Number.isFinite(forwardRate) ? forwardRate : ""}
                onChange={(event) => setForwardRate(event.target.value === "" ? Number.NaN : Number(event.target.value))}
              />
              <small>CNY / USD</small>
            </div>
          </label>

          <div className="field slider-field">
            <div className="label-row">
              <span>套保比例</span>
              <strong>{ratioLabel}</strong>
            </div>
            <input
              aria-label="套保比例"
              type="range"
              min="0"
              max="100"
              step="1"
              value={hedgePercent}
              onChange={(event) => setHedgePercent(Number(event.target.value))}
            />
            <div className="range-ends"><span>0%</span><span>100%</span></div>
          </div>

          <div className="composition-box">
            <div className="composition-title">
              <span>当前组合策略</span>
              <small>总配置 100%</small>
            </div>
            <div className="strategy-leg active-leg">
              <span><i />远期结汇</span>
              <strong>{ratioLabel}</strong>
            </div>
            <div className="strategy-leg open-leg">
              <span><i />未套保部分</span>
              <strong>{Math.round((1 - normalized.hedgeRatio) * 100)}%</strong>
            </div>
            <div className="future-leg-row" aria-label="未来可加入的策略产品">
              <span>＋ 期权</span><span>＋ 掉期</span><span>＋ 定存</span>
            </div>
          </div>

          <label className="field">
            <span>观察的到期即期汇率</span>
            <div className="input-shell emphasized">
              <input
                aria-label="观察的到期即期汇率"
                type="number"
                min={normalized.minimum}
                max={normalized.maximum}
                step="0.01"
                value={Number.isFinite(maturitySpot) ? maturitySpot : ""}
                onChange={(event) => setMaturitySpot(event.target.value === "" ? Number.NaN : Number(event.target.value))}
              />
              <small>CNY / USD</small>
            </div>
          </label>

          <details className="scenario-settings">
            <summary>调整图表情景范围</summary>
            <div className="scenario-grid">
              <label>
                最低汇率
                <input
                  aria-label="情景最低汇率"
                  type="number"
                  step="0.05"
                  value={Number.isFinite(scenarioMin) ? scenarioMin : ""}
                  onChange={(event) => setScenarioMin(event.target.value === "" ? Number.NaN : Number(event.target.value))}
                />
              </label>
              <label>
                最高汇率
                <input
                  aria-label="情景最高汇率"
                  type="number"
                  step="0.05"
                  value={Number.isFinite(scenarioMax) ? scenarioMax : ""}
                  onChange={(event) => setScenarioMax(event.target.value === "" ? Number.NaN : Number(event.target.value))}
                />
              </label>
            </div>
          </details>
        </aside>

        <div className="analysis-panel">
          <div className="panel-header">
            <div>
              <p className="eyebrow">情景结果</p>
              <h2>{ratioLabel} 远期套保收益分析</h2>
            </div>
            <div className={`signal ${protectsIncome ? "positive" : "negative"}`}>
              <span>{selectedLabel}</span>
              <strong>
                {protectsIncome ? "+" : "−"}¥{wan.format(Math.abs(summary.differenceCny) / 10_000)}万
              </strong>
            </div>
          </div>

          <div className="kpi-grid">
            <article className="kpi">
              <span>已锁定美元</span>
              <strong>${money.format(summary.hedgedUsd)}</strong>
              <small>按 {forwardRate.toFixed(4)} 结汇</small>
            </article>
            <article className="kpi">
              <span>未套保美元</span>
              <strong>${money.format(summary.unhedgedUsd)}</strong>
              <small>随到期即期汇率变化</small>
            </article>
            <article className="kpi featured">
              <span>预计人民币收入</span>
              <strong>¥{wan.format(summary.totalIncomeCny / 10_000)}万</strong>
              <small>到期即期汇率 {normalized.maturitySpot.toFixed(2)}</small>
            </article>
          </div>

          <div className="chart-card">
            <div className="chart-heading">
              <div>
                <h3>到期汇率对人民币收入的影响</h3>
                <p>套保比例越高，蓝线越平缓，企业收入的不确定性越低。</p>
              </div>
              <div className="legend" aria-label="图例">
                <span><i className="line hedge" />{ratioLabel} 套保</span>
                <span><i className="line open" />不套保</span>
              </div>
            </div>
            <IncomeChart
              points={scenarios}
              selectedSpot={normalized.maturitySpot}
            />
          </div>

          <div className="explanation">
            <span className="explanation-icon">i</span>
            <div>
              <strong>如何理解当前结果</strong>
              <p>
                当到期即期汇率为 {normalized.maturitySpot.toFixed(2)} 时，
                {protectsIncome
                  ? `低于远期价 ${normalized.forwardRate.toFixed(2)}，远期套保为企业多保护约 ${wan.format(Math.abs(summary.differenceCny) / 10_000)} 万元人民币收入。`
                  : `高于远期价 ${normalized.forwardRate.toFixed(2)}，企业仍获得约 ${wan.format(summary.totalIncomeCny / 10_000)} 万元人民币收入，但相较不套保存在约 ${wan.format(Math.abs(summary.differenceCny) / 10_000)} 万元机会成本。`}
              </p>
            </div>
          </div>
        </div>
      </section>

      <TradePortfolioLab />

      <section className="comparison-section" id="strategy-comparison" hidden aria-hidden="true">
        <div className="comparison-header">
          <div>
            <p className="eyebrow">组合策略对比</p>
            <h2>同一笔敞口，不同策略会带来怎样的收入边界？</h2>
            <p>
              同时比较不套保、50%、80%、100%和当前自定义组合。每个策略由多个产品组成项汇总，未来可直接加入期权、期货和掉期。
            </p>
          </div>
          <div className="architecture-badge">
            <span>策略 = 多个产品组成项</span>
            <small>当前已接入：远期＋未套保</small>
          </div>
        </div>

        <div className="comparison-kpis">
          <article>
            <span>情景内收入最稳定</span>
            <strong>{mostStable.strategy.name}</strong>
            <small>波动区间 ¥{wan.format(mostStable.incomeRangeCny / 10_000)}万</small>
          </article>
          <article>
            <span>当前汇率下收入最高</span>
            <strong>{highestIncome.strategy.name}</strong>
            <small>到期收入 ¥{wan.format(highestIncome.selected.totalIncomeCny / 10_000)}万</small>
          </article>
          <article className="custom-kpi">
            <span>自定义组合的风险敞口</span>
            <strong>{Math.round(customComparison.selected.uncoveredRatio * 100)}%</strong>
            <small>仍随到期即期汇率变化</small>
          </article>
        </div>

        <div className="comparison-chart-card">
          <div className="chart-heading">
            <div>
              <h3>五种策略的人民币收入曲线</h3>
              <p>曲线越平，收入越稳定；曲线越陡，保留的汇率上涨机会和下跌风险越多。</p>
            </div>
            <div className="comparison-legend" aria-label="策略图例">
              {comparisonSeries.map((item) => (
                <span key={item.id} className={item.id === "custom" ? "custom" : ""}>
                  <i style={{ backgroundColor: item.color }} />{item.label}
                </span>
              ))}
            </div>
          </div>
          <StrategyComparisonChart
            series={comparisonSeries}
            selectedSpot={normalized.maturitySpot}
          />
        </div>

        <div className="comparison-table-wrap">
          <table className="comparison-table">
            <thead>
              <tr>
                <th>策略</th>
                <th>当前组成</th>
                <th>到期收入</th>
                <th>最差情景收入</th>
                <th>收入波动区间</th>
                <th>相对不套保</th>
              </tr>
            </thead>
            <tbody>
              {strategyComparisons.map((item) => {
                const coverage = Math.round(item.selected.coveredRatio * 100);
                const difference = item.selected.differenceCny;
                return (
                  <tr key={item.strategy.id} className={item.strategy.id === "custom" ? "selected-row" : ""}>
                    <th scope="row">
                      <span className="table-strategy-name">
                        <i style={{ backgroundColor: strategyColors[item.strategy.id] }} />
                        {item.strategy.name}
                      </span>
                      <small>{item.strategy.description}</small>
                    </th>
                    <td>{coverage > 0 ? `远期 ${coverage}% ＋ 未套保 ${100 - coverage}%` : "未套保 100%"}</td>
                    <td>¥{wan.format(item.selected.totalIncomeCny / 10_000)}万</td>
                    <td>¥{wan.format(item.worstIncomeCny / 10_000)}万</td>
                    <td>¥{wan.format(item.incomeRangeCny / 10_000)}万</td>
                    <td className={difference >= 0 ? "gain" : "cost"}>
                      {Math.abs(difference) < 1 ? "—" : `${difference > 0 ? "+" : "−"}¥${wan.format(Math.abs(difference) / 10_000)}万`}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="decision-explanation">
          <div>
            <span>当前情景判断</span>
            <p>
              到期即期汇率 {normalized.maturitySpot.toFixed(2)}
              {normalized.maturitySpot < normalized.forwardRate ? " 低于 " : " 高于 "}
              远期价 {normalized.forwardRate.toFixed(2)}，因此提高远期比例会
              {normalized.maturitySpot < normalized.forwardRate ? "增加当前情景下的人民币收入保护。" : "提高收入确定性，但也会增加机会成本。"}
            </p>
          </div>
          <div>
            <span>组合策略边界</span>
            <p>
              “最稳定”不等于“任何时候都最好”。后续加入期权费、掉期现金流和不同期限后，系统会先逐项计算，再汇总整套策略的成本与收益。
            </p>
          </div>
          <div>
            <span>盈亏平衡点</span>
            <p>
              对当前无成本远期案例，盈亏平衡点为 {normalized.forwardRate.toFixed(4)}。到期汇率低于该水平时套保提供保护，高于该水平时体现机会成本。
            </p>
          </div>
        </div>
      </section>

      <section className="method-section">
        <div className="method-copy">
          <p className="eyebrow">计算逻辑</p>
          <h2>一个可审计、可扩展的产品计算框架</h2>
          <p>
            每个策略先拆分为定存、掉期远端、远期结算、到期即期和期权叠加，分别计算美元名义金额、税后利息与到期现金流，再汇总为可比较的人民币结果。
          </p>
        </div>
        <div className="formula-card">
          <span>最终人民币收入</span>
          <code>Σ（各产品组成项现金流－成本）<br />＋ 未覆盖敞口 × 到期即期价</code>
        </div>
      </section>

      <section className="roadmap-section">
        <div className="roadmap-heading">
          <div>
            <p className="eyebrow">产品路线图</p>
            <h2>四类产品已经进入同一个策略框架</h2>
          </div>
          <p>产品模块相互独立，后续接入新策略时无需重写整个系统。</p>
        </div>
        <div className="roadmap-grid">
          {products.map((product, index) => (
            <article className={product.ready ? "ready" : ""} key={product.name}>
              <span>0{index + 1}</span>
              <h3>{product.name}</h3>
              <p>{index === 0 ? "结汇比例、远期汇率与开放敞口" : index === 1 ? "四类头寸、执行价、期权费与领式组合" : index === 2 ? "近端换汇与远端锁汇现金流" : "利率、税后收益与实际期限"}</p>
              <small>已接入组合实验室</small>
            </article>
          ))}
        </div>
      </section>

      <section className="sources-section">
        <div>
          <p className="eyebrow">数据与边界</p>
          <h2>可追溯的市场假设</h2>
        </div>
        <div className="source-grid">
          <article>
            <span>官方即期参考</span>
            <strong>6.7909</strong>
            <a href="https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do" target="_blank" rel="noreferrer">国家外汇管理局（SAFE）↗</a>
          </article>
          <article>
            <span>远期参考区间</span>
            <strong>6.71 — 6.77</strong>
            <small>综合交易所价格与机构预测，用于教学情景分析</small>
          </article>
          <article className="notice">
            <span>重要说明</span>
            <p>本平台当前为虚构出口企业案例，不构成银行正式报价、投资建议或对未来汇率的保证。</p>
          </article>
        </div>
      </section>

      <footer>
        <div>
          <strong>企业外汇套保与风险分析平台</strong>
          <span>项目原型 · Composite Strategy MVP</span>
        </div>
        <p>将金融逻辑转化为可解释、可扩展的软件产品。</p>
      </footer>
    </main>
  );
}
