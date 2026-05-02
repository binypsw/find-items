export interface StructuredQuery {
  keywords: string[];
  keywords_th: string[];
  keywords_en: string[];
  category: string | null;
  condition: "new" | "used" | "refurbished" | "unknown";
  min_price_thb: number | null;
  max_price_thb: number | null;
  location: string | null;
  exclude_keywords: string[];
  source_filter: string[];
  extra_criteria: Record<string, unknown>;
}

export interface SellerInfo {
  name: string | null;
  rating: number | null;
  review_count: number | null;
  sold_count: number | null;
  is_verified: boolean;
}

export interface Listing {
  id: number;
  product_id: number | null;
  source_id: string;
  external_id: string;
  url: string;
  title: string;
  description: string | null;
  current_price_thb: number;
  price_original: number;
  currency: string;
  condition: string;
  seller_payload: SellerInfo;
  location: string | null;
  image_urls: string[];
  status: "active" | "sold" | "deleted" | "stale" | "error";
  first_seen_at: string;
  last_seen_at: string;
  next_poll_at: string | null;
}

export interface RankedListing extends Listing {
  score: number;
  rank: number;
  pros: string[];
  cons: string[];
  price_change_7d_pct: number | null;
}

export interface PricePoint {
  ts: string;
  price: number;
}

export interface Search {
  id: number;
  name: string;
  raw_query: string;
  parsed_query: StructuredQuery | null;
  schedule_cron: string | null;
  is_active: boolean;
  last_run_at: string | null;
  created_at: string;
}

export interface ScrapeRun {
  id: number;
  search_id: number | null;
  source_id: string;
  started_at: string;
  finished_at: string | null;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  items_found: number;
  items_new: number;
  items_updated: number;
  api_credits_used: number;
}

export interface RunEvent {
  type: "progress" | "item_found" | "error" | "completed";
  run_id: number;
  search_id: number;
  source_id?: string;
  payload: unknown;
}

export interface Source {
  id: string;
  name: string;
  base_url: string;
  tier: "direct" | "browserless" | "managed_api";
  enabled: boolean;
  health_status: string;
  last_success_at: string | null;
  monthly_credit_budget: number;
  credits_used_this_month: number;
  api_provider: string | null;
}

export interface AccountSession {
  id: number;
  source_id: string;
  label: string;
  expires_at: string | null;
  status: "active" | "expired" | "banned" | "needs_refresh";
  last_used_at: string | null;
  last_health_check_at: string | null;
  created_at: string;
}
