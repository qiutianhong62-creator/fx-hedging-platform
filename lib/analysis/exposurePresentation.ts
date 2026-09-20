import type { AmountRange, ResultKind } from "../api/forwardProbability.ts";
import { formatCnyWan } from "./probabilityDashboard.ts";

export function exposureCopy(kind: ResultKind) {
  return kind === "cny_cost"
    ? {
        exposure: "美元应付", amount: "成本", forward: "购汇",
        title: "看懂你的远期策略，到期需要支付多少钱",
        target: "人民币预算上限", targetTitle: "你的付款有多大概率不超预算",
        met: "不超过预算", missed: "超出预算",
        improvement: "节省成本",
        differenceNote: "节省成本 = 不套保成本 − 远期策略成本。正数表示节省，负数表示多花。",
      }
    : {
        exposure: "美元应收", amount: "收款", forward: "结汇",
        title: "看懂你的远期策略，到期可能收回多少钱",
        target: "目标人民币金额", targetTitle: "你的收款目标有多大概率实现",
        met: "达到目标", missed: "未达到目标",
        improvement: "增加收款",
        differenceNote: "增加收款 = 远期策略收款 − 不套保收款。正数表示多收，负数表示少收。",
      };
}

// The API always returns strategy minus baseline; costs improve in the opposite direction.
export function improvementRange(range: AmountRange, kind: ResultKind): AmountRange {
  return kind === "cny_cost"
    ? { minimum_amount_cny: -range.maximum_amount_cny, maximum_amount_cny: -range.minimum_amount_cny }
    : range;
}

export function signedCnyRange(minimum: number, maximum: number): string {
  const format = (value: number) => `${value > 0 ? "+" : ""}${formatCnyWan(value === 0 ? 0 : value)}`;
  return minimum === maximum ? format(minimum) : `${format(minimum)} – ${format(maximum)}`;
}
