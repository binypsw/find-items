import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { PriceHistoryChart } from "./PriceHistoryChart";
import { getPriceStats, createAlert } from "../api/client";
import type { RankedListing } from "../types";

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

const SOURCE_COLORS: Record<string, string> = {
  shopee: "#f97316",
  lazada: "#2563eb",
  kaidee: "#16a34a",
  jib: "#dc2626",
  bnn: "#0f766e",
  advice: "#7c3aed",
  priceza: "#0369a1",
};

const CONDITION_COLORS: Record<string, string> = {
  new: COLORS.success,
  used: COLORS.warning,
  refurbished: "#8b5cf6",
  unknown: COLORS.muted,
};

function formatPrice(price: number): string {
  return "฿" + price.toLocaleString("th-TH", { minimumFractionDigits: 0 });
}

interface ProductCardProps {
  listing: RankedListing;
  cheapestNewPrice?: number | null; // reference new price for used-item comparison
}

export function ProductCard({ listing, cheapestNewPrice }: ProductCardProps) {
  const { t } = useTranslation();
  const [modalOpen, setModalOpen] = useState(false);
  const [range, setRange] = useState<"7d" | "30d" | "90d" | "all">("30d");
  const [alertModalOpen, setAlertModalOpen] = useState(false);
  const [alertComparison, setAlertComparison] = useState<"lte" | "pct_drop">("lte");
  const [alertTarget, setAlertTarget] = useState("");
  const [alertSaved, setAlertSaved] = useState(false);

  const { data: priceStats } = useQuery({
    queryKey: ["price-stats", listing.id],
    queryFn: () => getPriceStats(listing.id),
    enabled: modalOpen,
  });

  const alertMutation = useMutation({
    mutationFn: () =>
      createAlert({
        listing_id: listing.id,
        target_price: parseFloat(alertTarget),
        comparison: alertComparison,
        notify_channels: ["discord"],
      }),
    onSuccess: () => {
      setAlertSaved(true);
      setTimeout(() => {
        setAlertModalOpen(false);
        setAlertSaved(false);
        setAlertTarget("");
        setAlertComparison("lte");
      }, 1200);
    },
  });

  const sourceColor = SOURCE_COLORS[listing.source_id.toLowerCase()] ?? COLORS.primary;
  const conditionColor = CONDITION_COLORS[listing.condition] ?? COLORS.muted;
  const imageUrl = listing.image_urls && listing.image_urls.length > 0 ? listing.image_urls[0] : null;
  const scorePercent = Math.max(0, Math.min(100, listing.score * 100));
  const scoreBarColor =
    scorePercent >= 70 ? COLORS.success : scorePercent >= 40 ? COLORS.warning : COLORS.error;

  const priceChangePct = listing.price_change_7d_pct;
  const hasPriceChange = priceChangePct !== null && priceChangePct !== undefined;

  return (
    <div
      style={{
        background: COLORS.card,
        borderRadius: 12,
        border: `1px solid ${COLORS.border}`,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      }}
    >
      {/* Image */}
      <div
        style={{
          height: 160,
          background: imageUrl ? "transparent" : "#f3f4f6",
          overflow: "hidden",
          position: "relative",
          flexShrink: 0,
        }}
      >
        {imageUrl ? (
          <img
            src={imageUrl}
            alt={listing.title}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div
            style={{
              width: "100%",
              height: "100%",
              background: "#e5e7eb",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: COLORS.muted,
              fontSize: "2rem",
            }}
          >
            🖼
          </div>
        )}
        {/* Source badge overlay */}
        <span
          style={{
            position: "absolute",
            top: 8,
            right: 8,
            padding: "0.2rem 0.45rem",
            borderRadius: 5,
            background: sourceColor,
            color: "#fff",
            fontSize: "0.7rem",
            fontWeight: 700,
            textTransform: "capitalize",
          }}
        >
          {listing.source_id}
        </span>
      </div>

      {/* Body */}
      <div style={{ padding: "0.75rem", flex: 1, display: "flex", flexDirection: "column", gap: "0.375rem" }}>
        <p
          style={{
            margin: 0,
            fontSize: "0.813rem",
            color: COLORS.text,
            fontWeight: 500,
            lineHeight: 1.4,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
          title={listing.title}
        >
          {listing.title}
        </p>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
          <span
            style={{
              fontSize: "1.125rem",
              fontWeight: 700,
              color: COLORS.success,
            }}
          >
            {formatPrice(listing.current_price_thb)}
          </span>
          {hasPriceChange && (
            <span
              style={{
                fontSize: "0.75rem",
                fontWeight: 600,
                color: priceChangePct! < 0 ? COLORS.success : COLORS.error,
              }}
            >
              {priceChangePct! < 0 ? "↓" : "↑"}{" "}
              {Math.abs(priceChangePct!).toFixed(1)}%{" "}
              {t("price_change_period")}
            </span>
          )}
          {/* % cheaper vs cheapest new — shown on used/unknown cards when reference price exists */}
          {(listing.condition === "used" || listing.condition === "unknown") && cheapestNewPrice != null && cheapestNewPrice > 0 && (
            (() => {
              const pct = ((cheapestNewPrice - listing.current_price_thb) / cheapestNewPrice) * 100;
              if (pct <= 0) return null;
              return (
                <span
                  title={t("cheapest_new_tooltip", { price: cheapestNewPrice.toLocaleString() })}
                  style={{
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    color: "#1d4ed8",
                    background: "#dbeafe",
                    padding: "0.1rem 0.35rem",
                    borderRadius: 4,
                    whiteSpace: "nowrap",
                  }}
                >
                  {t("cheaper_than_new", { pct: pct.toFixed(0) })}
                </span>
              );
            })()
          )}
        </div>

        {/* Condition badge */}
        <div>
          <span
            style={{
              display: "inline-block",
              padding: "0.15rem 0.45rem",
              borderRadius: 5,
              background: conditionColor + "22",
              color: conditionColor,
              fontSize: "0.7rem",
              fontWeight: 600,
              textTransform: "capitalize",
            }}
          >
            {listing.condition}
          </span>
        </div>
      </div>

      {/* Score + footer */}
      <div
        style={{
          padding: "0.5rem 0.75rem 0.75rem",
          borderTop: `1px solid ${COLORS.border}`,
          display: "flex",
          flexDirection: "column",
          gap: "0.5rem",
        }}
      >
        {/* Score bar */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: "0.7rem",
              color: COLORS.muted,
              marginBottom: "0.2rem",
            }}
          >
            <span
              title="Score = keyword relevance (50%) + price vs. market avg (30%) + condition match (20%)"
              style={{ cursor: "help" }}
            >
              {t("score_label")}
            </span>
            <span>{Math.round(scorePercent)}</span>
          </div>
          <div
            title="Score = keyword relevance (50%) + price vs. market avg (30%) + condition match (20%)"
            style={{
              height: 5,
              background: "#e5e7eb",
              borderRadius: 3,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${scorePercent}%`,
                height: "100%",
                background: scoreBarColor,
                borderRadius: 3,
              }}
            />
          </div>
        </div>

        {/* Chart modal trigger + Set Alert + View button */}
        <div style={{ display: "flex", gap: "0.375rem" }}>
          <button
            onClick={() => setModalOpen(true)}
            style={{
              flex: 1,
              padding: "0.35rem 0",
              borderRadius: 6,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.card,
              color: COLORS.text,
              cursor: "pointer",
              fontSize: "0.75rem",
              fontWeight: 500,
            }}
          >
            📈 {t("price_history_title")}
          </button>
          <button
            onClick={() => setAlertModalOpen(true)}
            style={{
              flex: 1,
              padding: "0.35rem 0",
              borderRadius: 6,
              border: `1px solid ${COLORS.border}`,
              background: COLORS.card,
              color: COLORS.text,
              cursor: "pointer",
              fontSize: "0.75rem",
              fontWeight: 500,
            }}
          >
            🔔 {t("set_alert_title")}
          </button>
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              flex: 1,
              padding: "0.35rem 0",
              borderRadius: 6,
              background: COLORS.primary,
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontSize: "0.75rem",
              fontWeight: 600,
              textAlign: "center",
              textDecoration: "none",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {t("view_btn")} ↗
          </a>
        </div>

        {/* Set Alert Modal */}
        {alertModalOpen && (
          <div
            onClick={() => setAlertModalOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.5)",
              zIndex: 1000,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "#fff",
                borderRadius: 12,
                padding: "1.25rem",
                maxWidth: 400,
                width: "90%",
                display: "flex",
                flexDirection: "column",
                gap: "0.875rem",
              }}
            >
              {/* Modal header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <span style={{ fontWeight: 700, fontSize: "0.9rem", color: COLORS.text }}>
                  🔔 {t("set_alert_title")}
                </span>
                <button
                  onClick={() => setAlertModalOpen(false)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "1.1rem",
                    color: COLORS.muted,
                    padding: "0 0.25rem",
                    flexShrink: 0,
                    lineHeight: 1,
                  }}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>

              {/* Listing title preview */}
              <div
                style={{
                  fontSize: "0.75rem",
                  color: COLORS.muted,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
                title={listing.title}
              >
                {listing.title}
              </div>

              {/* Comparison type selector */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {(
                  [
                    { value: "lte", label: t("set_alert_lte_label") },
                    { value: "pct_drop", label: t("set_alert_pct_label") },
                  ] as const
                ).map(({ value, label }) => (
                  <label
                    key={value}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      cursor: "pointer",
                      fontSize: "0.813rem",
                      color: COLORS.text,
                      padding: "0.4rem 0.6rem",
                      borderRadius: 6,
                      border: `1px solid ${alertComparison === value ? COLORS.primary : COLORS.border}`,
                      background: alertComparison === value ? COLORS.primary + "0d" : COLORS.card,
                    }}
                  >
                    <input
                      type="radio"
                      name={`alert-comparison-${listing.id}`}
                      value={value}
                      checked={alertComparison === value}
                      onChange={() => {
                        setAlertComparison(value);
                        setAlertTarget("");
                      }}
                      style={{ accentColor: COLORS.primary }}
                    />
                    {label}
                  </label>
                ))}
              </div>

              {/* Target value input */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                <input
                  type="number"
                  min={0}
                  step={alertComparison === "lte" ? 1 : 0.1}
                  value={alertTarget}
                  onChange={(e) => setAlertTarget(e.target.value)}
                  placeholder={alertComparison === "lte" ? "1500" : "10"}
                  style={{
                    padding: "0.5rem 0.75rem",
                    borderRadius: 6,
                    border: `1px solid ${COLORS.border}`,
                    fontSize: "0.875rem",
                    color: COLORS.text,
                    outline: "none",
                    width: "100%",
                    boxSizing: "border-box",
                  }}
                />
              </div>

              {/* Success state */}
              {alertSaved && (
                <div
                  style={{
                    padding: "0.4rem 0.75rem",
                    borderRadius: 6,
                    background: "#dcfce7",
                    color: "#15803d",
                    fontSize: "0.75rem",
                    fontWeight: 500,
                  }}
                >
                  ✓ {t("alert_saved_confirmation")}
                </div>
              )}

              {/* Action buttons */}
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  onClick={() => alertMutation.mutate()}
                  disabled={
                    alertMutation.isPending ||
                    alertSaved ||
                    !alertTarget ||
                    isNaN(parseFloat(alertTarget)) ||
                    parseFloat(alertTarget) <= 0
                  }
                  style={{
                    flex: 1,
                    padding: "0.45rem 0",
                    borderRadius: 6,
                    border: "none",
                    background:
                      alertMutation.isPending || alertSaved || !alertTarget
                        ? COLORS.primary + "88"
                        : COLORS.primary,
                    color: "#fff",
                    cursor:
                      alertMutation.isPending || alertSaved || !alertTarget
                        ? "not-allowed"
                        : "pointer",
                    fontSize: "0.813rem",
                    fontWeight: 600,
                  }}
                >
                  {alertMutation.isPending ? t("saving") : t("set_alert_save")}
                </button>
                <button
                  onClick={() => setAlertModalOpen(false)}
                  style={{
                    flex: 1,
                    padding: "0.45rem 0",
                    borderRadius: 6,
                    border: `1px solid ${COLORS.border}`,
                    background: COLORS.card,
                    color: COLORS.text,
                    cursor: "pointer",
                    fontSize: "0.813rem",
                    fontWeight: 500,
                  }}
                >
                  {t("cancel_btn")}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Price History Modal */}
        {modalOpen && (
          <div
            onClick={() => setModalOpen(false)}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0,0,0,0.5)",
              zIndex: 1000,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "#fff",
                borderRadius: 12,
                padding: "1.25rem",
                maxWidth: 600,
                width: "90%",
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              {/* Modal header */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
                <span
                  style={{
                    fontWeight: 600,
                    fontSize: "0.9rem",
                    color: COLORS.text,
                    maxWidth: 400,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={listing.title}
                >
                  {listing.title}
                </span>
                <button
                  onClick={() => setModalOpen(false)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "1.1rem",
                    color: COLORS.muted,
                    padding: "0 0.25rem",
                    flexShrink: 0,
                    lineHeight: 1,
                  }}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>

              {/* Range selector */}
              <div style={{ display: "flex", gap: "0.375rem" }}>
                {(["7d", "30d", "90d", "all"] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRange(r)}
                    style={{
                      padding: "0.25rem 0.6rem",
                      borderRadius: 6,
                      border: `1px solid ${range === r ? COLORS.primary : COLORS.border}`,
                      background: range === r ? COLORS.primary : COLORS.card,
                      color: range === r ? "#fff" : COLORS.text,
                      cursor: "pointer",
                      fontSize: "0.75rem",
                      fontWeight: range === r ? 600 : 400,
                    }}
                  >
                    {t(`range_${r}`)}
                  </button>
                ))}
              </div>

              {/* Price stats row */}
              {priceStats && priceStats.price_min != null && (
                <div style={{ fontSize: "0.75rem", color: COLORS.muted }}>
                  {t("price_stats_min")} {formatPrice(priceStats.price_min)}
                  {" · "}
                  {t("price_stats_avg")} {formatPrice(priceStats.price_avg ?? 0)}
                  {" · "}
                  {t("price_stats_max")} {formatPrice(priceStats.price_max ?? 0)}
                </div>
              )}

              {/* Fake sale warning */}
              {priceStats?.is_likely_fake_sale && (
                <div
                  style={{
                    background: "#fffbeb",
                    border: "1px solid #f59e0b",
                    borderRadius: 6,
                    padding: "0.5rem 0.75rem",
                    fontSize: "0.75rem",
                    color: "#92400e",
                  }}
                >
                  <strong>{t("fake_sale_badge")}</strong>
                  {priceStats.fake_sale_reason && (
                    <span>
                      {" "}{t("fake_sale_reason_label")} {priceStats.fake_sale_reason}
                    </span>
                  )}
                </div>
              )}

              {/* Chart */}
              <PriceHistoryChart listingId={listing.id} range={range} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
