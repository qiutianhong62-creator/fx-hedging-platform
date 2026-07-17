"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { StrategyComparisonChart, type ComparisonSeries } from "./StrategyComparisonChart";
import {
  buildMultiProductScenarios,
  calculateMultiProductScheme,
  optionLegLabels,
  type MultiProductScheme,
  type MultiStrategyCommonInput,
  type OptionLeg,
  type SettlementAllocation,
} from "../lib/strategies/multi";

const money = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
const wan = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const defaultSchemes: MultiProductScheme[] = [
  {
    id: "open-deposit",
    name: "美元定存后全部开放",
    enabled: true,
    color: "#1f5f82",
    depositRate: 0.0398,
    taxRate: 0.1,
    principal: { swapRatio: 0, swapRate: 6.799, forwardRatio: 0, forwardRate: 6.7951 },
    interest: { swapRatio: 0, swapRate: 6.799, forwardRatio: 0, forwardRate: 6.7951 },
    optionLegs: [
      { target: "principal", type: "disabled", coverageRatio: 0, strikeRate: 6.65, premiumRate: 0.035 },
      { target: "principal", type: "disabled", coverageRatio: 0, strikeRate: 6.9, premiumRate: 0.025 },
    ],
  },
  {
    id: "swap-deposit",
    name: "掉期＋定存锁汇",
    enabled: true,
    color: "#e5824f",
    depositRate: 0.0398,
    taxRate: 0.1,
    principal: { swapRatio: 1, swapRate: 6.799, forwardRatio: 0, forwardRate: 6.7951 },
    interest: { swapRatio: 0, swapRate: 6.799, forwardRatio: 1, forwardRate: 6.7951 },
    optionLegs: [
      { target: "principal", type: "disabled", coverageRatio: 0, strikeRate: 6.65, premiumRate: 0.035 },
      { target: "principal", type: "disabled", coverageRatio: 0, strikeRate: 6.9, premiumRate: 0.025 },
    ],
  },
  {
    id: "collar-deposit",
    name: "定存＋领式期权",
    enabled: true,
    color: "#087f73",
    depositRate: 0.0398,
    taxRate: 0.1,
    principal: { swapRatio: 0, swapRate: 6.799, forwardRatio: 0, forwardRate: 6.7951 },
    interest: { swapRatio: 0, swapRate: 6.799, forwardRatio: 0, forwardRate: 6.7951 },
    optionLegs: [
      { target: "principal", type: "buyPut", coverageRatio: 1, strikeRate: 6.65, premiumRate: 0.035 },
      { target: "principal", type: "sellCall", coverageRatio: 1, strikeRate: 6.9, premiumRate: 0.025 },
    ],
  },
];

function clampNumber(value: number, fallback: number, minimum = 0) {
  return Math.max(minimum, Number.isFinite(value) ? value : fallback);
}

type NumericFieldProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  step?: number;
  suffix?: string;
};

function NumericField({ label, value, onChange, step = 0.0001, suffix }: NumericFieldProps) {
  return (
    <label className="compact-field">
      <span>{label}</span>
      <div>
        <input
          type="number"
          step={step}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {suffix ? <small>{suffix}</small> : null}
      </div>
    </label>
  );
}

type AllocationEditorProps = {
  title: string;
  value: SettlementAllocation;
  onChange: (value: Partial<SettlementAllocation>) => void;
};

function AllocationEditor({ title, value, onChange }: AllocationEditorProps) {
  const spotRatio = 1 - value.swapRatio - value.forwardRatio;
  return (
    <div className="allocation-editor">
      <div className="allocation-heading">
        <strong>{title}</strong>
        <span className={spotRatio < 0 ? "ratio-error" : ""}>
          到期即期 {Math.round(spotRatio * 100)}%
        </span>
      </div>
      <div className="mini-grid four">
        <NumericField
          label="掉期远端比例"
          value={Math.round(value.swapRatio * 100)}
          step={1}
          suffix="%"
          onChange={(next) => onChange({ swapRatio: next / 100 })}
        />
        <NumericField label="掉期远端汇率" value={value.swapRate} onChange={(next) => onChange({ swapRate: next })} />
        <NumericField
          label="远期比例"
          value={Math.round(value.forwardRatio * 100)}
          step={1}
          suffix="%"
          onChange={(next) => onChange({ forwardRatio: next / 100 })}
        />
        <NumericField label="远期汇率" value={value.forwardRate} onChange={(next) => onChange({ forwardRate: next })} />
      </div>
    </div>
  );
}

type OptionEditorProps = {
  index: number;
  value: OptionLeg;
  onChange: (value: Partial<OptionLeg>) => void;
};

function OptionEditor({ index, value, onChange }: OptionEditorProps) {
  return (
    <div className="option-editor">
      <strong>期权腿 {index + 1}</strong>
      <label>
        <span>目标现金流</span>
        <select value={value.target} onChange={(event) => onChange({ target: event.target.value as OptionLeg["target"] })}>
          <option value="principal">本金</option>
          <option value="interest">定存利息</option>
        </select>
      </label>
      <label>
        <span>期权头寸</span>
        <select value={value.type} onChange={(event) => onChange({ type: event.target.value as OptionLeg["type"] })}>
          {Object.entries(optionLegLabels).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <NumericField
        label="名义覆盖率"
        value={Math.round(value.coverageRatio * 100)}
        step={1}
        suffix="%"
        onChange={(next) => onChange({ coverageRatio: next / 100 })}
      />
      <NumericField label="执行价" value={value.strikeRate} onChange={(next) => onChange({ strikeRate: next })} />
      <NumericField label="期权费率" value={value.premiumRate} onChange={(next) => onChange({ premiumRate: next })} />
    </div>
  );
}

export function MultiStrategyLab() {
  const [initialCny, setInitialCny] = useState(238_000_000);
  const [nearSpot, setNearSpot] = useState(6.8037);
  const [tenorDays, setTenorDays] = useState(14);
  const [annualBasis, setAnnualBasis] = useState(360);
  const [maturitySpot, setMaturitySpot] = useState(6.6);
  const [scenarioMin, setScenarioMin] = useState(6.4);
  const [scenarioMax, setScenarioMax] = useState(7.1);
  const [schemes, setSchemes] = useState(defaultSchemes);

  const common = useMemo<MultiStrategyCommonInput>(() => {
    const minimum = Math.min(scenarioMin, scenarioMax - 0.01);
    const maximum = Math.max(scenarioMax, minimum + 0.01);
    return {
      initialCny: clampNumber(initialCny, 0),
      nearSpot: clampNumber(nearSpot, 6.8037, 0.0001),
      tenorDays: clampNumber(tenorDays, 14),
      annualBasis: clampNumber(annualBasis, 360, 1),
      maturitySpot: Math.min(maximum, Math.max(minimum, clampNumber(maturitySpot, 6.6, 0.0001))),
    };
  }, [annualBasis, initialCny, maturitySpot, nearSpot, scenarioMax, scenarioMin, tenorDays]);

  const minimum = Math.min(scenarioMin, scenarioMax - 0.01);
  const maximum = Math.max(scenarioMax, minimum + 0.01);

  const results = useMemo(
    () => schemes.map((scheme) => ({ scheme, result: calculateMultiProductScheme(common, scheme) })),
    [common, schemes],
  );

  const series = useMemo<ComparisonSeries[]>(() => {
    const active = schemes
      .filter((scheme) => scheme.enabled)
      .map((scheme) => ({
        id: scheme.id,
        label: scheme.name,
        color: scheme.color,
        points: buildMultiProductScenarios(common, scheme, minimum, maximum, 31),
        emphasized: scheme.id === "collar-deposit",
      }));
    active.push({
      id: "keep-cny",
      label: "保留人民币不操作",
      color: "#8b9995",
      points: Array.from({ length: 31 }, (_, index) => ({
        spot: minimum + ((maximum - minimum) * index) / 30,
        incomeCny: common.initialCny,
        differenceCny: 0,
      })),
      emphasized: false,
    });
    return active;
  }, [common, maximum, minimum, schemes]);

  const updateScheme = (id: string, patch: Partial<MultiProductScheme>) => {
    setSchemes((current) => current.map((scheme) => scheme.id === id ? { ...scheme, ...patch } : scheme));
  };

  const updateAllocation = (
    id: string,
    target: "principal" | "interest",
    patch: Partial<SettlementAllocation>,
  ) => {
    setSchemes((current) => current.map((scheme) => scheme.id === id
      ? { ...scheme, [target]: { ...scheme[target], ...patch } }
      : scheme));
  };

  const updateOption = (id: string, index: number, patch: Partial<OptionLeg>) => {
    setSchemes((current) => current.map((scheme) => {
      if (scheme.id !== id) return scheme;
      const optionLegs = scheme.optionLegs.map((leg, legIndex) => legIndex === index ? { ...leg, ...patch } : leg) as [OptionLeg, OptionLeg];
      return { ...scheme, optionLegs };
    }));
  };

  return (
    <section className="comparison-section multi-lab" id="multi-strategy">
      <div className="comparison-header">
        <div>
          <p className="eyebrow">多产品组合实验室</p>
          <h2>把你的三个策略，放进同一张收益图。</h2>
          <p>统一资金、期限和市场情景，再分别调整远期、掉期、定存和期权。所有比例与价格变化都会立即反映到曲线上。</p>
        </div>
        <div className="architecture-badge">
          <span>策略 = 基础结算＋期权叠加</span>
          <small>远期 · 掉期 · 期权 · 定存均已接入</small>
        </div>
      </div>

      <div className="common-parameter-card">
        <div className="common-parameter-heading">
          <div>
            <span className="step">01</span>
            <strong>统一业务起点</strong>
          </div>
          <small>三个方案共用，保证比较公平</small>
        </div>
        <div className="common-input-grid">
          <NumericField label="初始人民币资金" value={initialCny} step={1_000_000} suffix="CNY" onChange={setInitialCny} />
          <NumericField label="近端即期汇率" value={nearSpot} suffix="CNY/USD" onChange={setNearSpot} />
          <NumericField label="期限" value={tenorDays} step={1} suffix="天" onChange={setTenorDays} />
          <NumericField label="年化天数基础" value={annualBasis} step={1} suffix="天" onChange={setAnnualBasis} />
          <NumericField label="观察的到期即期" value={maturitySpot} step={0.01} suffix="CNY/USD" onChange={setMaturitySpot} />
          <div className="scenario-pair">
            <NumericField label="情景下限" value={scenarioMin} step={0.05} onChange={setScenarioMin} />
            <NumericField label="情景上限" value={scenarioMax} step={0.05} onChange={setScenarioMax} />
          </div>
        </div>
      </div>

      <div className="scheme-grid">
        {results.map(({ scheme, result }, schemeIndex) => (
          <article className={`scheme-card ${scheme.enabled ? "enabled" : "disabled"}`} key={scheme.id} style={{ "--scheme-color": scheme.color } as CSSProperties}>
            <div className="scheme-topline" />
            <div className="scheme-card-header">
              <span className="scheme-index">方案 {String.fromCharCode(65 + schemeIndex)}</span>
              <label className="switch-label">
                <input type="checkbox" checked={scheme.enabled} onChange={(event) => updateScheme(scheme.id, { enabled: event.target.checked })} />
                <span>{scheme.enabled ? "参与比较" : "已关闭"}</span>
              </label>
            </div>
            <input
              className="scheme-name-input"
              aria-label={`方案 ${String.fromCharCode(65 + schemeIndex)} 名称`}
              value={scheme.name}
              onChange={(event) => updateScheme(scheme.id, { name: event.target.value })}
            />
            <div className="scheme-result">
              <div><span>到期人民币</span><strong>¥{wan.format(result.totalCny / 10_000)}万</strong></div>
              <div><span>策略净收益</span><strong className={result.netGainCny >= 0 ? "gain" : "cost"}>{result.netGainCny >= 0 ? "+" : "−"}¥{wan.format(Math.abs(result.netGainCny) / 10_000)}万</strong></div>
            </div>
            <div className="scheme-status-row">
              <span className={result.status === "PASS" ? "pass-chip" : "review-chip"}>{result.status === "PASS" ? "配置有效" : "需要复核"}</span>
              <small>开放本金 {Math.round(Math.max(0, result.principalSpotRatio) * 100)}%</small>
            </div>
            {result.messages.length > 0 ? <p className="scheme-warning">{result.messages[0]}</p> : null}

            <details className="scheme-details">
              <summary>编辑这个方案的产品参数</summary>
              <div className="detail-group">
                <h4>美元定存</h4>
                <div className="mini-grid two">
                  <NumericField label="年化利率" value={Number((scheme.depositRate * 100).toFixed(3))} step={0.1} suffix="%" onChange={(next) => updateScheme(scheme.id, { depositRate: next / 100 })} />
                  <NumericField label="利息税率" value={Number((scheme.taxRate * 100).toFixed(2))} step={1} suffix="%" onChange={(next) => updateScheme(scheme.id, { taxRate: next / 100 })} />
                </div>
                <small className="calculated-note">税后利息 ${money.format(result.afterTaxInterestUsd)}</small>
              </div>
              <AllocationEditor title="美元本金的到期结算" value={scheme.principal} onChange={(patch) => updateAllocation(scheme.id, "principal", patch)} />
              <AllocationEditor title="定存利息的到期结算" value={scheme.interest} onChange={(patch) => updateAllocation(scheme.id, "interest", patch)} />
              <div className="detail-group">
                <h4>期权叠加</h4>
                <p className="group-help">名义覆盖率不是资金投入比例；领式可用“买入看跌＋卖出看涨”构成。</p>
                {scheme.optionLegs.map((leg, index) => <OptionEditor key={index} index={index} value={leg} onChange={(patch) => updateOption(scheme.id, index, patch)} />)}
              </div>
            </details>
          </article>
        ))}
      </div>

      <div className="comparison-chart-card multi-chart-card">
        <div className="chart-heading">
          <div>
            <h3>同一起点下的多策略到期人民币结果</h3>
            <p>曲线越平，结果越稳定；折线的拐点通常来自期权执行价。</p>
          </div>
          <div className="comparison-legend" aria-label="多方案图例">
            {series.map((item) => <span key={item.id}><i style={{ backgroundColor: item.color }} />{item.label}</span>)}
          </div>
        </div>
        <StrategyComparisonChart series={series} selectedSpot={common.maturitySpot} />
      </div>

      <div className="comparison-table-wrap">
        <table className="comparison-table multi-result-table">
          <thead>
            <tr><th>方案</th><th>到期人民币</th><th>策略净收益</th><th>综合年化收益</th><th>开放本金</th><th>期权净现金流</th><th>状态</th></tr>
          </thead>
          <tbody>
            {results.filter(({ scheme }) => scheme.enabled).map(({ scheme, result }) => (
              <tr key={scheme.id}>
                <th scope="row"><span className="table-strategy-name"><i style={{ backgroundColor: scheme.color }} />{scheme.name}</span></th>
                <td>¥{wan.format(result.totalCny / 10_000)}万</td>
                <td className={result.netGainCny >= 0 ? "gain" : "cost"}>{result.netGainCny >= 0 ? "+" : "−"}¥{wan.format(Math.abs(result.netGainCny) / 10_000)}万</td>
                <td>{(result.annualizedReturn * 100).toFixed(2)}%</td>
                <td>{Math.round(Math.max(0, result.principalSpotRatio) * 100)}%</td>
                <td>{result.optionCashflowCny >= 0 ? "+" : "−"}¥{wan.format(Math.abs(result.optionCashflowCny) / 10_000)}万</td>
                <td><span className={result.status === "PASS" ? "pass-chip" : "review-chip"}>{result.status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="decision-explanation">
        <div><span>基础结算</span><p>本金和利息分别在掉期远端、远期和到期即期之间分配，三者自动合计为100%。</p></div>
        <div><span>期权叠加</span><p>期权只覆盖仍按到期即期结算的开放现金流，因此不会与已锁定部分重复计算。</p></div>
        <div><span>比较边界</span><p>这里比较的是同一笔人民币资金在相同期限内的结果；示例参数用于模型演示，不代表银行实时报价。</p></div>
      </div>
    </section>
  );
}
