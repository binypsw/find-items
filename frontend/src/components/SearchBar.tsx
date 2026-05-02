import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSearch, runSearch, parseQuery } from "../api/client";
import type { StructuredQuery } from "../types";

const COLORS = {
  primary: "#2563eb",
  bg: "#f9fafb",
  border: "#e5e7eb",
  text: "#374151",
  muted: "#6b7280",
  card: "#fff",
  success: "#16a34a",
  warning: "#f59e0b",
};

interface SearchBarProps {
  onSearchCreated?: (searchId: number) => void;
}

export function SearchBar({ onSearchCreated }: SearchBarProps) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [parsed, setParsed] = useState<StructuredQuery | null>(null);
  const [isParsing, setIsParsing] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const createMut = useMutation({
    mutationFn: (raw_query: string) =>
      createSearch({ name: raw_query.slice(0, 40), raw_query }),
    onSuccess: async (newSearch) => {
      qc.invalidateQueries({ queryKey: ["searches"] });
      setQuery("");
      setParsed(null);
      // immediately trigger a run
      try {
        await runSearch(newSearch.id);
        qc.invalidateQueries({ queryKey: ["searches"] });
        qc.invalidateQueries({ queryKey: ["runs", newSearch.id] });
      } catch {
        // run failure is non-fatal
      }
      if (onSearchCreated) onSearchCreated(newSearch.id);
    },
  });

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim() || query.trim().length < 3) {
      setParsed(null);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setIsParsing(true);
      try {
        const result = await parseQuery(query.trim());
        setParsed(result);
      } catch {
        setParsed(null);
      } finally {
        setIsParsing(false);
      }
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const formatPrice = (price: number) =>
    "฿" + price.toLocaleString("th-TH", { minimumFractionDigits: 0 });

  const conditionColor: Record<string, string> = {
    new: COLORS.success,
    used: COLORS.warning,
    refurbished: "#8b5cf6",
    unknown: COLORS.muted,
  };

  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (query.trim() && !createMut.isPending) {
            createMut.mutate(query.trim());
          }
        }}
        style={{ display: "flex", gap: "0.5rem" }}
      >
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("search_placeholder")}
          style={{
            flex: 1,
            padding: "0.75rem 1rem",
            borderRadius: 10,
            border: `1.5px solid ${COLORS.border}`,
            fontSize: "1rem",
            outline: "none",
            color: COLORS.text,
            background: COLORS.card,
          }}
        />
        <button
          type="submit"
          disabled={createMut.isPending || !query.trim()}
          style={{
            padding: "0.75rem 1.5rem",
            borderRadius: 10,
            background: createMut.isPending ? "#93c5fd" : COLORS.primary,
            color: "#fff",
            border: "none",
            cursor: createMut.isPending || !query.trim() ? "not-allowed" : "pointer",
            fontSize: "1rem",
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          {createMut.isPending ? (
            <span>
              <Spinner /> {t("loading")}
            </span>
          ) : (
            t("search_btn")
          )}
        </button>
      </form>

      {/* Parsed preview */}
      {(isParsing || parsed) && (
        <div
          style={{
            marginTop: "0.5rem",
            padding: "0.75rem 1rem",
            background: COLORS.bg,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 8,
            fontSize: "0.813rem",
            color: COLORS.text,
          }}
        >
          {isParsing ? (
            <span style={{ color: COLORS.muted }}>
              <Spinner /> {i18n.language === "th" ? "วิเคราะห์..." : "Analyzing..."}
            </span>
          ) : parsed ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center" }}>
              <span style={{ fontWeight: 600, color: COLORS.muted, marginRight: "0.25rem" }}>
                {t("parsed_preview_title")}
              </span>
              {parsed.keywords.length > 0 && (
                <span>
                  <Tag color={COLORS.primary}>{t("keywords_label")}</Tag>{" "}
                  {parsed.keywords.join(", ")}
                </span>
              )}
              {parsed.condition && parsed.condition !== "unknown" && (
                <span>
                  <Tag color={conditionColor[parsed.condition] ?? COLORS.muted}>
                    {t("condition_label")}
                  </Tag>{" "}
                  {parsed.condition}
                </span>
              )}
              {parsed.max_price_thb !== null && (
                <span>
                  <Tag color={COLORS.warning}>{t("max_price_label")}</Tag>{" "}
                  {formatPrice(parsed.max_price_thb)}
                </span>
              )}
            </div>
          ) : null}
        </div>
      )}

      {createMut.isError && (
        <p style={{ color: "#ef4444", fontSize: "0.813rem", marginTop: "0.25rem" }}>
          {i18n.language === "th" ? "เกิดข้อผิดพลาด กรุณาลองใหม่" : "Error creating search, please try again."}
        </p>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <span
      style={{
        display: "inline-block",
        width: 12,
        height: 12,
        border: "2px solid currentColor",
        borderTopColor: "transparent",
        borderRadius: "50%",
        verticalAlign: "middle",
        marginRight: 4,
      }}
    />
  );
}

function Tag({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.1rem 0.4rem",
        borderRadius: 4,
        background: color + "22",
        color,
        fontWeight: 600,
        fontSize: "0.75rem",
      }}
    >
      {children}
    </span>
  );
}
