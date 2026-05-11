import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSources, getSessions, createSession, updateSession, deleteSession } from "../api/client";
import type { AccountSession } from "../types";

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

const STATUS_BADGE: Record<AccountSession["status"], { bg: string; color: string }> = {
  active: { bg: "#dcfce7", color: "#16a34a" },
  expired: { bg: "#fef3c7", color: "#d97706" },
  banned: { bg: "#fee2e2", color: "#dc2626" },
  needs_refresh: { bg: "#ffedd5", color: "#ea580c" },
};

const SOURCE_OPTIONS = ["shopee", "lazada", "kaidee", "jib", "bnn", "priceza", "facebook"];

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

type ModalMode = { type: "add" } | { type: "edit"; session: AccountSession } | null;

interface SessionsPanelProps {
  enabled?: boolean;
}

export function SessionsPanel({ enabled = true }: SessionsPanelProps) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [modal, setModal] = useState<ModalMode>(null);

  // Form state
  const [formLabel, setFormLabel] = useState("");
  const [formSource, setFormSource] = useState(SOURCE_OPTIONS[0]);
  const [formCookies, setFormCookies] = useState("");
  const [mutError, setMutError] = useState<string | null>(null);

  const { data: sources } = useQuery({ queryKey: ["sources"], queryFn: getSources });
  const sourceIds = sources?.map((s) => s.id) ?? SOURCE_OPTIONS;

  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: getSessions,
    enabled,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteSession(id),
    onSuccess: () => {
      setDeletingId(null);
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: () => setDeletingId(null),
  });

  const createMut = useMutation({
    mutationFn: (body: { source_id: string; label: string; cookies_json: string }) =>
      createSession(body),
    onSuccess: () => {
      closeModal();
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : "Failed to create session";
      setMutError(msg);
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { label?: string; cookies_json?: string } }) =>
      updateSession(id, body),
    onSuccess: () => {
      closeModal();
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : "Failed to update session";
      setMutError(msg);
    },
  });

  function openAdd() {
    setFormLabel("");
    setFormSource(sourceIds[0] ?? SOURCE_OPTIONS[0]);
    setFormCookies("");
    setMutError(null);
    setModal({ type: "add" });
  }

  function openEdit(session: AccountSession) {
    setFormLabel(session.label);
    setFormSource(session.source_id);
    setFormCookies("");
    setMutError(null);
    setModal({ type: "edit", session });
  }

  function closeModal() {
    setModal(null);
    setMutError(null);
  }

  function handleSave() {
    setMutError(null);
    if (!formLabel.trim()) {
      setMutError("Label is required");
      return;
    }
    if (modal?.type === "add") {
      if (!formCookies.trim()) {
        setMutError("Cookies JSON is required");
        return;
      }
      createMut.mutate({
        source_id: formSource,
        label: formLabel.trim(),
        cookies_json: formCookies.trim(),
      });
    } else if (modal?.type === "edit") {
      const body: { label?: string; cookies_json?: string } = {
        label: formLabel.trim(),
      };
      if (formCookies.trim()) {
        body.cookies_json = formCookies.trim();
      }
      updateMut.mutate({ id: modal.session.id, body });
    }
  }

  const isMutating = createMut.isPending || updateMut.isPending;

  return (
    <div style={{ padding: "1.5rem" }}>
      {/* Header row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "1rem",
        }}
      >
        <h2
          style={{
            fontSize: "1rem",
            fontWeight: 700,
            color: COLORS.text,
            margin: 0,
          }}
        >
          {t("sessions_panel_title")}
        </h2>
        <button
          onClick={openAdd}
          style={{
            padding: "0.35rem 0.85rem",
            borderRadius: 6,
            background: COLORS.primary,
            color: "#fff",
            border: "none",
            cursor: "pointer",
            fontSize: "0.813rem",
            fontWeight: 600,
          }}
        >
          + {t("add_session_btn", "Add Session")}
        </button>
      </div>

      {isLoading ? (
        <p style={{ color: COLORS.muted, fontSize: "0.875rem" }}>{t("loading")}</p>
      ) : !sessions || sessions.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            color: COLORS.muted,
            fontSize: "0.875rem",
            padding: "3rem 1rem",
          }}
        >
          No account sessions — add cookies via API to enable authenticated scraping
        </div>
      ) : (
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
                <Th>{t("col_label")}</Th>
                <Th>Source</Th>
                <Th>{t("col_status_session")}</Th>
                <Th>{t("col_last_used")}</Th>
                <Th>{t("col_expires")}</Th>
                <Th></Th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((session: AccountSession) => {
                const badge = STATUS_BADGE[session.status] ?? {
                  bg: "#f3f4f6",
                  color: COLORS.muted,
                };
                return (
                  <tr
                    key={session.id}
                    style={{ borderBottom: `1px solid ${COLORS.border}` }}
                  >
                    <Td>{session.label}</Td>
                    <Td>{session.source_id}</Td>
                    <Td>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "0.15rem 0.5rem",
                          borderRadius: 5,
                          background: badge.bg,
                          color: badge.color,
                          fontWeight: 600,
                          fontSize: "0.75rem",
                          textTransform: "capitalize",
                        }}
                      >
                        {session.status.replace("_", " ")}
                      </span>
                    </Td>
                    <Td>{formatDate(session.last_used_at)}</Td>
                    <Td>{formatDate(session.expires_at)}</Td>
                    <Td>
                      <div style={{ display: "flex", gap: "0.4rem" }}>
                        <button
                          onClick={() => openEdit(session)}
                          style={{
                            padding: "0.2rem 0.5rem",
                            borderRadius: 4,
                            background: "#f3f4f6",
                            color: COLORS.text,
                            border: `1px solid ${COLORS.border}`,
                            cursor: "pointer",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                          }}
                        >
                          {t("edit_btn", "Edit")}
                        </button>
                        <button
                          onClick={() => {
                            if (
                              window.confirm(
                                t("delete_confirm", { label: session.label })
                              )
                            ) {
                              setDeletingId(session.id);
                              deleteMut.mutate(session.id);
                            }
                          }}
                          disabled={deletingId === session.id}
                          style={{
                            padding: "0.2rem 0.5rem",
                            borderRadius: 4,
                            background:
                              deletingId === session.id ? "#fca5a5" : COLORS.error,
                            color: "#fff",
                            border: "none",
                            cursor:
                              deletingId === session.id ? "not-allowed" : "pointer",
                            fontSize: "0.7rem",
                            fontWeight: 600,
                          }}
                        >
                          {t("delete_btn")}
                        </button>
                      </div>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal overlay */}
      {modal !== null && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal();
          }}
        >
          <div
            style={{
              background: COLORS.card,
              borderRadius: 10,
              padding: "1.75rem 2rem",
              width: "100%",
              maxWidth: 480,
              boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
            }}
          >
            <h3
              style={{
                margin: "0 0 1.25rem 0",
                fontSize: "1rem",
                fontWeight: 700,
                color: COLORS.text,
              }}
            >
              {modal.type === "add"
                ? t("add_session_title", "Add Session")
                : t("edit_session_title", "Edit Session")}
            </h3>

            {/* Label field */}
            <label
              style={{
                display: "block",
                fontSize: "0.813rem",
                fontWeight: 600,
                color: COLORS.text,
                marginBottom: "0.3rem",
              }}
            >
              {t("field_label", "Label")}
            </label>
            <input
              type="text"
              value={formLabel}
              onChange={(e) => setFormLabel(e.target.value)}
              style={{
                width: "100%",
                padding: "0.45rem 0.65rem",
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                fontSize: "0.875rem",
                color: COLORS.text,
                marginBottom: "1rem",
                boxSizing: "border-box",
              }}
            />

            {/* Source field */}
            <label
              style={{
                display: "block",
                fontSize: "0.813rem",
                fontWeight: 600,
                color: COLORS.text,
                marginBottom: "0.3rem",
              }}
            >
              {t("field_source", "Source")}
            </label>
            {modal.type === "add" ? (
              <select
                value={formSource}
                onChange={(e) => setFormSource(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.45rem 0.65rem",
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 6,
                  fontSize: "0.875rem",
                  color: COLORS.text,
                  marginBottom: "1rem",
                  background: COLORS.card,
                  boxSizing: "border-box",
                }}
              >
                {sourceIds.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            ) : (
              <div
                style={{
                  padding: "0.45rem 0.65rem",
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 6,
                  fontSize: "0.875rem",
                  color: COLORS.muted,
                  marginBottom: "1rem",
                  background: COLORS.bg,
                }}
              >
                {modal.session.source_id}
              </div>
            )}

            {/* Cookies JSON field */}
            <label
              style={{
                display: "block",
                fontSize: "0.813rem",
                fontWeight: 600,
                color: COLORS.text,
                marginBottom: "0.3rem",
              }}
            >
              {t("field_cookies", "Cookies JSON")}
            </label>
            <textarea
              rows={6}
              value={formCookies}
              onChange={(e) => setFormCookies(e.target.value)}
              placeholder={
                modal.type === "edit"
                  ? 'Paste new cookies to replace (leave empty to keep existing)'
                  : '[{"name":"...","value":"..."}]'
              }
              style={{
                width: "100%",
                padding: "0.45rem 0.65rem",
                border: `1px solid ${COLORS.border}`,
                borderRadius: 6,
                fontSize: "0.75rem",
                fontFamily: "monospace",
                color: COLORS.text,
                resize: "vertical",
                marginBottom: "1rem",
                boxSizing: "border-box",
              }}
            />

            {/* Inline error */}
            {mutError && (
              <div
                style={{
                  padding: "0.5rem 0.75rem",
                  background: "#fee2e2",
                  color: COLORS.error,
                  borderRadius: 6,
                  fontSize: "0.813rem",
                  marginBottom: "1rem",
                }}
              >
                {mutError}
              </div>
            )}

            {/* Action buttons */}
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "0.6rem",
              }}
            >
              <button
                onClick={closeModal}
                disabled={isMutating}
                style={{
                  padding: "0.45rem 1rem",
                  borderRadius: 6,
                  background: COLORS.bg,
                  color: COLORS.text,
                  border: `1px solid ${COLORS.border}`,
                  cursor: isMutating ? "not-allowed" : "pointer",
                  fontSize: "0.813rem",
                  fontWeight: 600,
                }}
              >
                {t("cancel_btn", "Cancel")}
              </button>
              <button
                onClick={handleSave}
                disabled={isMutating}
                style={{
                  padding: "0.45rem 1rem",
                  borderRadius: 6,
                  background: isMutating ? "#93c5fd" : COLORS.primary,
                  color: "#fff",
                  border: "none",
                  cursor: isMutating ? "not-allowed" : "pointer",
                  fontSize: "0.813rem",
                  fontWeight: 600,
                }}
              >
                {isMutating ? t("saving", "Saving…") : t("save_btn", "Save")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Th({ children }: { children?: React.ReactNode }) {
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

function Td({ children }: { children?: React.ReactNode }) {
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
