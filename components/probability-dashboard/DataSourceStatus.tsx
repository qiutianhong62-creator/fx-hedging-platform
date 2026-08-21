import type { AutomaticForwardProbabilityResponse } from "../../lib/api/forwardProbability.ts";
import {
  formatProbability,
  formatSpot,
} from "../../lib/analysis/probabilityDashboard.ts";

type ResponseProps = { response: AutomaticForwardProbabilityResponse };

const cacheLabels = {
  live_fetch: "本次实时抓取",
  daily_cache: "使用当日缓存",
  stale_fallback: "使用备用缓存",
} as const;

const unavailableLabels = {
  fetch_failed: "网页暂时无法读取",
  source_invalid: "来源内容无法识别",
  source_stale: "来源数据过旧",
  horizon_insufficient: "预测期限不足",
} as const;

function dateTime(value: string): string {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf())
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(parsed);
}

export function DataSourceStatus({ response }: ResponseProps) {
  const forecast = response.data_sources.forecast;
  const history = response.data_sources.market_history;
  const isFallback = forecast.aggregation_status === "single_source_fallback";

  return (
    <section className="result-section" aria-labelledby="source-status-title">
      <div className="result-heading">
        <div>
          <p className="section-kicker">数据来源</p>
          <h2 id="source-status-title">这次分析使用了哪些市场信息</h2>
        </div>
        <span className={isFallback ? "source-state source-fallback" : "source-state"}>
          {isFallback ? "单一机构备用结果" : "ING + MUFG 等权综合"}
        </span>
      </div>

      <div className="source-grid">
        {forecast.sources.map((source) => (
          <article className="source-card" key={source.institution}>
            <div className="source-card-title">
              <strong>{source.institution} 预测</strong>
              <span>{formatProbability(source.weight)} 权重</span>
            </div>
            <dl>
              <div>
                <dt>匹配到期汇率</dt>
                <dd>{formatSpot(source.matched_maturity_spot)}</dd>
              </div>
              <div>
                <dt>机构更新日</dt>
                <dd>{source.source_updated_date}</dd>
              </div>
              <div>
                <dt>系统抓取时间</dt>
                <dd>{dateTime(source.fetched_at_utc)}</dd>
              </div>
              <div>
                <dt>数据状态</dt>
                <dd>{cacheLabels[source.cache_status]}</dd>
              </div>
            </dl>
            <a href={source.source_url} target="_blank" rel="noreferrer">
              查看机构原始来源 ↗
            </a>
          </article>
        ))}

        <article className="source-card source-card-history">
          <div className="source-card-title">
            <strong>FRED 历史波动率</strong>
            <span>近 1 年</span>
          </div>
          <dl>
            <div>
              <dt>年化波动率</dt>
              <dd>{response.distribution.assumed_annualized_volatility_pct.toFixed(2)}%</dd>
            </div>
            <div>
              <dt>观察窗口</dt>
              <dd>{history.historical_volatility.window_start} 至 {history.historical_volatility.window_end}</dd>
            </div>
            <div>
              <dt>有效汇率记录</dt>
              <dd>{history.historical_volatility.observation_count} 条</dd>
            </div>
            <div>
              <dt>数据状态</dt>
              <dd>{cacheLabels[history.source.cache_status]}</dd>
            </div>
          </dl>
          <small>来源序列：{history.source.provider} · {history.source.series_id}</small>
        </article>
      </div>

      {forecast.unavailable_sources.length > 0 && (
        <div className="source-unavailable" role="status">
          <strong>部分机构本次未参与综合：</strong>
          {forecast.unavailable_sources.map((source) => (
            <span key={source.institution}>
              {source.institution}（{unavailableLabels[source.reason_code]}）
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
