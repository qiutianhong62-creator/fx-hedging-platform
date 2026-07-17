"use client";

import { useMemo, useRef, useState, type CSSProperties } from "react";
import { StrategyComparisonChart, type ComparisonSeries } from "./StrategyComparisonChart";
import {
  buildPortfolioScenarios,
  calculatePortfolioPayoffCny,
  calculateTradePayoffCny,
  createPortfolioTrade,
  defaultPortfolioTrades,
  productColors,
  productLabels,
  tradeMatchesAnalysis,
  tradeDescription,
  usdNotional,
  type PortfolioTrade,
  type TradeProduct,
} from "../lib/strategies/portfolio";

const money = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

type NumberFieldProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  suffix?: string;
};

function NumberField({ label, value, onChange, step = 0.0001, suffix }: NumberFieldProps) {
  return (
    <label className="trade-field">
      <span>{label}</span>
      <div>
        <input type="number" min="0" step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />
        {suffix ? <small>{suffix}</small> : null}
      </div>
    </label>
  );
}

function signedMoney(value: number) {
  const sign = value > 0.005 ? "+" : value < -0.005 ? "−" : "";
  return `${sign}¥${money.format(Math.abs(value))}`;
}

export function TradePortfolioLab() {
  const [trades, setTrades] = useState<PortfolioTrade[]>(defaultPortfolioTrades);
  const [analysisDate, setAnalysisDate] = useState("2026-12-31");
  const [referenceSpot, setReferenceSpot] = useState(6.80);
  const [selectedSpot, setSelectedSpot] = useState(6.60);
  const [scenarioMin, setScenarioMin] = useState(6.40);
  const [scenarioMax, setScenarioMax] = useState(7.10);
  const [showLegs, setShowLegs] = useState(true);
  const nextId = useRef(3);

  const minimum = Math.min(scenarioMin, scenarioMax - 0.01);
  const maximum = Math.max(scenarioMax, minimum + 0.01);
  const selected = Math.min(maximum, Math.max(minimum, selectedSpot));
  const context = useMemo(() => ({ analysisDate, referenceSpot: Math.max(0.0001, referenceSpot) }), [analysisDate, referenceSpot]);
  const includedTrades = trades.filter((trade) => tradeMatchesAnalysis(trade, context));
  const excludedCount = trades.filter((trade) => trade.enabled && trade.maturityDate !== analysisDate).length;
  const invalidSwapCount = trades.filter(
    (trade) => trade.enabled && trade.product === "swap" && trade.nearDate >= trade.maturityDate,
  ).length;

  const totalPayoff = useMemo(
    () => calculatePortfolioPayoffCny(trades, selected, context),
    [context, selected, trades],
  );

  const totalSeries = useMemo(
    () => buildPortfolioScenarios(trades, context, minimum, maximum),
    [context, maximum, minimum, trades],
  );

  const series = useMemo<ComparisonSeries[]>(() => {
    const items: ComparisonSeries[] = [
      {
        id: "portfolio-total",
        label: "组合总损益",
        color: "#17374f",
        points: totalSeries,
        emphasized: true,
      },
      {
        id: "zero-line",
        label: "盈亏平衡线",
        color: "#98a5a1",
        dashed: true,
        points: totalSeries.map((point) => ({ ...point, incomeCny: 0, differenceCny: 0 })),
      },
    ];
    if (showLegs) {
      includedTrades.forEach((trade, index) => {
        items.push({
          id: trade.id,
          label: `${index + 1}. ${trade.name}`,
          color: productColors[trade.product],
          points: buildPortfolioScenarios([trade], context, minimum, maximum),
        });
      });
    }
    return items;
  }, [context, includedTrades, maximum, minimum, showLegs, totalSeries]);

  const payoffs = totalSeries.map((point) => point.incomeCny);
  const bestPayoff = Math.max(...payoffs);
  const worstPayoff = Math.min(...payoffs);

  const updateTrade = (id: string, patch: Partial<PortfolioTrade>) => {
    setTrades((current) => current.map((trade) => trade.id === id ? { ...trade, ...patch } : trade));
  };

  const changeProduct = (trade: PortfolioTrade, product: TradeProduct) => {
    updateTrade(trade.id, { product });
  };

  const addTrade = (product: TradeProduct) => {
    const id = `trade-${product}-${nextId.current}`;
    nextId.current += 1;
    setTrades((current) => [...current, createPortfolioTrade(product, id, analysisDate)]);
  };

  return (
    <section className="comparison-section portfolio-lab" id="trade-builder">
      <div className="comparison-header">
        <div>
          <p className="eyebrow">自由交易搭建器</p>
          <h2>你来选择每一笔交易，网站只负责合并成一条收益曲线。</h2>
          <p>没有预设策略。你可以自由添加远期、期权、掉期和定存，分别填写金额、方向、价格与到期日，再查看整个组合在不同到期汇率下的损益。</p>
        </div>
        <div className="architecture-badge">
          <span>组合损益 = Σ 每笔交易损益</span>
          <small>金额独立 · 参数独立 · 产品可混搭</small>
        </div>
      </div>

      <div className="portfolio-scenario-card">
        <div className="portfolio-scenario-heading">
          <div>
            <strong>统一分析条件</strong>
            <small>曲线只汇总与分析到期日一致且已启用的交易；掉期以远端日期作为分析到期日</small>
          </div>
          <label className="show-legs-toggle">
            <input type="checkbox" checked={showLegs} onChange={(event) => setShowLegs(event.target.checked)} />
            同时显示每笔交易
          </label>
        </div>
        <div className="portfolio-scenario-grid">
          <label className="trade-field">
            <span>分析到期日</span>
            <div><input type="date" value={analysisDate} onChange={(event) => setAnalysisDate(event.target.value)} /></div>
          </label>
          <NumberField label="参考即期汇率" value={referenceSpot} onChange={setReferenceSpot} />
          <NumberField label="当前观察汇率" value={selectedSpot} onChange={setSelectedSpot} />
          <NumberField label="情景下限" value={scenarioMin} onChange={setScenarioMin} />
          <NumberField label="情景上限" value={scenarioMax} onChange={setScenarioMax} />
        </div>
        {excludedCount > 0 ? <p className="portfolio-warning">有 {excludedCount} 笔已启用交易的到期日不同，暂未计入当前曲线。</p> : null}
        {invalidSwapCount > 0 ? <p className="portfolio-warning">有 {invalidSwapCount} 笔掉期的近端日期不早于远端日期，请调整后再计入曲线。</p> : null}
        <p className="portfolio-rule">切换产品时，交易名称、金额、币种和日期不会被清空。掉期近端与远端方向自动相反，组合分析以远端日期为准。</p>
      </div>

      <div className="trade-list-heading">
        <div>
          <span>你的交易清单</span>
          <strong>{includedTrades.length} 笔计入当前组合</strong>
        </div>
        <div className="add-trade-buttons" aria-label="添加交易">
          {(Object.keys(productLabels) as TradeProduct[]).map((product) => (
            <button key={product} type="button" onClick={() => addTrade(product)}>＋{productLabels[product]}</button>
          ))}
        </div>
      </div>

      <div className="trade-list">
        {trades.map((trade, index) => {
          const payoff = calculateTradePayoffCny(trade, selected, context);
          const included = tradeMatchesAnalysis(trade, context);
          return (
            <article className={`trade-card ${included ? "included" : "excluded"}`} key={trade.id} style={{ "--trade-color": productColors[trade.product] } as CSSProperties}>
              <div className="trade-color-bar" />
              <div className="trade-card-header">
                <span className="trade-number">交易 {index + 1}</span>
                <div className="trade-card-actions">
                  <label><input type="checkbox" checked={trade.enabled} onChange={(event) => updateTrade(trade.id, { enabled: event.target.checked })} />启用</label>
                  <button type="button" onClick={() => setTrades((current) => current.filter((item) => item.id !== trade.id))}>删除</button>
                </div>
              </div>

              <div className="trade-identity-grid">
                <label className="trade-name-field">
                  <span>交易名称</span>
                  <input value={trade.name} onChange={(event) => updateTrade(trade.id, { name: event.target.value })} />
                </label>
                <label className="trade-select-field">
                  <span>产品</span>
                  <select value={trade.product} onChange={(event) => changeProduct(trade, event.target.value as TradeProduct)}>
                    {(Object.keys(productLabels) as TradeProduct[]).map((product) => <option key={product} value={product}>{productLabels[product]}</option>)}
                  </select>
                </label>
              </div>

              <div className="trade-input-grid">
                <NumberField label="名义金额" value={trade.notional} step={1000} onChange={(value) => updateTrade(trade.id, { notional: value })} />
                <label className="trade-select-field">
                  <span>金额币种</span>
                  <select value={trade.notionalCurrency} onChange={(event) => updateTrade(trade.id, { notionalCurrency: event.target.value as PortfolioTrade["notionalCurrency"] })}>
                    <option value="CNY">人民币 CNY</option>
                    <option value="USD">美元 USD</option>
                  </select>
                </label>
                <label className="trade-field">
                  <span>{trade.product === "swap" ? "远端日期（分析到期日）" : "到期日"}</span>
                  <div><input type="date" value={trade.maturityDate} onChange={(event) => updateTrade(trade.id, { maturityDate: event.target.value })} /></div>
                </label>

                {trade.product === "forward" ? (
                  <>
                    <label className="trade-select-field">
                      <span>远期方向</span>
                      <select value={trade.direction} onChange={(event) => updateTrade(trade.id, { direction: event.target.value as PortfolioTrade["direction"] })}>
                        <option value="buyUsd">远期购汇</option>
                        <option value="sellUsd">远期结汇</option>
                      </select>
                    </label>
                    <NumberField label="远期汇率" value={trade.contractRate} onChange={(value) => updateTrade(trade.id, { contractRate: value })} />
                  </>
                ) : null}

                {trade.product === "swap" ? (
                  <>
                    <label className="trade-field">
                      <span>近端日期</span>
                      <div><input type="date" value={trade.nearDate} onChange={(event) => updateTrade(trade.id, { nearDate: event.target.value })} /></div>
                    </label>
                    <label className="trade-select-field">
                      <span>近端方向</span>
                      <select value={trade.direction} onChange={(event) => updateTrade(trade.id, { direction: event.target.value as PortfolioTrade["direction"] })}>
                        <option value="buyUsd">近端购汇</option>
                        <option value="sellUsd">近端结汇</option>
                      </select>
                    </label>
                    <NumberField label="近端汇率" value={trade.nearRate} onChange={(value) => updateTrade(trade.id, { nearRate: value })} />
                    <label className="trade-readonly-field">
                      <span>远端方向（自动相反）</span>
                      <div>{trade.direction === "buyUsd" ? "远端结汇" : "远端购汇"}</div>
                    </label>
                    <NumberField label="远端汇率" value={trade.contractRate} onChange={(value) => updateTrade(trade.id, { contractRate: value })} />
                  </>
                ) : null}

                {trade.product === "option" ? (
                  <>
                    <label className="trade-select-field">
                      <span>买卖方向</span>
                      <select value={trade.optionPosition} onChange={(event) => updateTrade(trade.id, { optionPosition: event.target.value as PortfolioTrade["optionPosition"] })}>
                        <option value="buy">买入期权</option>
                        <option value="sell">卖出期权</option>
                      </select>
                    </label>
                    <label className="trade-select-field">
                      <span>期权类型</span>
                      <select value={trade.optionKind} onChange={(event) => updateTrade(trade.id, { optionKind: event.target.value as PortfolioTrade["optionKind"] })}>
                        <option value="call">看涨期权</option>
                        <option value="put">看跌期权</option>
                      </select>
                    </label>
                    <NumberField label="执行价" value={trade.strike} onChange={(value) => updateTrade(trade.id, { strike: value })} />
                    <NumberField label="期权费" value={trade.premium} onChange={(value) => updateTrade(trade.id, { premium: value })} suffix="CNY/USD" />
                  </>
                ) : null}

                {trade.product === "deposit" ? (
                  <>
                    <NumberField label="存款年利率" value={trade.annualRate * 100} step={0.01} onChange={(value) => updateTrade(trade.id, { annualRate: value / 100 })} suffix="%" />
                    <NumberField label="利息税率" value={trade.taxRate * 100} step={1} onChange={(value) => updateTrade(trade.id, { taxRate: value / 100 })} suffix="%" />
                    <NumberField label="计息天数" value={trade.dayCount} step={1} onChange={(value) => updateTrade(trade.id, { dayCount: value })} suffix="天" />
                  </>
                ) : null}
              </div>

              <div className="trade-card-footer">
                <div>
                  <span>{tradeDescription(trade)}</span>
                  {trade.product !== "deposit" && trade.notionalCurrency === "CNY" ? <small>折算美元名义本金约 ${money.format(usdNotional(trade))}</small> : null}
                </div>
                <div className={payoff >= 0 ? "trade-payoff gain" : "trade-payoff loss"}>
                  <span>{included ? `汇率 ${selected.toFixed(4)} 时` : trade.product === "swap" && trade.nearDate >= trade.maturityDate ? "近端日期应早于远端" : "未计入当前曲线"}</span>
                  <strong>{included ? signedMoney(payoff) : "—"}</strong>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <div className="portfolio-result-grid">
        <article className="portfolio-result primary">
          <span>当前观察汇率下组合损益</span>
          <strong className={totalPayoff >= 0 ? "gain" : "loss"}>{signedMoney(totalPayoff)}</strong>
          <small>到期即期汇率 {selected.toFixed(4)}</small>
        </article>
        <article className="portfolio-result">
          <span>情景内最差结果</span>
          <strong>{signedMoney(worstPayoff)}</strong>
          <small>情景区间 {minimum.toFixed(2)}–{maximum.toFixed(2)}</small>
        </article>
        <article className="portfolio-result">
          <span>情景内最好结果</span>
          <strong>{signedMoney(bestPayoff)}</strong>
          <small>不代表收益预测</small>
        </article>
      </div>

      <div className="comparison-chart-card portfolio-chart-card">
        <div className="chart-heading">
          <div>
            <h3>自选产品组合的到期损益曲线</h3>
            <p>深色粗线是所有已计入交易的合计；彩色细线是每一笔交易对组合的贡献。</p>
          </div>
          <div className="portfolio-legend" aria-label="曲线图例">
            {series.map((item) => <span key={item.id}><i style={{ backgroundColor: item.color }} />{item.label}</span>)}
          </div>
        </div>
        <StrategyComparisonChart
          series={series}
          selectedSpot={selected}
          yAxisLabel="组合到期损益（万元）"
          ariaLabel="用户自由选择的多笔外汇交易组合到期损益曲线"
        />
      </div>

      <div className="portfolio-method-note">
        <strong>当前示例为什么会形成这条线？</strong>
        <p>远期购汇在美元升值时产生正损益、美元贬值时产生负损益；卖出看涨期权先收取期权费，但当汇率高于执行价后需要承担期权赔付。两笔交易逐点相加，就是深色的组合总损益线。</p>
      </div>
    </section>
  );
}
