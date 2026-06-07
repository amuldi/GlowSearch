import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "GlowSearch",
  description: "화장품 상품 정보 검색",
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
