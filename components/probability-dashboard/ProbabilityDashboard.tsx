"use client";

import { useMemo, useRef, useState } from "react";

import {
  ForwardProbabilityApiError,
  requestForwardProbability,
  type AutomaticForwardProbabilityResponse,
  type ExposureType,
} from "../../lib/api/forwardProbability.ts";
import {
  buildRequest,
  coverageSummary,
  createInitialDraft,
  switchExposure,
  validateDraft,
  type AnalysisDraft,
  type DraftErrors,
  type ForwardLegDraft,
} from "../../lib/analysis/probabilityDashboard.ts";
import { AnalysisInputPanel } from "./AnalysisInputPanel";
import { AnalysisSummary } from "./AnalysisSummary";
import { DataSourceStatus } from "./DataSourceStatus";
import { ProbabilityComparisonTable } from "./ProbabilityComparisonTable";
import { ProbabilityDistributionChart } from "./ProbabilityDistributionChart";
import { RiskNotices } from "./RiskNotices";
import { TargetAnalysisPanel } from "./TargetAnalysisPanel";
import { exposureCopy } from "../../lib/analysis/exposurePresentation.ts";

type DashboardStatus =
  | "idle"
  | "loading_initial"
  | "success"
  | "loading_target"
  | "validation_error"
  | "connection_error"
  | "analysis_error";

export function ProbabilityDashboard() {
  const [draft, setDraft] = useState<AnalysisDraft>(createInitialDraft());
  const [status, setStatus] = useState<DashboardStatus>("idle");
  const [errors, setErrors] = useState<DraftErrors>({});
  const [response, setResponse] =
    useState<AutomaticForwardProbabilityResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [targetError, setTargetError] = useState<string | null>(null);
  const [isStale, setIsStale] = useState(false);
  const legCounter = useRef(1);
  const requestVersion = useRef(0);
  const copy = exposureCopy(draft.exposureType === "usd_payable" ? "cny_cost" : "cny_proceeds");

  const coverage = useMemo(() => coverageSummary(draft), [draft]);

  const markChanged = () => {
    requestVersion.current += 1;
    setStatus(response ? "success" : "idle");
    setErrorMessage(null);
    setErrors({});
    if (response) {
      setIsStale(true);
      setResponse((current) =>
        current
          ? {
              ...current,
              no_hedge: { ...current.no_hedge, target_probability: null },
              forward_strategy: {
                ...current.forward_strategy,
                target_probability: null,
              },
            }
          : current,
      );
    }
    setTargetError(null);
  };

  const changeExposure = (exposureType: ExposureType) => {
    if (exposureType === draft.exposureType) return;
    requestVersion.current += 1;
    setDraft((current) => switchExposure(current, exposureType));
    legCounter.current = 1;
    setResponse(null);
    setErrors({});
    setErrorMessage(null);
    setTargetError(null);
    setIsStale(false);
    setStatus("idle");
  };

  const changeTarget = (targetCny: number | null) => {
    requestVersion.current += 1;
    setDraft((current) => ({ ...current, targetCny }));
    setStatus(response ? "success" : "idle");
    setTargetError(null);
    setResponse((current) => current ? {
      ...current,
      no_hedge: { ...current.no_hedge, target_probability: null },
      forward_strategy: { ...current.forward_strategy, target_probability: null },
    } : null);
  };

  const updateDraft = (patch: Partial<AnalysisDraft>) => {
    markChanged();
    setDraft((current) => ({ ...current, ...patch }));
  };

  const updateLeg = (id: string, patch: Partial<ForwardLegDraft>) => {
    markChanged();
    setDraft((current) => ({
      ...current,
      legs: current.legs.map((leg) =>
        leg.id === id ? { ...leg, ...patch } : leg,
      ),
    }));
  };

  const addLeg = () => {
    markChanged();
    legCounter.current += 1;
    setDraft((current) => ({
      ...current,
      legs: [
        ...current.legs,
        {
          id: `forward-${legCounter.current}`,
          notionalUsd: 0,
          forwardRate: 0,
        },
      ],
    }));
  };

  const deleteLeg = (id: string) => {
    markChanged();
    setDraft((current) =>
      current.legs.length === 1
        ? current
        : { ...current, legs: current.legs.filter((leg) => leg.id !== id) },
    );
  };

  const runInitialAnalysis = async () => {
    const version = ++requestVersion.current;
    const nextErrors = validateDraft({ ...draft, targetCny: null });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setStatus("validation_error");
      return;
    }
    setStatus("loading_initial");
    setErrorMessage(null);
    try {
      const nextResponse = await requestForwardProbability(
        buildRequest(draft, null),
      );
      if (version !== requestVersion.current) return;
      setResponse(nextResponse);
      setStatus("success");
      setIsStale(false);
    } catch (error) {
      if (version !== requestVersion.current) return;
      const normalized =
        error instanceof ForwardProbabilityApiError
          ? error
          : new ForwardProbabilityApiError(
              "analysis_error",
              "分析失败，请稍后重试。",
            );
      setErrorMessage(normalized.message);
      setStatus(
        normalized.code === "connection_error"
          ? "connection_error"
          : normalized.code === "validation_error"
            ? "validation_error"
            : "analysis_error",
      );
    }
  };

  const runTargetAnalysis = async () => {
    if (!response || isStale || status === "loading_initial") return;
    if (
      draft.targetCny === null ||
      !Number.isFinite(draft.targetCny) ||
      draft.targetCny <= 0
    ) {
      setTargetError(`${copy.target}必须大于 0`);
      return;
    }
    setStatus("loading_target");
    const version = ++requestVersion.current;
    setTargetError(null);
    try {
      const nextResponse = await requestForwardProbability(
        buildRequest(draft, draft.targetCny),
      );
      if (version !== requestVersion.current) return;
      setResponse(nextResponse);
      setStatus("success");
    } catch (error) {
      if (version !== requestVersion.current) return;
      const message =
        error instanceof ForwardProbabilityApiError
          ? error.message
          : "目标概率计算失败，请重试。";
      setTargetError(message);
      setStatus("success");
    }
  };

  return (
    <main className="probability-dashboard">
      <header className="dashboard-header">
        <a className="dashboard-brand" href="#top" aria-label="企业外汇风险分析首页">
          <span className="dashboard-brand-mark">FX</span>
          <span>
            <strong>企业外汇风险分析</strong>
            <small>到期收付款概率工作台</small>
          </span>
        </a>
        <span className="data-status">数据来自 ING、MUFG 与 FRED</span>
      </header>

      <section className="dashboard-intro" id="top">
        <p className="section-kicker">USD/CNY · 概率分析</p>
        <h1>{copy.title}</h1>
        <p>
          输入真实远期报价，系统会连接机构预测与历史市场数据，比较不套保和远期策略在不同汇率区间下的人民币{copy.amount}结果。
        </p>
      </section>

      <fieldset className="exposure-selector">
        <legend>我的情况</legend>
        <label>
          <input type="radio" name="exposure" value="usd_receivable"
            checked={draft.exposureType === "usd_receivable"}
            onChange={() => changeExposure("usd_receivable")} />
          未来收到美元（出口收款）
        </label>
        <label>
          <input type="radio" name="exposure" value="usd_payable"
            checked={draft.exposureType === "usd_payable"}
            onChange={() => changeExposure("usd_payable")} />
          未来支付美元（进口付款）
        </label>
        <p>切换收付款方向会保留美元金额和到期日，清空远期报价、目标和分析结果。</p>
      </fieldset>

      <AnalysisInputPanel
        draft={draft}
        errors={errors}
        loading={status === "loading_initial" || status === "loading_target"}
        stale={isStale}
        coverage={coverage}
        onDraftChange={updateDraft}
        onLegChange={updateLeg}
        onAddLeg={addLeg}
        onDeleteLeg={deleteLeg}
        onSubmit={runInitialAnalysis}
      />

      {!response && (
        <aside className="workflow-preview" aria-label="后续分析步骤">
          <strong>接下来会看到什么？</strong>
          <span>先查看分析结果，再填写{copy.target}。</span>
          <span>概率分布图作为表格的辅助说明，精确数字以表格为准。</span>
          <span>结果不构成银行报价、交易建议或收益保证。</span>
        </aside>
      )}

      {errorMessage && (
        <section className="status-error" role="alert">
          <strong>这次分析没有完成</strong>
          <p>{errorMessage}</p>
          {status === "connection_error" && (
            <p>请先启动本地 Python 后端服务，然后保留当前输入并再次点击“开始概率分析”。</p>
          )}
        </section>
      )}

      {response && (
        <div
          className={`results-stack${status === "loading_initial" ? " results-dimmed" : ""}`}
          aria-live="polite"
          aria-busy={status === "loading_initial"}
        >
          <DataSourceStatus response={response} />
          <AnalysisSummary response={response} />
          <ProbabilityComparisonTable response={response} />
          <ProbabilityDistributionChart response={response} />
          <TargetAnalysisPanel
            resultKind={response.result_kind}
            disabled={isStale || status === "loading_initial"}
            targetCny={draft.targetCny}
            loading={status === "loading_target"}
            error={targetError}
            noHedge={response.no_hedge.target_probability}
            strategy={response.forward_strategy.target_probability}
            onTargetChange={changeTarget}
            onSubmit={runTargetAnalysis}
          />
          <RiskNotices response={response} />
        </div>
      )}

      <footer className="dashboard-footer">
        模型结果用于风险情景分析，不构成交易或套保建议。
      </footer>
    </main>
  );
}
