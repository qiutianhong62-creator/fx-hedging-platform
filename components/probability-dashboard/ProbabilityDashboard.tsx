"use client";

import { useMemo, useRef, useState } from "react";

import {
  ForwardProbabilityApiError,
  requestForwardProbability,
  type AutomaticForwardProbabilityResponse,
} from "../../lib/api/forwardProbability.ts";
import {
  buildRequest,
  coverageSummary,
  createInitialDraft,
  validateDraft,
  type AnalysisDraft,
  type DraftErrors,
  type ForwardLegDraft,
} from "../../lib/analysis/probabilityDashboard.ts";
import { AnalysisInputPanel } from "./AnalysisInputPanel";
import { AnalysisSummary } from "./AnalysisSummary";
import { DataSourceStatus } from "./DataSourceStatus";
import { ProbabilityComparisonTable } from "./ProbabilityComparisonTable";

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
  const [isStale, setIsStale] = useState(false);
  const legCounter = useRef(1);

  const coverage = useMemo(() => coverageSummary(draft), [draft]);

  const markChanged = () => {
    if (response) setIsStale(true);
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
      setResponse(nextResponse);
      setStatus("success");
      setIsStale(false);
    } catch (error) {
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

  return (
    <main className="probability-dashboard">
      <header className="dashboard-header">
        <a className="dashboard-brand" href="#top" aria-label="企业外汇风险分析首页">
          <span className="dashboard-brand-mark">FX</span>
          <span>
            <strong>企业外汇风险分析</strong>
            <small>到期收款概率工作台</small>
          </span>
        </a>
        <span className="data-status">数据来自 ING、MUFG 与 FRED</span>
      </header>

      <section className="dashboard-intro" id="top">
        <p className="section-kicker">USD/CNY · 概率分析</p>
        <h1>看懂你的远期策略，到期可能收回多少钱</h1>
        <p>
          输入真实远期报价，系统会连接机构预测与历史市场数据，比较不套保和远期策略在不同汇率区间下的人民币收款结果。
        </p>
      </section>

      <AnalysisInputPanel
        draft={draft}
        errors={errors}
        loading={status === "loading_initial"}
        stale={isStale}
        coverage={coverage}
        onDraftChange={updateDraft}
        onLegChange={updateLeg}
        onAddLeg={addLeg}
        onDeleteLeg={deleteLeg}
        onSubmit={runInitialAnalysis}
      />

      {errorMessage && (
        <section className="status-error" role="alert">
          <strong>这次分析没有完成</strong>
          <p>{errorMessage}</p>
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
        </div>
      )}

      <footer className="dashboard-footer">
        模型结果用于风险情景分析，不构成交易或套保建议。
      </footer>
    </main>
  );
}
