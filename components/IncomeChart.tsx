"use client";

import { useEffect, useRef } from "react";
import type { ScenarioPoint } from "../lib/strategies/types";

type Props = {
  points: ScenarioPoint[];
  selectedSpot: number;
};

export function IncomeChart({ points, selectedSpot }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;

    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const width = Math.max(640, rect.width);
      const height = 360;
      const ratio = window.devicePixelRatio || 1;
      canvas.width = width * ratio;
      canvas.height = height * ratio;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);

      const margin = { top: 24, right: 24, bottom: 54, left: 68 };
      const plotWidth = width - margin.left - margin.right;
      const plotHeight = height - margin.top - margin.bottom;
      const spots = points.map((point) => point.spot);
      const incomes = points.flatMap((point) => [point.hedgedIncomeCny, point.unhedgedIncomeCny]);
      const xMin = Math.min(...spots);
      const xMax = Math.max(...spots);
      const rawMin = Math.min(...incomes) / 10_000;
      const rawMax = Math.max(...incomes) / 10_000;
      const padding = Math.max(5, (rawMax - rawMin) * 0.08);
      const yMin = Math.floor((rawMin - padding) / 10) * 10;
      const yMax = Math.ceil((rawMax + padding) / 10) * 10;
      const x = (value: number) => margin.left + ((value - xMin) / (xMax - xMin)) * plotWidth;
      const y = (value: number) => margin.top + (1 - (value / 10_000 - yMin) / (yMax - yMin)) * plotHeight;

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
        context.fillText(`${value.toFixed(0)}`, margin.left - 10, py);
      }

      context.textAlign = "center";
      context.textBaseline = "top";
      for (let index = 0; index <= 7; index += 1) {
        const value = xMin + ((xMax - xMin) * index) / 7;
        const px = margin.left + (plotWidth * index) / 7;
        context.fillText(value.toFixed(2), px, height - margin.bottom + 14);
      }

      const drawLine = (key: "hedgedIncomeCny" | "unhedgedIncomeCny", color: string, lineWidth: number) => {
        context.beginPath();
        points.forEach((point, index) => {
          const px = x(point.spot);
          const py = y(point[key]);
          if (index === 0) context.moveTo(px, py);
          else context.lineTo(px, py);
        });
        context.strokeStyle = color;
        context.lineWidth = lineWidth;
        context.lineJoin = "round";
        context.lineCap = "round";
        context.stroke();
      };

      drawLine("unhedgedIncomeCny", "#e5824f", 2.5);
      drawLine("hedgedIncomeCny", "#087f73", 3.5);

      const selected = Math.min(xMax, Math.max(xMin, selectedSpot));
      const px = x(selected);
      context.save();
      context.setLineDash([5, 5]);
      context.strokeStyle = "#94a39f";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(px, margin.top);
      context.lineTo(px, margin.top + plotHeight);
      context.stroke();
      context.restore();

      const nearest = points.reduce((best, point) =>
        Math.abs(point.spot - selected) < Math.abs(best.spot - selected) ? point : best,
      );
      context.fillStyle = "#087f73";
      context.beginPath();
      context.arc(x(nearest.spot), y(nearest.hedgedIncomeCny), 5, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "#ffffff";
      context.lineWidth = 2;
      context.stroke();

      context.save();
      context.translate(18, margin.top + plotHeight / 2);
      context.rotate(-Math.PI / 2);
      context.fillStyle = "#53645f";
      context.textAlign = "center";
      context.font = '12px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif';
      context.fillText("人民币收入（万元）", 0, 0);
      context.restore();

      context.fillStyle = "#53645f";
      context.textAlign = "center";
      context.fillText("到期即期汇率（人民币 / 美元）", margin.left + plotWidth / 2, height - 16);
    };

    render();
    const observer = new ResizeObserver(render);
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [points, selectedSpot]);

  return (
    <div className="canvas-wrap">
      <canvas
        ref={canvasRef}
        aria-label="自定义套保与不套保人民币收入情景折线图"
        role="img"
      />
    </div>
  );
}
