import axios from "axios";
import type {
  AccountSession,
  Listing,
  PricePoint,
  RankedListing,
  Search,
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

// Dashboard
export const getTopListings = (searchId: number, limit = 10) =>
  api.get<RankedListing[]>(`/dashboard/${searchId}/top`, { params: { limit } }).then((r) => r.data);

// Listings
export const getListing = (id: number) => api.get<Listing>(`/listings/${id}`).then((r) => r.data);
export const getPriceHistory = (id: number, range = "30d") =>
  api.get<PricePoint[]>(`/listings/${id}/price-history`, { params: { range } }).then((r) => r.data);

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

// WebSocket helper
export function createRunWebSocket(token?: string): WebSocket {
  const host = window.location.host;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${host}/ws/runs${token ? `?token=${token}` : ""}`;
  return new WebSocket(url);
}
