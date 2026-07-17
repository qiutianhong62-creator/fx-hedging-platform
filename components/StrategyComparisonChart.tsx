"use client";

import { useEffect, useRef } from "react";
import type { CompositeScenarioPoint } from "../lib/strategies/types";

export type ComparisonSeries = {
  id: string;
  label: string;
  color: string;
  points: CompositeScenarioPoint[];
  emphasized?: boolean;
  dashed?: boolean;
};

type Props = {
  series: ComparisonSeries[];
  selectedSpot: number;
  yAxisLabel?: string;
  ariaLabel?: string;
};

export function StrategyComparisonChart({
  series,
  selectedSpot,
  yAxisLabel = "人民币收入（万元）",
  ariaLabel = "多个自定义外汇策略的人民币收入情景对比折线图",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || series.length === 0 || series[0].points.length < 2) return;

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(760, rect.width);
      const height = 390;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);

      const margin = { top: 25, right: 30, bottom: 58, left: 72 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const spots = series[0].points.map((point) => point.spot);
      const incomes = series.flatMap((item) => item.points.map((point) => point.incomeCny));
      const xMin = Math.min(...spots);
      const xMax = Math.max(...spots);
      const rawMin = Math.min(...incomes) / 10_000;
      const rawMax = Math.max(...incomes) / 10_000;
      const padding = Math.max(5, (rawMax - rawMin) * 0.08);
      const yMin = Math.floor((rawMin - padding) / 10) * 10;
      const yMax = Math.ceil((rawMax + padding) / 10) * 10;
      const x = (value: number) => margin.left + ((value - xMin) / (xMax - xMin)) * plotWidth;
      const y = (value: number) =>
        margin.top + (1 - (value / 10_000 - yMin) / (yMax - yMin)) * plotHeight;

      context.font = '12px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif';
      context.lineWidth = 1;
      context.strokeStyle = "#dde5e3";
      context.fillStyle = "#65746f";
      context.textAlign = "right";
      context.textBaseline = "middle";
      for (let index = 0; index <= 5; index += 1) {
        const value = yMin + ((yMax - yMin) * index) / 5;
        const py = margin.top + plotHeight - (plotHeight * index) / 5;
        context.beginPath();
        context.moveTo(margin.left, py);
        context.lineTo(width - margin.right, py);
        context.stroke();
        context.fillText(value.toFixed(0), margin.left - 10, py);
      }

      context.textAlign = "center";
      context.textBaseline = "top";
      for (let index = 0; index <= 7; index += 1) {
        const value = xMin + ((xMax - xMin) * index) / 7;
        const px = margin.left + (plotWidth * index) / 7;
        context.fillText(value.toFixed(2), px, height - margin.bottom + 14);
      }

      for (const item of series) {
        context.save();
        if (item.dashed) context.setLineDash([8, 5]);
        context.beginPath();
        item.points.forEach((point, index) => {
          const px = x(point.spot);
          const py = y(point.incomeCny);
          if (index === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        });
        context.strokeStyle = item.color;
        context.lineWidth = item.emphasized ? 4 : 2.3;
        context.lineJoin = "round";
        context.lineCap = "round";
        context.stroke();
        context.restore();
      }

      const selected = Math.min(xMax, Math.max(xMin, selectedSpot));
      const selectedX = x(selected);
      context.save();
      context.setLineDash([4, 5]);
      context.strokeStyle = "#8d9b97";
      context.beginPath();
      context.moveTo(selectedX, margin.top);
      context.lineTo(selectedX, margin.top + plotHeight);
      context.stroke();
      context.restore();

      for (const item of series) {
        const nearest = item.points.reduce((best, point) =>
          Math.abs(point.spot - selected) < Math.abs(best.spot - selected) ? point : best,
        );
        context.fillStyle = item.color;
        context.beginPath();
        context.arc(x(nearest.spot), y(nearest.incomeCny), item.emphasized ? 5.5 : 4, 0, Math.PI * 2);
        context.fill();
        context.strokeStyle = "#ffffff";
        context.lineWidth = 2;
        context.stroke();
      }

      context.save();
      context.translate(18, margin.top + plotHeight / 2);
      context.rotate(-Math.PI / 2);
      context.fillStyle = "#53645f";
      context.textAlign = "center";
      context.fillText(yAxisLabel, 0, 0);
      context.restore();

      context.fillStyle = "#53645f";
      context.textAlign = "center";
      context.fillText("到期即期汇率（人民币 / 美元）", margin.left + plotWidth / 2, height - 16);
    };

    render();
    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [selectedSpot, series, yAxisLabel]);

  return (
    <div className="comparison-canvas-wrap">
      <canvas
        ref={canvasRef}
        aria-label={ariaLabel}
        role="img"
      />
    </div>
  );
}
