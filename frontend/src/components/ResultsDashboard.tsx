import { useState, useMemo, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTopListings, getSearchRuns, runSearch, getSearch } from "../api/client";
import { ProductCard } from "./ProductCard";
import type { RankedListing, ScrapeRun } from "../types";

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

type SortKey = "score" | "price_asc" | "price_desc";
type ConditionFilter = "all" | "new" | "used";

function ResultsTab({
  searchId,
  t,
}: {
  searchId: number;
  lang: string;
  t: (key: string) => string;
}) {
  const qc = useQueryClient();
  const [sort, setSort] = useState<SortKey>("score");
  const [condFilter, setCondFilter] = useState<ConditionFilter>("all");

  // Auto-set condition filter based on search's parsed condition preference
  const { data: searchMeta } = useQuery({
    queryKey: ["search", searchId],
    queryFn: () => getSearch(searchId),
    enabled: searchId > 0,
    staleTime: 60_000,
  });
  useEffect(() => {
    const pq = searchMeta?.parsed_query;
    if (pq?.condition === "used") setCondFilter("used");
    else if (pq?.condition === "new") setCondFilter("new");
    else setCondFilter("all");
  }, [searchMeta?.parsed_query?.condition, searchId]);

  const { data, isLoading } = useQuery({
    queryKey: ["top-listings", searchId],
    queryFn: () => getTopListings(searchId, 50),
    enabled: searchId > 0,
    refetchInterval: 8000,
  });

  const runMut = useMutation({
    mutationFn: () => runSearch(searchId),
    onSuccess: () => {
      setTimeout(() => qc.invalidateQueries({ queryKey: ["top-listings", searchId] }), 2000);
    },
  });

  const sorted = useMemo<RankedListing[]>(() => {
    if (!data) return [];
    let list: RankedListing[];
    if (condFilter === "all") {
      list = data;
    } else if (condFilter === "used") {
      // "unknown" condition = can't determine → include when searching used
      list = data.filter((l) => l.condition === "used" || l.condition === "unknown");
    } else {
      list = data.filter((l) => l.condition === condFilter);
    }
    if (sort === "price_asc") return [...list].sort((a, b) => a.current_price_thb - b.current_price_thb);
    if (sort === "price_desc") return [...list].sort((a, b) => b.current_price_thb - a.current_price_thb);
    return [...list].sort((a, b) => b.score - a.score);
  }, [data, sort, condFilter]);

  // Cheapest new-condition listing per source — used as reference when browsing used items.
  // Strict relevance check: item title must match the majority of search keywords so that
  // broad-fallback results (Canon printer when searching camera, mainboard when searching RAM)
  // are excluded. If no item qualifies, the reference bar is hidden entirely.
  const newRefPrices = useMemo<Array<{ source_id: string; price: number; url: string }>>(() => {
    if (!data) return [];
    const usedExists = data.some((l) => l.condition === "used");
    const showRef = condFilter === "used" || (condFilter === "all" && usedExists);
    if (!showRef) return [];

    // Build relevance tokens from the search's parsed English keywords
    const pq = searchMeta?.parsed_query;
    const refTokens: string[] = [
      ...(pq?.keywords_en ?? []),
      ...(pq?.keywords ?? []),
    ]
      .map((k) => k.toLowerCase().trim())
      .filter((k) => k.length > 1);
    const uniqueTokens = [...new Set(refTokens)];

    // Decide minimum match threshold: at least ceil(n/2) tokens must match (majority)
    const minMatch = uniqueTokens.length > 0 ? Math.ceil(uniqueTokens.length / 2) : 0;

    const isRelevant = (title: string): boolean => {
      if (uniqueTokens.length === 0) return true; // no filter info — allow all
      const lower = title.toLowerCase();
      const matched = uniqueTokens.filter((tok) => lower.includes(tok)).length;
      return matched >= minMatch;
    };

    const bySource: Record<string, { price: number; url: string }> = {};
    for (const l of data) {
      if (l.condition !== "new") continue;
      if (!isRelevant(l.title)) continue;
      if (!bySource[l.source_id] || l.current_price_thb < bySource[l.source_id].price) {
        bySource[l.source_id] = { price: l.current_price_thb, url: l.url };
      }
    }
    return Object.entries(bySource)
      .sort((a, b) => a[1].price - b[1].price)
      .map(([source_id, v]) => ({ source_id, ...v }));
  }, [data, condFilter, searchMeta]);

  if (isLoading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div style={{ height: 36, background: "#e5e7eb", borderRadius: 8, width: "100%" }} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "1rem" }}>
          {[1, 2, 3].map((i) => <SkeletonCard key={i} />)}
        </div>
      </div>
    );
  }

  const hasData = data && data.length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      {/* Controls row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          flexWrap: "wrap",
          padding: "0.5rem 0",
        }}
      >
        {/* Result count */}
        <span style={{ fontSize: "0.813rem", color: COLORS.muted, marginRight: "auto" }}>
          {hasData ? `${sorted.length} / ${data!.length} ${t("results_count") || "results"}` : ""}
        </span>

        {/* Condition filter */}
        {(["all", "new", "used"] as ConditionFilter[]).map((c) => (
          <button
            key={c}
            onClick={() => setCondFilter(c)}
            style={{
              padding: "0.25rem 0.6rem",
              borderRadius: 6,
              border: `1.5px solid ${condFilter === c ? COLORS.primary : COLORS.border}`,
              background: condFilter === c ? COLORS.primary + "14" : "transparent",
              color: condFilter === c ? COLORS.primary : COLORS.muted,
              fontSize: "0.75rem",
              fontWeight: condFilter === c ? 700 : 400,
              cursor: "pointer",
            }}
          >
            {c === "all" ? (t("filter_all") || "All") : c === "new" ? (t("condition_new") || "New") : (t("condition_used") || "Used")}
          </button>
        ))}

        {/* Sort */}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as SortKey)}
          style={{
            padding: "0.25rem 0.5rem",
            borderRadius: 6,
            border: `1.5px solid ${COLORS.border}`,
            fontSize: "0.75rem",
            color: COLORS.text,
            background: COLORS.card,
            cursor: "pointer",
          }}
        >
          <option value="score">{t("sort_score") || "Best match"}</option>
          <option value="price_asc">{t("sort_price_asc") || "Price: low → high"}</option>
          <option value="price_desc">{t("sort_price_desc") || "Price: high → low"}</option>
        </select>

        {/* Run now */}
        <button
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          style={{
            padding: "0.25rem 0.7rem",
            borderRadius: 6,
            background: runMut.isPending ? COLORS.muted : COLORS.success,
            color: "#fff",
            border: "none",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: runMut.isPending ? "not-allowed" : "pointer",
          }}
        >
          {runMut.isPending ? "..." : (t("run_btn") || "Run")}
        </button>
      </div>

      {/* New-price reference bar — shown when browsing used items */}
      {newRefPrices.length > 0 && (
        <div
          style={{
            background: "#eff6ff",
            border: "1px solid #bfdbfe",
            borderRadius: 8,
            padding: "0.5rem 0.75rem",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            flexWrap: "wrap",
            fontSize: "0.8rem",
          }}
        >
          <span style={{ color: "#1e40af", fontWeight: 600, whiteSpace: "nowrap" }}>
            {t("new_ref_label") || "ราคาใหม่อ้างอิง:"}
          </span>
          {newRefPrices.map((r) => (
            <a
              key={r.source_id}
              href={r.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.3rem",
                padding: "0.2rem 0.5rem",
                borderRadius: 5,
                background: "#dbeafe",
                color: "#1d4ed8",
                textDecoration: "none",
                fontWeight: 600,
                whiteSpace: "nowrap",
              }}
            >
              <span style={{ textTransform: "capitalize", fontSize: "0.72rem", opacity: 0.8 }}>
                {r.source_id}
              </span>
              ฿{r.price.toLocaleString()}
            </a>
          ))}
          <span style={{ color: "#64748b", fontSize: "0.72rem" }}>
            {t("new_ref_hint") || "ราคามือ 1 ถูกสุดที่มีในระบบ เพื่อเปรียบเทียบความคุ้มค่า"}
          </span>
        </div>
      )}

      {!hasData ? (
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
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
            gap: "1rem",
          }}
        >
          {sorted.map((listing) => (
            <ProductCard
              key={listing.id}
              listing={listing}
              cheapestNewPrice={newRefPrices.length > 0 ? newRefPrices[0].price : null}
            />
          ))}
        </div>
      )}
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
