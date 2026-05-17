import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSearches, runSearch, deleteSearch, toggleWatchlist } from "../api/client";
import type { Search } from "../types";

const COLORS = {
  primary: "#2563eb",
  success: "#16a34a",
  error: "#ef4444",
  bg: "#f9fafb",
  border: "#e5e7eb",
  text: "#374151",
  muted: "#6b7280",
  card: "#fff",
};

interface SavedSearchesProps {
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function relativeTime(dateStr: string, lang: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (lang === "th") {
    if (minutes < 1) return "เพิ่งรัน";
    if (minutes < 60) return `${minutes} นาทีที่แล้ว`;
    if (hours < 24) return `${hours} ชั่วโมงที่แล้ว`;
    return `${days} วันที่แล้ว`;
  } else {
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  }
}

export function SavedSearches({ selectedId, onSelect }: SavedSearchesProps) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [runError, setRunError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [isRunningAll, setIsRunningAll] = useState(false);
  const runErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const deleteErrorTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (runErrorTimer.current) clearTimeout(runErrorTimer.current);
      if (deleteErrorTimer.current) clearTimeout(deleteErrorTimer.current);
    };
  }, []);

  const { data: searches = [], isLoading } = useQuery({
    queryKey: ["searches"],
    queryFn: getSearches,
  });

  const runMut = useMutation({
    mutationFn: (id: number) => runSearch(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to run search";
      setRunError(msg);
      if (runErrorTimer.current) clearTimeout(runErrorTimer.current);
      runErrorTimer.current = setTimeout(() => setRunError(null), 5000);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSearch(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to delete search";
      setDeleteError(msg);
      if (deleteErrorTimer.current) clearTimeout(deleteErrorTimer.current);
      deleteErrorTimer.current = setTimeout(() => setDeleteError(null), 5000);
    },
  });

  const watchlistMut = useMutation({
    mutationFn: ({ id, mode }: { id: number; mode: boolean }) => toggleWatchlist(id, mode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });

  const runAll = async () => {
    setIsRunningAll(true);
    try {
      for (const s of searches) {
        try {
          await runSearch(s.id);
        } catch {
          // continue
        }
      }
      qc.invalidateQueries({ queryKey: ["searches"] });
    } finally {
      setIsRunningAll(false);
    }
  };

  const regularSearches = searches.filter((s: Search) => !s.watchlist_mode);
  const watchlistSearches = searches.filter((s: Search) => s.watchlist_mode);

  return (
    <aside
      style={{
        width: 240,
        minWidth: 200,
        background: COLORS.card,
        borderRight: `1px solid ${COLORS.border}`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "0.75rem 1rem",
          borderBottom: `1px solid ${COLORS.border}`,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
        }}
      >
        <span style={{ fontWeight: 700, fontSize: "0.875rem", color: COLORS.text }}>
          {i18n.language === "th" ? "การค้นหาที่บันทึก" : "Saved Searches"}
        </span>
        <button
          onClick={runAll}
          disabled={searches.length === 0 || isRunningAll || runMut.isPending}
          style={{
            padding: "0.25rem 0.6rem",
            borderRadius: 6,
            background: COLORS.success,
            color: "#fff",
            border: "none",
            cursor: searches.length === 0 ? "not-allowed" : "pointer",
            fontSize: "0.75rem",
            fontWeight: 600,
            opacity: searches.length === 0 ? 0.5 : 1,
          }}
        >
          {t("run_all")}
        </button>
      </div>

      {/* Error toasts */}
      {runError && (
        <div style={{ padding: "0.25rem 1rem", fontSize: "0.75rem", color: COLORS.error }}>
          {runError}
        </div>
      )}
      {deleteError && (
        <div style={{ padding: "0.25rem 1rem", fontSize: "0.75rem", color: COLORS.error }}>
          {deleteError}
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0" }}>
        {isLoading ? (
          <div style={{ padding: "1rem", color: COLORS.muted, fontSize: "0.813rem" }}>
            {t("loading")}
          </div>
        ) : searches.length === 0 ? (
          <div style={{ padding: "1rem", color: COLORS.muted, fontSize: "0.813rem" }}>
            {t("no_searches")}
          </div>
        ) : (
          <>
            {regularSearches.map((s: Search) => (
              <SearchRow
                key={s.id}
                search={s}
                isSelected={selectedId === s.id}
                lang={i18n.language}
                onSelect={() => onSelect(s.id)}
                onRun={() => runMut.mutate(s.id)}
                onDelete={() => deleteMut.mutate(s.id)}
                onToggleWatch={() =>
                  watchlistMut.mutate({ id: s.id, mode: !s.watchlist_mode })
                }
                isRunning={runMut.isPending && runMut.variables === s.id}
                isDeleting={deleteMut.isPending && deleteMut.variables === s.id}
                isTogglingWatch={
                  watchlistMut.isPending &&
                  (watchlistMut.variables as { id: number } | undefined)?.id === s.id
                }
                t={t}
              />
            ))}

            {/* Watchlist section */}
            <hr style={{ margin: "0.5rem 0", border: "none", borderTop: "1px solid #e5e7eb" }} />
            <div
              style={{
                padding: "0.5rem 1rem 0.25rem",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: COLORS.text,
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
              }}
            >
              <span>{t("watchlist_title")}</span>
              {watchlistSearches.length > 0 && (
                <span
                  style={{
                    background: "#dbeafe",
                    color: COLORS.primary,
                    borderRadius: 10,
                    padding: "0 0.375rem",
                    fontSize: "0.688rem",
                    fontWeight: 700,
                  }}
                >
                  {watchlistSearches.length}
                </span>
              )}
            </div>

            {watchlistSearches.length === 0 ? (
              <div style={{ padding: "0.25rem 1rem 0.5rem", fontSize: "0.75rem", color: COLORS.muted }}>
                {t("watchlist_empty")}
              </div>
            ) : (
              watchlistSearches.map((s: Search) => (
                <SearchRow
                  key={s.id}
                  search={s}
                  isSelected={selectedId === s.id}
                  lang={i18n.language}
                  onSelect={() => onSelect(s.id)}
                  onRun={() => runMut.mutate(s.id)}
                  onDelete={() => deleteMut.mutate(s.id)}
                  onToggleWatch={() =>
                    watchlistMut.mutate({ id: s.id, mode: !s.watchlist_mode })
                  }
                  isRunning={runMut.isPending && runMut.variables === s.id}
                  isDeleting={deleteMut.isPending && deleteMut.variables === s.id}
                  isTogglingWatch={
                    watchlistMut.isPending &&
                    (watchlistMut.variables as { id: number } | undefined)?.id === s.id
                  }
                  t={t}
                />
              ))
            )}
          </>
        )}
      </div>
    </aside>
  );
}

interface SearchRowProps {
  search: Search;
  isSelected: boolean;
  lang: string;
  onSelect: () => void;
  onRun: () => void;
  onDelete: () => void;
  onToggleWatch: () => void;
  isRunning: boolean;
  isDeleting: boolean;
  isTogglingWatch: boolean;
  t: (key: string) => string;
}

function SearchRow({
  search,
  isSelected,
  lang,
  onSelect,
  onRun,
  onDelete,
  onToggleWatch,
  isRunning,
  isDeleting,
  isTogglingWatch,
  t,
}: SearchRowProps) {
  const isWatched = search.watchlist_mode;

  return (
    <div
      onClick={onSelect}
      style={{
        padding: "0.625rem 1rem",
        cursor: "pointer",
        borderLeft: isSelected ? `3px solid ${COLORS.primary}` : "3px solid transparent",
        background: isSelected ? COLORS.primary + "0d" : "transparent",
        borderBottom: `1px solid ${COLORS.border}`,
        transition: "background 0.15s",
      }}
    >
      <div
        style={{
          fontSize: "0.813rem",
          fontWeight: isSelected ? 600 : 400,
          color: COLORS.text,
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
          marginBottom: "0.25rem",
          display: "flex",
          alignItems: "center",
          gap: "0.25rem",
        }}
        title={search.raw_query}
      >
        {isWatched && (
          <span
            title={lang === "th" ? "เฝ้าดูอยู่" : "Watching"}
            style={{ fontSize: "0.75rem", flexShrink: 0 }}
          >
            {"🔔"}
          </span>
        )}
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {search.raw_query}
        </span>
      </div>
      <div
        style={{
          fontSize: "0.75rem",
          color: COLORS.muted,
          marginBottom: "0.375rem",
        }}
      >
        {search.last_run_at ? relativeTime(search.last_run_at, lang) : "—"}
      </div>
      <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRun();
          }}
          disabled={isRunning}
          style={{
            padding: "0.2rem 0.5rem",
            borderRadius: 4,
            background: isRunning ? "#86efac" : COLORS.success,
            color: "#fff",
            border: "none",
            cursor: isRunning ? "not-allowed" : "pointer",
            fontSize: "0.7rem",
            fontWeight: 600,
          }}
        >
          {isRunning ? "..." : t("run_btn")}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleWatch();
          }}
          disabled={isTogglingWatch}
          title={
            isWatched
              ? lang === "th"
                ? "หยุดเฝ้าดู"
                : "Stop watching"
              : lang === "th"
              ? "เฝ้าดูสินค้าใหม่"
              : "Watch for new items"
          }
          style={{
            padding: "0.2rem 0.5rem",
            borderRadius: 4,
            background: isWatched ? "#dbeafe" : "#f3f4f6",
            color: isWatched ? COLORS.primary : COLORS.muted,
            border: isWatched ? `1px solid ${COLORS.primary}` : "1px solid #d1d5db",
            cursor: isTogglingWatch ? "not-allowed" : "pointer",
            fontSize: "0.7rem",
            fontWeight: 600,
            opacity: isTogglingWatch ? 0.6 : 1,
          }}
        >
          {isWatched ? t("watch_btn_on") : t("watch_btn_off")}
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            if (window.confirm(lang === "th" ? "ลบการค้นหานี้?" : "Delete this search?")) {
              onDelete();
            }
          }}
          disabled={isDeleting}
          style={{
            padding: "0.2rem 0.5rem",
            borderRadius: 4,
            background: isDeleting ? "#fca5a5" : COLORS.error,
            color: "#fff",
            border: "none",
            cursor: isDeleting ? "not-allowed" : "pointer",
            fontSize: "0.7rem",
            fontWeight: 600,
          }}
        >
          {t("delete_btn")}
        </button>
      </div>
    </div>
  );
}
