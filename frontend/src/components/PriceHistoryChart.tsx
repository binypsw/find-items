import { useQuery } from "@tanstack/react-query";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { getPriceHistory } from "../api/client";
import type { PricePoint } from "../types";

interface PriceHistoryChartProps {
  listingId: number;
  range?: "7d" | "30d" | "90d" | "all";
}

function formatDateLabel(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function formatPrice(price: number): string {
  return "฿" + price.toLocaleString("th-TH", { minimumFractionDigits: 0 });
}

export function PriceHistoryChart({ listingId, range = "30d" }: PriceHistoryChartProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["price-history", listingId, range],
    queryFn: () => getPriceHistory(listingId, range),
    enabled: listingId > 0,
  });

  if (isLoading) {
    return (
      <div
        style={{
          width: 400,
          height: 180,
          background: "#f3f4f6",
          borderRadius: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.75rem",
          color: "#6b7280",
        }}
      >
        Loading chart...
      </div>
    );
  }

  if (isError || !data || data.length === 0) {
    return (
      <div
        style={{
          width: 400,
          height: 180,
          background: "#f9fafb",
          borderRadius: 8,
          border: "1px dashed #e5e7eb",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: "0.75rem",
          color: "#9ca3af",
        }}
      >
        No price history
      </div>
    );
  }

  const chartData = data.map((p: PricePoint) => ({
    date: formatDateLabel(p.ts),
    price: p.price,
  }));

  return (
    <ResponsiveContainer width={400} height={180}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: "#6b7280" }}
          tickLine={false}
          axisLine={{ stroke: "#e5e7eb" }}
        />
        <YAxis
          tickFormatter={(v: number) => formatPrice(v)}
          tick={{ fontSize: 10, fill: "#6b7280" }}
          tickLine={false}
          axisLine={false}
          width={70}
        />
        <Tooltip
          formatter={(value: number) => [formatPrice(value), "Price"]}
          labelStyle={{ fontSize: 11, color: "#374151" }}
          contentStyle={{
            fontSize: 11,
            borderRadius: 6,
            border: "1px solid #e5e7eb",
            background: "#fff",
          }}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke="#2563eb"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: "#2563eb" }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
