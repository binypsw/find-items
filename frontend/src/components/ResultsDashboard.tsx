import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { getTopListings, getSearchRuns } from "../api/client";
import { ProductCard } from "./ProductCard";
import type { ScrapeRun } from "../types";

const COLORS = {
  primary: "#2563eb",
  success: "#16a34a",
  warning: "#f59e0b",
  error: "#ef4444",
  bg: "#f9fafb",
  border: "#e5e7eb",
  text: "#374151",
  muted: "#6b7280",
  card: "#fff",
};

const STATUS_COLORS: Record<string, string> = {
  pending: COLORS.muted,
  running: COLORS.warning,
  completed: COLORS.success,
  failed: COLORS.error,
  cancelled: COLORS.muted,
};

interface ResultsDashboardProps {
  selectedSearchId: number | null;
}

type Tab = "results" | "history";

export function ResultsDashboard({ selectedSearchId }: ResultsDashboardProps) {
  const { t, i18n } = useTranslation();
  const [tab, setTab] = useState<Tab>("results");

  if (selectedSearchId === null) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: COLORS.muted,
          fontSize: "0.938rem",
          padding: "2rem",
        }}
      >
        {t("select_search")}
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* Tabs */}
      <div
        style={{
          display: "flex",
          borderBottom: `1px solid ${COLORS.border}`,
          padding: "0 1rem",
          background: COLORS.card,
          flexShrink: 0,
        }}
      >
        {(["results", "history"] as Tab[]).map((tabKey) => (
          <button
            key={tabKey}
            onClick={() => setTab(tabKey)}
            style={{
              padding: "0.75rem 1rem",
              border: "none",
              background: "none",
              cursor: "pointer",
              fontSize: "0.875rem",
              fontWeight: tab === tabKey ? 700 : 400,
              color: tab === tabKey ? COLORS.primary : COLORS.muted,
              borderBottom: tab === tabKey ? `2px solid ${COLORS.primary}` : "2px solid transparent",
              marginBottom: -1,
            }}
          >
            {t(tabKey === "results" ? "results_tab" : "history_tab")}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "1rem" }}>
        {tab === "results" ? (
          <ResultsTab searchId={selectedSearchId} lang={i18n.language} t={t} />
        ) : (
          <HistoryTab searchId={selectedSearchId} lang={i18n.language} t={t} />
        )}
      </div>
    </div>
  );
}

function ResultsTab({
  searchId,
  t,
}: {
  searchId: number;
  lang: string;
  t: (key: string) => string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["top-listings", searchId],
    queryFn: () => getTopListings(searchId, 20),
    enabled: searchId > 0,
  });

  if (isLoading) {
    return (
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: "1rem",
        }}
      >
        {[1, 2, 3].map((i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "3rem",
          color: COLORS.muted,
          fontSize: "0.938rem",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        <span style={{ fontSize: "2.5rem" }}>🔍</span>
        <span>{t("no_results")}</span>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
        gap: "1rem",
      }}
    >
      {data.map((listing) => (
        <ProductCard key={listing.id} listing={listing} />
      ))}
    </div>
  );
}

function HistoryTab({
  searchId,
  lang,
  t,
}: {
  searchId: number;
  lang: string;
  t: (key: string) => string;
}) {
  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs", searchId],
    queryFn: () => getSearchRuns(searchId, 10),
    enabled: searchId > 0,
  });

  const formatDate = (dateStr: string) =>
    new Date(dateStr).toLocaleDateString(lang === "th" ? "th-TH" : "en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  if (isLoading) {
    return <p style={{ color: COLORS.muted, fontSize: "0.875rem" }}>{t("loading")}</p>;
  }

  if (!runs || runs.length === 0) {
    return <p style={{ color: COLORS.muted, fontSize: "0.875rem" }}>{t("no_results")}</p>;
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.813rem",
        }}
      >
        <thead>
          <tr style={{ background: COLORS.bg, textAlign: "left" }}>
            <Th>{t("col_source")}</Th>
            <Th>{t("col_started")}</Th>
            <Th>{t("col_status")}</Th>
            <Th>{t("col_items")}</Th>
            <Th>{t("col_credits")}</Th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run: ScrapeRun) => (
            <tr key={run.id} style={{ borderBottom: `1px solid ${COLORS.border}` }}>
              <Td>{run.source_id}</Td>
              <Td>{formatDate(run.started_at)}</Td>
              <Td>
                <StatusBadge status={run.status} />
              </Td>
              <Td>{run.items_found}</Td>
              <Td>{run.api_credits_used}</Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? COLORS.muted;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.5rem",
        borderRadius: 5,
        background: color + "22",
        color,
        fontWeight: 600,
        fontSize: "0.75rem",
        textTransform: "capitalize",
      }}
    >
      {status}
    </span>
  );
}

function SkeletonCard() {
  return (
    <div
      style={{
        background: COLORS.card,
        borderRadius: 12,
        border: `1px solid ${COLORS.border}`,
        overflow: "hidden",
        height: 320,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div style={{ height: 160, background: "#e5e7eb" }} />
      <div style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        <div style={{ height: 14, background: "#e5e7eb", borderRadius: 4, width: "80%" }} />
        <div style={{ height: 14, background: "#e5e7eb", borderRadius: 4, width: "60%" }} />
        <div style={{ height: 20, background: "#e5e7eb", borderRadius: 4, width: "40%", marginTop: "0.25rem" }} />
      </div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      style={{
        padding: "0.6rem 1rem",
        fontWeight: 600,
        fontSize: "0.813rem",
        color: COLORS.text,
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td
      style={{
        padding: "0.6rem 1rem",
        fontSize: "0.813rem",
        color: COLORS.text,
      }}
    >
      {children}
    </td>
  );
}
