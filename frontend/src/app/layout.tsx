import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CaseLens — AI-Powered Case File Analysis",
  description: "Upload legal PDFs and receive structured case summaries powered by Claude.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f8f9fa]">
        {/* Header */}
        <header className="bg-[var(--navy)] text-white shadow-lg">
          <div className="max-w-5xl mx-auto px-6 py-5 flex items-baseline gap-4">
            <h1 className="text-2xl font-bold tracking-tight">
              Case<span className="text-[var(--gold)]">Lens</span>
            </h1>
            <p className="text-sm text-gray-400 hidden sm:block">
              AI-Powered Case File Analysis
            </p>
          </div>
        </header>

        {/* Main Content */}
        <main className="max-w-5xl mx-auto px-6 py-10">
          {children}
        </main>

        {/* Footer */}
        <footer className="text-center text-xs text-gray-400 py-6">
          CaseLens v0.8.0 — For legal research purposes only
        </footer>
      </body>
    </html>
  );
}
