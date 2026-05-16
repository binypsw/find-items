import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getAlerts, deleteAlert, updateAlert } from "../api/client";
import type { PriceAlert } from "../types";

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

function formatPrice(price: number): string {
  return "฿" + price.toLocaleString("th-TH", { minimumFractionDigits: 0 });
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("th-TH", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface AlertRowProps {
  alert: PriceAlert;
  onToggle: (id: number, isActive: boolean) => void;
  onDelete: (id: number) => void;
  isToggling: boolean;
  isDeleting: boolean;
}

function AlertRow({ alert, onToggle, onDelete, isToggling, isDeleting }: AlertRowProps) {
  const { t } = useTranslation();
  const isTriggered = alert.triggered_at !== null;
  const rowOpacity = isTriggered ? 0.6 : 1;

  const comparisonBadge =
    alert.comparison === "lte" ? (
      <span
        style={{
          display: "inline-block",
          padding: "0.15rem 0.45rem",
          borderRadius: 5,
          background: "#dbeafe",
          color: "#1d4ed8",
          fontSize: "0.7rem",
          fontWeight: 700,
          whiteSpace: "nowrap",
        }}
      >
        {"<="} {formatPrice(alert.target_price)}
      </span>
    ) : (
      <span
        style={{
          display: "inline-block",
          padding: "0.15rem 0.45rem",
          borderRadius: 5,
          background: "#dcfce7",
          color: "#15803d",
          fontSize: "0.7rem",
          fontWeight: 700,
          whiteSpace: "nowrap",
        }}
      >
        {"↓"} {alert.target_price}%
      </span>
    );

  const statusBadge = isTriggered ? (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.45rem",
        borderRadius: 5,
        background: "#f3f4f6",
        color: COLORS.muted,
        fontSize: "0.7rem",
        fontWeight: 600,
      }}
    >
      {t("alert_triggered")}
    </span>
  ) : (
    <span
      style={{
        display: "inline-block",
        padding: "0.15rem 0.45rem",
        borderRadius: 5,
        background: "#dcfce7",
        color: "#15803d",
        fontSize: "0.7rem",
        fontWeight: 600,
      }}
    >
      {t("alert_active")}
    </span>
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.75rem",
        padding: "0.75rem 1rem",
        borderBottom: `1px solid ${COLORS.border}`,
        opacity: rowOpacity,
        flexWrap: "wrap",
      }}
    >
      {/* Title + link */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <a
          href={alert.listing_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            fontSize: "0.813rem",
            color: COLORS.primary,
            fontWeight: 500,
            textDecoration: "none",
            display: "block",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
          title={alert.listing_title}
        >
          {alert.listing_title}
        </a>
        {isTriggered && alert.triggered_at && (
          <span style={{ fontSize: "0.7rem", color: COLORS.muted }}>
            {formatDate(alert.triggered_at)}
          </span>
        )}
      </div>

      {/* Comparison badge */}
      <div style={{ flexShrink: 0 }}>{comparisonBadge}</div>

      {/* Status badge */}
      <div style={{ flexShrink: 0 }}>{statusBadge}</div>

      {/* Toggle active button */}
      <button
        onClick={() => onToggle(alert.id, !alert.is_active)}
        disabled={isToggling || isTriggered}
        style={{
          padding: "0.3rem 0.6rem",
          borderRadius: 6,
          border: `1px solid ${COLORS.border}`,
          background: alert.is_active ? COLORS.warning + "22" : COLORS.card,
          color: alert.is_active ? "#92400e" : COLORS.muted,
          cursor: isToggling || isTriggered ? "not-allowed" : "pointer",
          fontSize: "0.75rem",
          fontWeight: 500,
          flexShrink: 0,
          opacity: isToggling ? 0.5 : 1,
        }}
      >
        {alert.is_active ? "⏸" : "▶"}
      </button>

      {/* Delete button */}
      <button
        onClick={() => onDelete(alert.id)}
        disabled={isDeleting}
        style={{
          padding: "0.3rem 0.6rem",
          borderRadius: 6,
          border: `1px solid ${COLORS.error}44`,
          background: COLORS.error + "11",
          color: COLORS.error,
          cursor: isDeleting ? "not-allowed" : "pointer",
          fontSize: "0.75rem",
          fontWeight: 500,
          flexShrink: 0,
          opacity: isDeleting ? 0.5 : 1,
        }}
      >
        🗑
      </button>
    </div>
  );
}

export function AlertsPanel({ enabled = true }: { enabled?: boolean }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const { data: alerts, isLoading } = useQuery({
    queryKey: ["alerts"],
    queryFn: getAlerts,
    enabled,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => deleteAlert(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      updateAlert(id, { is_active }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
    },
  });

  return (
    <div
      style={{
        background: COLORS.card,
        borderRadius: 12,
        border: `1px solid ${COLORS.border}`,
        margin: "1rem",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "0.875rem 1rem",
          borderBottom: `1px solid ${COLORS.border}`,
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
        }}
      >
        <span style={{ fontSize: "1rem" }}>🔔</span>
        <span style={{ fontWeight: 700, fontSize: "0.9rem", color: COLORS.text }}>
          {t("alerts_tab")}
        </span>
        {alerts && alerts.length > 0 && (
          <span
            style={{
              marginLeft: "auto",
              background: COLORS.primary + "1a",
              color: COLORS.primary,
              borderRadius: 12,
              padding: "0.1rem 0.5rem",
              fontSize: "0.75rem",
              fontWeight: 600,
            }}
          >
            {alerts.length}
          </span>
        )}
      </div>

      {/* Content */}
      {isLoading ? (
        <div style={{ padding: "2rem", textAlign: "center", color: COLORS.muted, fontSize: "0.875rem" }}>
          {t("loading")}
        </div>
      ) : !alerts || alerts.length === 0 ? (
        <div
          style={{
            padding: "3rem 1rem",
            textAlign: "center",
            color: COLORS.muted,
            fontSize: "0.875rem",
          }}
        >
          <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>🔕</div>
          {t("alert_no_alerts")}
        </div>
      ) : (
        <div>
          {alerts.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onToggle={(id, is_active) => toggleMutation.mutate({ id, is_active })}
              onDelete={(id) => deleteMutation.mutate(id)}
              isToggling={toggleMutation.isPending && toggleMutation.variables?.id === alert.id}
              isDeleting={deleteMutation.isPending && deleteMutation.variables === alert.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}
