import axios from "axios";
import type {
  AccountSession,
  Listing,
  NotificationConfig,
  PriceAlert,
  PricePoint,
  PriceStats,
  RankedListing,
  Search,
  SellerRisk,
  Source,
  ScrapeRun,
  StructuredQuery,
} from "../types";

const api = axios.create({ baseURL: "/api" });

// Searches
export const getSearches = () => api.get<Search[]>("/searches").then((r) => r.data);
export const getSearch = (id: number) => api.get<Search>(`/searches/${id}`).then((r) => r.data);
export const createSearch = (body: { name: string; raw_query: string; schedule_cron?: string }) =>
  api.post<Search>("/searches", body).then((r) => r.data);
export const deleteSearch = (id: number) => api.delete(`/searches/${id}`);
export const runSearch = (id: number, source_filter?: string[]) =>
  api.post<{ run_id: number; task_id: string }>(`/searches/${id}/run`, { source_filter }).then((r) => r.data);
export const parseQuery = (raw_query: string) =>
  api.post<StructuredQuery>("/searches/parse", { raw_query }).then((r) => r.data);

// Watchlist
export const getWatchlist = () => api.get<Search[]>("/searches/watchlist").then((r) => r.data);
export const toggleWatchlist = (id: number, watchlist_mode: boolean) =>
  api.patch<Search>(`/searches/${id}/watchlist`, { watchlist_mode }).then((r) => r.data);

// Dashboard
export const getTopListings = (searchId: number, limit = 10) =>
  api.get<RankedListing[]>(`/dashboard/${searchId}/top`, { params: { limit } }).then((r) => r.data);

// Listings
export const getListing = (id: number) => api.get<Listing>(`/listings/${id}`).then((r) => r.data);
export const getPriceHistory = (id: number, range = "30d") =>
  api.get<PricePoint[]>(`/listings/${id}/price-history`, { params: { range } }).then((r) => r.data);
export const getPriceStats = (id: number) =>
  api.get<PriceStats>(`/listings/${id}/price-stats`).then((r) => r.data);
export const getSellerInfo = (id: number) =>
  api.get<SellerRisk>(`/listings/${id}/seller`).then((r) => r.data);

// Sources
export const getSources = () => api.get<Source[]>("/sources").then((r) => r.data);
export const updateSource = (id: string, body: Partial<Source>) =>
  api.patch<Source>(`/sources/${id}`, body).then((r) => r.data);

// Sessions
export const getSessions = () => api.get<AccountSession[]>("/sessions").then((r) => r.data);
export const createSession = (body: { source_id: string; label: string; cookies_json: string }) =>
  api.post<AccountSession>("/sessions", body).then((r) => r.data);
export const updateSession = (id: number, body: { label?: string; cookies_json?: string }) =>
  api.patch<AccountSession>(`/sessions/${id}`, body).then((r) => r.data);
export const deleteSession = (id: number) => api.delete(`/sessions/${id}`);

// Runs
export const getRun = (id: number) => api.get<ScrapeRun>(`/runs/${id}`).then((r) => r.data);
export const getSearchRuns = (searchId: number, limit = 10) =>
  api.get<ScrapeRun[]>(`/searches/${searchId}/runs`, { params: { limit } }).then((r) => r.data);

// Alerts
export const getAlerts = () => api.get<PriceAlert[]>("/alerts").then((r) => r.data);
export const createAlert = (body: { listing_id: number; target_price: number; comparison: string; notify_channels: string[] }) =>
  api.post<PriceAlert>("/alerts", body).then((r) => r.data);
export const updateAlert = (id: number, body: Partial<{ target_price: number; is_active: boolean; notify_channels: string[] }>) =>
  api.patch<PriceAlert>(`/alerts/${id}`, body).then((r) => r.data);
export const deleteAlert = (id: number): Promise<void> =>
  api.delete(`/alerts/${id}`).then(() => undefined);

// Notification config
export const getNotificationConfig = () => api.get<NotificationConfig>("/config/notifications").then((r) => r.data);
export const putNotificationConfig = (body: NotificationConfig) =>
  api.put<NotificationConfig>("/config/notifications", body).then((r) => r.data);

// WebSocket helper
export function createRunWebSocket(token?: string): WebSocket {
  const host = window.location.host;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${host}/ws/runs${token ? `?token=${token}` : ""}`;
  return new WebSocket(url);
}
