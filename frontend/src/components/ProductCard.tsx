import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PriceHistoryChart } from "./PriceHistoryChart";
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
  const [showChart, setShowChart] = useState(false);

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
              {priceChangePct! < 0 ? "this week" : "this week"}
            </span>
          )}
          {/* % cheaper vs cheapest new — shown on used cards when reference price exists */}
          {listing.condition === "used" && cheapestNewPrice != null && cheapestNewPrice > 0 && (
            (() => {
              const pct = ((cheapestNewPrice - listing.current_price_thb) / cheapestNewPrice) * 100;
              if (pct <= 0) return null;
              return (
                <span
                  title={`ราคามือ 1 ถูกสุด: ฿${cheapestNewPrice.toLocaleString()}`}
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
                  ถูกกว่ามือ 1 {pct.toFixed(0)}%
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
            <span>{t("score_label")}</span>
            <span>{Math.round(scorePercent)}</span>
          </div>
          <div
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

        {/* Chart toggle + View button */}
        <div style={{ display: "flex", gap: "0.375rem" }}>
          <button
            onClick={() => setShowChart((v) => !v)}
            style={{
              flex: 1,
              padding: "0.35rem 0",
              borderRadius: 6,
              border: `1px solid ${COLORS.border}`,
              background: showChart ? COLORS.bg : COLORS.card,
              color: COLORS.text,
              cursor: "pointer",
              fontSize: "0.75rem",
              fontWeight: 500,
            }}
          >
            {showChart ? "Hide Chart" : "Price Chart"}
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

        {/* Inline price chart */}
        {showChart && (
          <div style={{ marginTop: "0.25rem", overflowX: "auto" }}>
            <PriceHistoryChart listingId={listing.id} />
          </div>
        )}
      </div>
    </div>
  );
}
