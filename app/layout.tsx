import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业外汇套保与风险分析平台",
  description: "面向出口企业的多产品组合套保、收益曲线与风险情景分析平台。",
  openGraph: {
    title: "企业外汇套保与风险分析平台",
    description: "在同一业务起点下，自由组合远期、掉期、期权和定存，并比较不同汇率情景的人民币结果。",
    type: "website",
    locale: "zh_CN",
    images: [
      {
        url: "/og-composite-v2.png",
        width: 1734,
        height: 907,
        alt: "企业外汇套保与风险分析平台",
      },
    ],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
