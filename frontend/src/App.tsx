import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SearchBar } from "./components/SearchBar";
import { SavedSearches } from "./components/SavedSearches";
import { ResultsDashboard } from "./components/ResultsDashboard";
import { SourcesPanel } from "./components/SourcesPanel";
import { LiveFeed } from "./components/LiveFeed";

const COLORS = {
  primary: "#2563eb",
  bg: "#f9fafb",
  border: "#e5e7eb",
  text: "#374151",
  muted: "#6b7280",
  card: "#fff",
};

type MainTab = "results" | "sources" | "live";

export default function App() {
  const { t, i18n } = useTranslation();
  const [selectedSearchId, setSelectedSearchId] = useState<number | null>(null);
  const [mainTab, setMainTab] = useState<MainTab>("results");

  return (
    <div
      style={{
        fontFamily: "'Inter', system-ui, sans-serif",
        minHeight: "100vh",
        background: COLORS.bg,
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* ── Top Bar ─────────────────────────────────────────────── */}
      <header
        style={{
          background: COLORS.card,
          borderBottom: `1px solid ${COLORS.border}`,
          padding: "0 1.5rem",
          height: 56,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          position: "sticky",
          top: 0,
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontSize: "1.25rem" }}>🔍</span>
          <span
            style={{
              fontWeight: 800,
              fontSize: "1.1rem",
              color: COLORS.text,
              letterSpacing: "-0.02em",
            }}
          >
            Find Item
          </span>
          <span
            style={{
              fontSize: "0.75rem",
              color: COLORS.muted,
              display: "none", // hidden on small screens, shown via CSS not available inline
            }}
          >
            {t("welcome")}
          </span>
        </div>

        {/* Language toggle */}
        <button
          onClick={() => i18n.changeLanguage(i18n.language === "th" ? "en" : "th")}
          style={{
            padding: "0.35rem 0.9rem",
            borderRadius: 8,
            border: `1.5px solid ${COLORS.border}`,
            background: COLORS.card,
            cursor: "pointer",
            fontSize: "0.813rem",
            fontWeight: 600,
            color: COLORS.text,
          }}
        >
          {i18n.language === "th" ? "EN" : "TH"}
        </button>
      </header>

      {/* ── Search Bar ──────────────────────────────────────────── */}
      <div
        style={{
          background: COLORS.card,
          borderBottom: `1px solid ${COLORS.border}`,
          padding: "0.875rem 1.5rem",
          flexShrink: 0,
        }}
      >
        <SearchBar onSearchCreated={(id) => { setSelectedSearchId(id); setMainTab("results"); }} />
      </div>

      {/* ── Main layout: sidebar + content ─────────────────────── */}
      <div
        style={{
          display: "flex",
          flex: 1,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        {/* Sidebar — saved searches */}
        <aside
          style={{
            width: 260,
            flexShrink: 0,
            borderRight: `1px solid ${COLORS.border}`,
            background: COLORS.card,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <SavedSearches
            selectedId={selectedSearchId}
            onSelect={(id) => { setSelectedSearchId(id); setMainTab("results"); }}
          />
        </aside>

        {/* Content area */}
        <main
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            minWidth: 0,
          }}
        >
          {/* Content tabs */}
          <div
            style={{
              display: "flex",
              borderBottom: `1px solid ${COLORS.border}`,
              background: COLORS.card,
              padding: "0 1rem",
              flexShrink: 0,
            }}
          >
            {(
              [
                { key: "results", label: t("results_tab") },
                { key: "sources", label: t("sources_tab") },
                { key: "live", label: t("live_feed_title") },
              ] as { key: MainTab; label: string }[]
            ).map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setMainTab(key)}
                style={{
                  padding: "0.75rem 1rem",
                  border: "none",
                  background: "none",
                  cursor: "pointer",
                  fontSize: "0.875rem",
                  fontWeight: mainTab === key ? 700 : 400,
                  color: mainTab === key ? COLORS.primary : COLORS.muted,
                  borderBottom:
                    mainTab === key
                      ? `2px solid ${COLORS.primary}`
                      : "2px solid transparent",
                  marginBottom: -1,
                }}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Tab panels */}
          <div style={{ flex: 1, overflowY: "auto" }}>
            {mainTab === "results" && (
              <ResultsDashboard selectedSearchId={selectedSearchId} />
            )}
            {mainTab === "sources" && <SourcesPanel />}
            {mainTab === "live" && <LiveFeed />}
          </div>
        </main>
      </div>
    </div>
  );
}
