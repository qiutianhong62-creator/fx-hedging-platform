"use client";

import { useState } from "react";

import type { AutomaticForwardProbabilityResponse, ResultKind } from "../../lib/api/forwardProbability.ts";
import { exposureCopy, improvementRange, signedCnyRange } from "../../lib/analysis/exposurePresentation.ts";
import {
  allProbabilityRows,
  formatCnyWan,
  formatFullCny,
  formatProbability,
  formatSpot,
  selectCoreIntervals,
  type ProbabilityTableRow,
} from "../../lib/analysis/probabilityDashboard.ts";

type ResponseProps = { response: AutomaticForwardProbabilityResponse };

function amountRange(minimum: number, maximum: number) {
  return (
    <span title={`${formatFullCny(minimum)} 至 ${formatFullCny(maximum)}`}>
      {formatCnyWan(minimum)} – {formatCnyWan(maximum)}
    </span>
  );
}

function differenceRange(rawMinimum: number, rawMaximum: number, kind: ResultKind) {
  const { minimum_amount_cny: minimum, maximum_amount_cny: maximum } = improvementRange(
    { minimum_amount_cny: rawMinimum, maximum_amount_cny: rawMaximum }, kind,
  );
  const className =
    minimum >= 0
      ? "difference-positive"
      : maximum <= 0
        ? "difference-negative"
        : "difference-mixed";
  return (
    <span className={className} title={`${formatFullCny(minimum)} 至 ${formatFullCny(maximum)}`}>
      {signedCnyRange(minimum, maximum)}
    </span>
  );
}

function rowKey(row: ProbabilityTableRow): string {
  return row.kind === "core"
    ? `core-${row.interval.lower_spot}-${row.interval.upper_spot}`
    : `${row.kind}-${row.boundarySpot}`;
}

function ProbabilityTableRowView({ row, kind }: { row: ProbabilityTableRow; kind: ResultKind }) {
  if (row.kind !== "core") {
    const difference = row.forwardBoundaryCny - row.noHedgeBoundaryCny;
    return (
      <tr className="tail-row">
        <th scope="row">
          {row.direction === "below" ? "低于" : "高于"} {formatSpot(row.boundarySpot)}
        </th>
        <td>{formatProbability(row.probability)}</td>
        <td>极端尾部</td>
        <td title={formatFullCny(row.noHedgeBoundaryCny)}>{formatCnyWan(row.noHedgeBoundaryCny)}（边界）</td>
        <td title={formatFullCny(row.forwardBoundaryCny)}>{formatCnyWan(row.forwardBoundaryCny)}（边界）</td>
        <td>{differenceRange(difference, difference, kind)}（边界差额）</td>
      </tr>
    );
  }

  const { interval } = row;
  return (
    <tr>
      <th scope="row">{formatSpot(interval.lower_spot)} – {formatSpot(interval.upper_spot)}</th>
      <td>{formatProbability(interval.interval_probability)}</td>
      <td>低于上界 {formatProbability(interval.probability_below_upper)}</td>
      <td>{amountRange(interval.no_hedge.minimum_amount_cny, interval.no_hedge.maximum_amount_cny)}</td>
      <td>{amountRange(interval.forward_strategy.minimum_amount_cny, interval.forward_strategy.maximum_amount_cny)}</td>
      <td>{differenceRange(interval.strategy_minus_no_hedge.minimum_amount_cny, interval.strategy_minus_no_hedge.maximum_amount_cny, kind)}</td>
    </tr>
  );
}

export function ProbabilityComparisonTable({ response }: ResponseProps) {
  const copy = exposureCopy(response.result_kind);
  const [expanded, setExpanded] = useState(false);
  const rows: ProbabilityTableRow[] = expanded
    ? allProbabilityRows(response.probability_profile)
    : selectCoreIntervals(response.probability_profile.intervals).map(
        (interval) => ({ kind: "core" as const, interval }),
      );

  return (
    <section className="result-section" aria-labelledby="probability-table-title">
      <div className="result-heading table-heading">
        <div>
          <p className="section-kicker">概率明细</p>
          <h2 id="probability-table-title">汇率区间与人民币{copy.amount}对比</h2>
          <p>
            {expanded
              ? "完整分布包含20个核心区间和两个极端尾部。"
              : "默认显示概率最高的8个区间，并按汇率从低到高排列。"}
          </p>
        </div>
        <button
          className="secondary-button"
          type="button"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "收起完整分布" : "查看完整分布"}
        </button>
      </div>
      <div className="probability-table-scroll">
        <table className="probability-table">
          <caption>不套保与远期策略在同一到期汇率区间下的结果</caption>
          <thead>
            <tr>
              <th>到期汇率区间</th>
              <th>发生概率</th>
              <th>累计概率</th>
              <th>不套保{copy.amount}</th>
              <th>远期策略{copy.amount}</th>
              <th>{copy.improvement}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ProbabilityTableRowView key={rowKey(row)} row={row} kind={response.result_kind} />
            ))}
          </tbody>
        </table>
      </div>
      <p className="table-footnote">
        {copy.differenceNote}
      </p>
    </section>
  );
}
