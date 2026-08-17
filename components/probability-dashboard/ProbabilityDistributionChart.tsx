import type { AutomaticForwardProbabilityResponse } from "../../lib/api/forwardProbability.ts";
import {
  formatProbability,
  formatSpot,
  mostLikelyInterval,
} from "../../lib/analysis/probabilityDashboard.ts";

type ResponseProps = { response: AutomaticForwardProbabilityResponse };

export function ProbabilityDistributionChart({ response }: ResponseProps) {
  const intervals = response.probability_profile.intervals;
  const mostLikely = mostLikelyInterval(intervals);
  const width = 960;
  const height = 320;
  const margin = { top: 36, right: 24, bottom: 54, left: 58 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const maximumProbability = Math.max(
    ...intervals.map((interval) => interval.interval_probability),
  );
  const barWidth = plotWidth / intervals.length;
  const coreLower = response.probability_profile.core_lower_spot;
  const coreUpper = response.probability_profile.core_upper_spot;
  const spotX = (spot: number) =>
    margin.left + ((spot - coreLower) / (coreUpper - coreLower)) * plotWidth;
  const tickIndexes = [0, 5, 10, 15, 20];
  const expectedX = spotX(response.distribution.assumed_expected_maturity_spot);
  const range50 = response.distribution.typical_spot_range_50;
  const range90 = response.distribution.wide_spot_range_90;

  return (
    <section className="result-section probability-chart" aria-labelledby="distribution-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">图形辅助</p>
          <h2 id="distribution-title">到期汇率概率分布</h2>
          <p>概率分布图作为表格的辅助说明；精确金额和概率请以表格为准。</p>
        </div>
      </div>
      <div className="probability-chart-scroll">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`最高概率区间为${formatSpot(mostLikely.lower_spot)}至${formatSpot(mostLikely.upper_spot)}，发生概率${formatProbability(mostLikely.interval_probability)}`}
        >
          <line className="chart-axis" x1={margin.left} x2={margin.left} y1={margin.top} y2={margin.top + plotHeight} />
          <line className="chart-axis" x1={margin.left} x2={margin.left + plotWidth} y1={margin.top + plotHeight} y2={margin.top + plotHeight} />
          <text className="axis-label" transform={`translate(17 ${margin.top + plotHeight / 2}) rotate(-90)`}>区间发生概率</text>
          {intervals.map((interval, index) => {
            const barHeight =
              (interval.interval_probability / maximumProbability) * plotHeight;
            const isMostLikely = interval === mostLikely;
            return (
              <rect
                className={isMostLikely ? "most-likely" : undefined}
                key={interval.lower_spot}
                x={margin.left + index * barWidth + 1}
                y={margin.top + plotHeight - barHeight}
                width={Math.max(1, barWidth - 2)}
                height={barHeight}
              >
                <title>{formatSpot(interval.lower_spot)}–{formatSpot(interval.upper_spot)}：{formatProbability(interval.interval_probability)}</title>
              </rect>
            );
          })}
          {tickIndexes.map((index) => {
            const spot = coreLower + ((coreUpper - coreLower) * index) / 20;
            return (
              <g key={index}>
                <line className="chart-tick" x1={spotX(spot)} x2={spotX(spot)} y1={margin.top + plotHeight} y2={margin.top + plotHeight + 6} />
                <text className="chart-tick-label" x={spotX(spot)} y={margin.top + plotHeight + 22}>{formatSpot(spot)}</text>
              </g>
            );
          })}
          <text className="axis-label" x={margin.left + plotWidth / 2} y={height - 8}>到期 USD/CNY 汇率</text>

          <line className="expected-spot-line" x1={expectedX} x2={expectedX} y1={margin.top} y2={margin.top + plotHeight} />
          <text className="expected-spot-label" x={expectedX + 5} y={margin.top + 13}>预计 {formatSpot(response.distribution.assumed_expected_maturity_spot)}</text>

          <line className="range-bracket range-90" x1={spotX(range90.lower_spot)} x2={spotX(range90.upper_spot)} y1={17} y2={17} />
          <text className="range-label" x={(spotX(range90.lower_spot) + spotX(range90.upper_spot)) / 2} y={12}>90% 汇率范围</text>
          <line className="range-bracket range-50" x1={spotX(range50.lower_spot)} x2={spotX(range50.upper_spot)} y1={28} y2={28} />
          <text className="range-label" x={(spotX(range50.lower_spot) + spotX(range50.upper_spot)) / 2} y={34}>50% 范围</text>
        </svg>
      </div>
    </section>
  );
}
