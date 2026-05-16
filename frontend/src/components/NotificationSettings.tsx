import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { getNotificationConfig, putNotificationConfig } from "../api/client";

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

export function NotificationSettings({ enabled = true }: { enabled?: boolean }) {
  const { t } = useTranslation();
  const [webhookUrl, setWebhookUrl] = useState<string>("");
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const { data: config, isLoading } = useQuery({
    queryKey: ["notification-config"],
    queryFn: getNotificationConfig,
    enabled,
  });

  // Sync loaded config into local state
  useEffect(() => {
    if (config !== undefined) {
      setWebhookUrl(config.discord_webhook_url ?? "");
    }
  }, [config]);

  const saveMutation = useMutation({
    mutationFn: () =>
      putNotificationConfig({ discord_webhook_url: webhookUrl.trim() || null }),
    onSuccess: () => {
      setFeedback({ type: "success", message: t("notif_save_success") });
      setTimeout(() => setFeedback(null), 3000);
    },
    onError: () => {
      setFeedback({ type: "error", message: t("notif_save_error") });
      setTimeout(() => setFeedback(null), 4000);
    },
  });

  return (
    <div
      style={{
        background: COLORS.card,
        borderRadius: 12,
        border: `1px solid ${COLORS.border}`,
        margin: "0 1rem 1rem",
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
        <span style={{ fontSize: "1rem" }}>⚙️</span>
        <span style={{ fontWeight: 700, fontSize: "0.9rem", color: COLORS.text }}>
          {t("notification_settings_title")}
        </span>
      </div>

      {/* Form */}
      <div style={{ padding: "1rem", display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <label
            htmlFor="discord-webhook"
            style={{ fontSize: "0.813rem", fontWeight: 600, color: COLORS.text }}
          >
            {t("discord_webhook_label")}
          </label>
          <input
            id="discord-webhook"
            type="url"
            value={isLoading ? "" : webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
            placeholder="https://discord.com/api/webhooks/..."
            disabled={isLoading}
            style={{
              padding: "0.5rem 0.75rem",
              borderRadius: 6,
              border: `1px solid ${COLORS.border}`,
              fontSize: "0.813rem",
              color: COLORS.text,
              background: isLoading ? COLORS.bg : COLORS.card,
              outline: "none",
              width: "100%",
              boxSizing: "border-box",
            }}
          />
        </div>

        {/* Feedback message */}
        {feedback && (
          <div
            style={{
              padding: "0.4rem 0.75rem",
              borderRadius: 6,
              background: feedback.type === "success" ? "#dcfce7" : "#fee2e2",
              color: feedback.type === "success" ? "#15803d" : COLORS.error,
              fontSize: "0.75rem",
              fontWeight: 500,
            }}
          >
            {feedback.type === "success" ? "✓ " : "✗ "}
            {feedback.message}
          </div>
        )}

        {/* Save button */}
        <div>
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending || isLoading}
            style={{
              padding: "0.45rem 1.25rem",
              borderRadius: 6,
              border: "none",
              background: saveMutation.isPending ? COLORS.primary + "88" : COLORS.primary,
              color: "#fff",
              cursor: saveMutation.isPending || isLoading ? "not-allowed" : "pointer",
              fontSize: "0.813rem",
              fontWeight: 600,
            }}
          >
            {saveMutation.isPending ? t("saving") : t("save_btn")}
          </button>
        </div>
      </div>
    </div>
  );
}
