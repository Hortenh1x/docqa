import type { Metadata } from "next";
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { TopBar } from "@/components/TopBar";

const fraunces = Fraunces({
  subsets: ["latin"],
  weight: ["600"],
  variable: "--font-fraunces",
});
const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
});
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  title: "DocQA — ask the documents",
  description:
    "Answers with page-level citations — or an honest 'not found'. Multi-tenant document Q&A.",
};

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${inter.variable} ${jetbrains.variable}`}>
      <body className="min-h-screen bg-paper text-ink antialiased">
        <Providers>
          {DEMO_MODE && (
            <div className="bg-pending/10 border-b border-pending/30 px-4 py-1.5 text-center text-xs text-ink-soft">
              Public demo — sandbox data is wiped nightly. Policies collections are read-only.
            </div>
          )}
          <TopBar />
          <main className="mx-auto w-full max-w-[760px] px-4 pb-24">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
