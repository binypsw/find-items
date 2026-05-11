import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { createRunWebSocket } from "../api/client";
import type { RunEvent } from "../types";

const COLORS = {
  success: "#16a34a",
  error: "#ef4444",
  primary: "#2563eb",
  warning: "#f59e0b",
  bg: "#f9fafb",
  border: "#e5e7eb",
  text: "#374151",
  muted: "#6b7280",
  card: "#fff",
};

const EVENT_STYLE: Record<string, { bg: string; color: string; icon: string }> = {
  item_found: { bg: COLORS.success + "15", color: COLORS.success, icon: "✓" },
  error: { bg: COLORS.error + "15", color: COLORS.error, icon: "✕" },
  completed: { bg: COLORS.primary + "15", color: COLORS.primary, icon: "✓✓" },
  progress: { bg: COLORS.warning + "15", color: COLORS.warning, icon: "⟳" },
};

interface FeedEntry {
  id: number;
  event: RunEvent;
  ts: Date;
}

export function LiveFeed() {
  const { t, i18n } = useTranslation();
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);

  useEffect(() => {
    let ws: WebSocket;
    let retryTimer: ReturnType<typeof setTimeout>;

    function connect() {
      try {
        ws = createRunWebSocket();

        ws.onopen = () => {
          ws.send(JSON.stringify({ subscribe: "all" }));
          setConnected(true);
        };
        ws.onclose = () => {
          setConnected(false);
          retryTimer = setTimeout(connect, 5000);
        };
        ws.onerror = () => ws.close();

        ws.onmessage = (msg) => {
          try {
            const event: RunEvent = JSON.parse(msg.data);
            setEntries((prev) => {
              const next = [...prev, { id: ++seqRef.current, event, ts: new Date() }];
              return next.slice(-50); // keep last 50
            });
          } catch {
            /* ignore malformed */
          }
        };
      } catch {
        retryTimer = setTimeout(connect, 5000);
      }
    }

    connect();

    return () => {
      clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  // Always auto-scroll to bottom on new entries (terminal-like)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [entries]);

  const formatTime = (d: Date) =>
    d.toLocaleTimeString(i18n.language === "th" ? "th-TH" : "en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  return (
    <div style={{ padding: "1rem", display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "0.75rem",
        }}
      >
        <h3 style={{ margin: 0, fontSize: "1rem", fontWeight: 700, color: COLORS.text }}>
          {t("live_feed_title")}
        </h3>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: connected ? COLORS.success : COLORS.error,
              display: "inline-block",
            }}
          />
          <span style={{ fontSize: "0.75rem", color: COLORS.muted }}>
            {connected
              ? i18n.language === "th"
                ? "เชื่อมต่อแล้ว"
                : "Connected"
              : i18n.language === "th"
              ? "ไม่ได้เชื่อมต่อ"
              : "Disconnected"}
          </span>
        </div>
      </div>

      {/* Feed */}
      <div
        ref={containerRef}
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "0.3rem",
        }}
      >
        {entries.length === 0 ? (
          <p style={{ color: COLORS.muted, fontSize: "0.813rem", textAlign: "center", padding: "1rem" }}>
            {t("no_live_events")}
          </p>
        ) : (
          entries.map((entry) => {
            const style = EVENT_STYLE[entry.event.type] ?? EVENT_STYLE.progress;
            const payload = entry.event.payload as Record<string, unknown>;
            const label =
              entry.event.type === "item_found"
                ? `${entry.event.source_id} — ${(payload?.title as string)?.slice(0, 40) ?? ""}`
                : entry.event.type === "completed"
                ? `${entry.event.source_id} completed (${payload?.items_found ?? 0} items)`
                : entry.event.type === "error"
                ? `${entry.event.source_id}: ${(payload?.error as string)?.slice(0, 50) ?? "error"}`
                : `run ${entry.event.run_id}`;

            return (
              <div
                key={entry.id}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "0.5rem",
                  padding: "0.3rem 0.6rem",
                  borderRadius: 6,
                  background: style.bg,
                  fontSize: "0.75rem",
                }}
              >
                <span style={{ fontWeight: 700, color: style.color, flexShrink: 0 }}>
                  {style.icon}
                </span>
                <span style={{ color: COLORS.muted, flexShrink: 0 }}>
                  {formatTime(entry.ts)}
                </span>
                <span style={{ color: COLORS.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {label}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
