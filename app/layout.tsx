import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业外汇套保与风险分析平台",
  description: "面向出口企业的交互式外汇套保收益与风险情景分析平台。",
  openGraph: {
    title: "企业外汇套保与风险分析平台",
    description: "输入任意套保比例，实时比较远期套保与不套保的人民币收入曲线。",
    type: "website",
    locale: "zh_CN",
    images: [
      {
        url: "/fx-hedging-social-card.png",
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
