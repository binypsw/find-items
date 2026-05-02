import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSources, updateSource } from "../api/client";
import type { Source } from "../types";

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

const TIER_COLORS: Record<string, string> = {
  direct: COLORS.success,
  browserless: COLORS.warning,
  managed_api: COLORS.primary,
};

const HEALTH_COLORS: Record<string, string> = {
  ok: COLORS.success,
  degraded: COLORS.warning,
  down: COLORS.error,
  unknown: COLORS.muted,
};

export function SourcesPanel() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();

  const { data: sources = [], isLoading } = useQuery({
    queryKey: ["sources"],
    queryFn: getSources,
    refetchInterval: 30000,
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSource(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sources"] }),
  });

  const formatDate = (d: string | null) =>
    d
      ? new Date(d).toLocaleDateString(i18n.language === "th" ? "th-TH" : "en-US", {
          month: "short",
          day: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "—";

  if (isLoading) {
    return <p style={{ color: COLORS.muted, fontSize: "0.875rem", padding: "1rem" }}>{t("loading")}</p>;
  }

  return (
    <div style={{ padding: "1rem" }}>
      <h3
        style={{
          margin: "0 0 1rem",
          fontSize: "1rem",
          fontWeight: 700,
          color: COLORS.text,
        }}
      >
        {t("sources_panel_title")}
      </h3>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {sources.map((source: Source) => {
          const budget = source.monthly_credit_budget || 0;
          const used = source.credits_used_this_month || 0;
          const pct = budget > 0 ? Math.min(100, (used / budget) * 100) : 0;
          const barColor =
            pct >= 90 ? COLORS.error : pct >= 70 ? COLORS.warning : COLORS.success;

          return (
            <div
              key={source.id}
              style={{
                background: COLORS.card,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 10,
                padding: "0.875rem",
                opacity: source.enabled ? 1 : 0.55,
              }}
            >
              {/* Header row */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span style={{ fontWeight: 700, fontSize: "0.875rem", color: COLORS.text }}>
                    {source.name}
                  </span>
                  <Badge color={TIER_COLORS[source.tier] ?? COLORS.muted}>{source.tier}</Badge>
                  <Badge color={HEALTH_COLORS[source.health_status] ?? COLORS.muted}>
                    {source.health_status}
                  </Badge>
                </div>

                {/* Enable/disable toggle */}
                <label
                  style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer" }}
                >
                  <input
                    type="checkbox"
                    checked={source.enabled}
                    onChange={(e) =>
                      toggleMut.mutate({ id: source.id, enabled: e.target.checked })
                    }
                    style={{ cursor: "pointer", width: 16, height: 16 }}
                  />
                  <span style={{ fontSize: "0.75rem", color: COLORS.muted }}>
                    {source.enabled
                      ? i18n.language === "th"
                        ? "เปิด"
                        : "On"
                      : i18n.language === "th"
                      ? "ปิด"
                      : "Off"}
                  </span>
                </label>
              </div>

              {/* Credit bar */}
              {budget > 0 && (
                <div style={{ marginBottom: "0.4rem" }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.75rem",
                      color: COLORS.muted,
                      marginBottom: "0.25rem",
                    }}
                  >
                    <span>{t("credits_used_label")}</span>
                    <span>
                      {used.toLocaleString()} / {budget.toLocaleString()}
                    </span>
                  </div>
                  <div
                    style={{
                      height: 6,
                      background: COLORS.bg,
                      borderRadius: 3,
                      border: `1px solid ${COLORS.border}`,
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${pct}%`,
                        background: barColor,
                        borderRadius: 3,
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Last success */}
              <div style={{ fontSize: "0.75rem", color: COLORS.muted }}>
                {i18n.language === "th" ? "สำเร็จล่าสุด" : "Last success"}:{" "}
                {formatDate(source.last_success_at)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Badge({
  children,
  color,
}: {
  children: React.ReactNode;
  color: string;
}) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.1rem 0.45rem",
        borderRadius: 5,
        background: color + "20",
        color,
        fontWeight: 600,
        fontSize: "0.7rem",
        textTransform: "capitalize",
      }}
    >
      {children}
    </span>
  );
}
