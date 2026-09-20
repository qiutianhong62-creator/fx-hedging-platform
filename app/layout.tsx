import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "企业外汇套保与风险分析平台",
  description: "输入真实远期报价，比较不同汇率区间下的人民币收款与付款成本。",
  openGraph: {
    title: "企业外汇套保与风险分析平台",
    description: "输入真实远期报价，比较不同汇率区间下的人民币收款与付款成本。",
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
