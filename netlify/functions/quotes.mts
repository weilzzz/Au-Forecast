import type { Context } from "@netlify/functions";

const YAHOO_INTRADAY =
  "https://query1.finance.yahoo.com/v8/finance/chart/GC%3DF?range=5d&interval=5m&includePrePost=true";
const GOLD_SPOT = "https://api.gold-api.com/price/XAU";

type Quote = {
  symbol: string;
  name: string;
  price: number;
  unit: string;
  previous_close: number | null;
  previous_close_note?: string;
  open: number | null;
  day_high: number | null;
  day_low: number | null;
  change: number | null;
  change_percent: number | null;
  updated_at: string;
  source_name: string;
  source_url: string;
  market_open: boolean;
  contract?: string;
};

const round = (value: number | null, digits = 4) =>
  value === null || !Number.isFinite(value)
    ? null
    : Number(value.toFixed(digits));

const percentChange = (current: number, previous: number | null) =>
  previous === null || previous === 0
    ? null
    : ((current / previous) - 1) * 100;

const json = (payload: object, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });

const secondSunday = (year: number, month: number) => {
  const first = new Date(Date.UTC(year, month, 1));
  return 1 + ((7 - first.getUTCDay()) % 7) + 7;
};

const firstSunday = (year: number, month: number) => {
  const first = new Date(Date.UTC(year, month, 1));
  return 1 + ((7 - first.getUTCDay()) % 7);
};

const isMetalsMarketOpen = (now = new Date()) => {
  const year = now.getUTCFullYear();
  const dstStart = Date.UTC(year, 2, secondSunday(year, 2), 7);
  const dstEnd = Date.UTC(year, 10, firstSunday(year, 10), 6);
  const offsetHours =
    now.getTime() >= dstStart && now.getTime() < dstEnd ? -4 : -5;
  const local = new Date(now.getTime() + offsetHours * 60 * 60 * 1000);
  const weekday = local.getUTCDay();
  const hour = local.getUTCHours() + local.getUTCMinutes() / 60;

  if (weekday === 6) return false;
  if (weekday === 0) return hour >= 18;
  if (weekday === 5) return hour < 17;
  return !(hour >= 17 && hour < 18);
};

const fetchJson = async (url: string) => {
  const response = await fetch(url, {
    headers: { "user-agent": "AurumSignal/1.0" },
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error("upstream request failed");
  return response.json() as Promise<Record<string, unknown>>;
};

const fetchSpot = async (marketOpen: boolean): Promise<Quote> => {
  const payload = await fetchJson(GOLD_SPOT);
  const price = Number(payload.price);
  if (!Number.isFinite(price)) throw new Error("spot price unavailable");

  return {
    symbol: "XAUUSD",
    name: "国际现货黄金",
    price,
    unit: "USD/oz",
    previous_close: null,
    previous_close_note: "场外现货市场没有统一官方收盘价",
    open: null,
    day_high: null,
    day_low: null,
    change: null,
    change_percent: null,
    updated_at:
      typeof payload.updatedAt === "string"
        ? payload.updatedAt
        : new Date().toISOString(),
    source_name: "Gold API",
    source_url: GOLD_SPOT,
    market_open: marketOpen,
  };
};

const fetchComex = async (marketOpen: boolean): Promise<Quote> => {
  const payload = await fetchJson(YAHOO_INTRADAY);
  const chart = payload.chart as
    | {
        result?: Array<{
          meta?: Record<string, unknown>;
          timestamp?: number[];
          indicators?: {
            quote?: Array<{
              open?: Array<number | null>;
              high?: Array<number | null>;
              low?: Array<number | null>;
              close?: Array<number | null>;
            }>;
          };
        }>;
      }
    | undefined;
  const result = chart?.result?.[0];
  const meta = result?.meta ?? {};
  const timestamps = result?.timestamp ?? [];
  const values = result?.indicators?.quote?.[0] ?? {};
  const closes = values.close ?? [];
  const offset = Number(meta.gmtoffset ?? -4 * 3600);
  const points = timestamps.flatMap((timestamp, index) => {
    const close = closes[index];
    if (close === null || close === undefined) return [];
    return [{
      timestamp,
      sessionDate: new Date((timestamp + offset) * 1000)
        .toISOString()
        .slice(0, 10),
      open: values.open?.[index] ?? null,
      high: values.high?.[index] ?? null,
      low: values.low?.[index] ?? null,
      close,
    }];
  });
  const latest = points.at(-1);
  if (!latest) throw new Error("futures price unavailable");

  const session = points.filter(
    (point) => point.sessionDate === latest.sessionDate,
  );
  const previousValue = meta.chartPreviousClose ?? meta.previousClose;
  const previousClose =
    typeof previousValue === "number" ? previousValue : null;
  const regularPrice = meta.regularMarketPrice;
  const current =
    typeof regularPrice === "number" ? regularPrice : latest.close;
  const opens = session
    .map((point) => point.open)
    .filter((value): value is number => value !== null);
  const highs = session
    .map((point) => point.high)
    .filter((value): value is number => value !== null);
  const lows = session
    .map((point) => point.low)
    .filter((value): value is number => value !== null);
  const marketTime =
    typeof meta.regularMarketTime === "number"
      ? meta.regularMarketTime
      : latest.timestamp;

  return {
    symbol: "COMEX GC",
    name: "COMEX黄金期货",
    contract: "GC连续主力",
    price: round(current) ?? current,
    unit: "USD/oz",
    previous_close: round(previousClose),
    open: round(opens.at(0) ?? null),
    day_high: round(highs.length ? Math.max(...highs) : null),
    day_low: round(lows.length ? Math.min(...lows) : null),
    change: round(previousClose === null ? null : current - previousClose),
    change_percent: round(percentChange(current, previousClose)),
    updated_at: new Date(marketTime * 1000).toISOString(),
    source_name: "Yahoo Finance",
    source_url: "https://finance.yahoo.com/quote/GC%3DF",
    market_open: marketOpen,
  };
};

export default async (request: Request, _context: Context) => {
  if (request.method !== "GET") {
    return json({ error: "method_not_allowed" }, 405);
  }

  const marketOpen = isMetalsMarketOpen();
  const [spot, comex] = await Promise.allSettled([
    fetchSpot(marketOpen),
    fetchComex(marketOpen),
  ]);
  const quotes: Record<string, Quote> = {};
  const errors: Record<string, string> = {};

  if (spot.status === "fulfilled") quotes.xauusd = spot.value;
  else errors.xauusd = "Live spot quote is temporarily unavailable.";
  if (comex.status === "fulfilled") quotes.comex_gc = comex.value;
  else errors.comex_gc = "Live futures quote is temporarily unavailable.";

  return json({
    schema_version: "1.0.0",
    interval_seconds: 300,
    market_open: marketOpen,
    fetched_at: new Date().toISOString(),
    quotes,
    errors,
    stale: Object.keys(quotes).length === 0,
  });
};
