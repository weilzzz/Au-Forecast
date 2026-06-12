import { XMLParser } from "fast-xml-parser";

type MarketItem = {
  symbol?: string;
  price?: number | null;
  value?: number | null;
  change_1d?: number | null;
  change_5d?: number | null;
  volume_change_5avg?: number | null;
  volatility_20d?: number | null;
  updated_at?: string | null;
  source_name?: string;
  source_url?: string;
};

const SYMBOLS: Record<string, string> = {
  gc: "GC=F",
  gld: "GLD",
  sp500: "^GSPC",
  nasdaq: "^IXIC",
  vix: "^VIX",
  dxy: "DX-Y.NYB",
  wti: "CL=F",
  silver: "SI=F",
  copper: "HG=F",
  eurusd: "EURUSD=X",
  gbpusd: "GBPUSD=X",
  audusd: "AUDUSD=X",
  usdjpy: "JPY=X",
  usdcad: "CAD=X",
};

const INDICATOR_META: Record<
  string,
  { sensitivity: number; threshold: number; rationale: string }
> = {
  gc: { sensitivity: 1, threshold: 0.25, rationale: "黄金期货上涨通常直接利多黄金" },
  real_10y: { sensitivity: -1, threshold: 0.03, rationale: "实际利率上升通常提高持有黄金的机会成本" },
  nominal_10y: { sensitivity: -1, threshold: 0.05, rationale: "美债收益率上升通常对无息黄金构成压力" },
  dxy: { sensitivity: -1, threshold: 0.25, rationale: "美元走强通常压制美元计价黄金" },
  sp500: { sensitivity: -1, threshold: 0.5, rationale: "美股走弱可能提升避险需求" },
  nasdaq: { sensitivity: -1, threshold: 0.6, rationale: "成长股走弱可能提升避险需求" },
  vix: { sensitivity: 1, threshold: 2, rationale: "波动率上升通常提升避险需求" },
  gld: { sensitivity: 1, threshold: 0.25, rationale: "GLD价格上涨反映黄金市场价格动能" },
  wti: { sensitivity: 1, threshold: 0.5, rationale: "油价仅作为通胀与商品环境参考，关系并不稳定" },
  silver: { sensitivity: 1, threshold: 0.5, rationale: "白银可作为贵金属风险偏好的参考" },
  copper: { sensitivity: 1, threshold: 0.5, rationale: "铜价仅作为商品广度参考，不直接代表黄金方向" },
};

const clamp = (value: number, low: number, high: number) =>
  Math.max(low, Math.min(high, value));

const round = (value: number | null | undefined, digits = 4) =>
  value === null || value === undefined || !Number.isFinite(value)
    ? null
    : Number(value.toFixed(digits));

const percentChange = (
  current: number | null | undefined,
  previous: number | null | undefined,
) =>
  current === null ||
  current === undefined ||
  previous === null ||
  previous === undefined ||
  previous === 0
    ? null
    : ((current / previous) - 1) * 100;

const fetchText = async (url: string) => {
  const response = await fetch(url, {
    headers: { "user-agent": "AurumSignal/1.0" },
    signal: AbortSignal.timeout(25_000),
  });
  if (!response.ok) throw new Error("upstream request failed");
  return response.text();
};

const fetchJson = async (url: string) =>
  JSON.parse(await fetchText(url)) as Record<string, unknown>;

const yahoo = async (symbol: string): Promise<MarketItem> => {
  const encoded = encodeURIComponent(symbol);
  const payload = await fetchJson(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encoded}?range=3mo&interval=1d`,
  );
  const chart = payload.chart as {
    result?: Array<{
      meta?: Record<string, unknown>;
      timestamp?: number[];
      indicators?: {
        quote?: Array<{
          close?: Array<number | null>;
          volume?: Array<number | null>;
        }>;
      };
    }>;
  };
  const result = chart.result?.[0];
  if (!result) throw new Error("Yahoo data unavailable");
  const meta = result.meta ?? {};
  const timestamps = result.timestamp ?? [];
  const quote = result.indicators?.quote?.[0] ?? {};
  const closes = quote.close ?? [];
  const volumes = quote.volume ?? [];
  const points = timestamps.flatMap((timestamp, index) => {
    const close = closes[index];
    return close === null || close === undefined
      ? []
      : [{ timestamp, close, volume: volumes[index] ?? null }];
  });
  const latest = points.at(-1);
  if (!latest) throw new Error("Yahoo prices unavailable");
  const current =
    typeof meta.regularMarketPrice === "number"
      ? meta.regularMarketPrice
      : latest.close;
  const returns = points.slice(-21).flatMap((point, index, list) => {
    if (index === 0) return [];
    const change = percentChange(point.close, list[index - 1].close);
    return change === null ? [] : [change / 100];
  });
  const mean = returns.reduce((sum, value) => sum + value, 0) / (returns.length || 1);
  const volatility =
    returns.length >= 2
      ? Math.sqrt(
          returns.reduce((sum, value) => sum + ((value - mean) ** 2), 0) /
            returns.length,
        )
      : null;
  const previous = points.at(-2)?.close;
  const fiveDayBase = points.at(-6)?.close;
  const recentVolumes = points
    .slice(-6, -1)
    .map((point) => point.volume)
    .filter((value): value is number => Boolean(value));
  const volumeAverage =
    recentVolumes.length
      ? recentVolumes.reduce((sum, value) => sum + value, 0) / recentVolumes.length
      : null;
  const latestVolume = latest.volume;
  const volumeChange =
    meta.marketState === "REGULAR"
      ? null
      : percentChange(latestVolume, volumeAverage);

  return {
    symbol,
    price: round(current),
    change_1d: round(percentChange(current, previous)),
    change_5d: round(percentChange(current, fiveDayBase)),
    volume_change_5avg: round(volumeChange),
    volatility_20d: round(volatility, 6),
    updated_at: new Date(
      Number(meta.regularMarketTime ?? latest.timestamp) * 1000,
    ).toISOString(),
    source_name: "Yahoo Finance",
    source_url: `https://finance.yahoo.com/quote/${encoded}`,
  };
};

const spot = async (): Promise<MarketItem> => {
  const payload = await fetchJson("https://api.gold-api.com/price/XAU");
  const price = Number(payload.price);
  if (!Number.isFinite(price)) throw new Error("spot price unavailable");
  return {
    symbol: "XAUUSD",
    price,
    updated_at:
      typeof payload.updatedAt === "string"
        ? payload.updatedAt
        : new Date().toISOString(),
    source_name: "Gold API",
    source_url: "https://api.gold-api.com/price/XAU",
  };
};

const treasury = async (
  kind: "real" | "nominal",
): Promise<MarketItem> => {
  const year = new Date().getUTCFullYear();
  const data =
    kind === "real"
      ? "daily_treasury_real_yield_curve"
      : "daily_treasury_yield_curve";
  const field = kind === "real" ? "TC_10YEAR" : "BC_10YEAR";
  const xml = await fetchText(
    `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=${data}&field_tdr_date_value=${year}`,
  );
  const parsed = new XMLParser({ ignoreAttributes: false }).parse(xml) as {
    feed?: { entry?: unknown };
  };
  const entries = parsed.feed?.entry;
  const rows = (Array.isArray(entries) ? entries : entries ? [entries] : [])
    .flatMap((entry) => {
      const properties = (
        entry as {
          content?: {
            "m:properties"?: Record<string, unknown>;
          };
        }
      ).content?.["m:properties"];
      const dateNode = properties?.["d:NEW_DATE"];
      const valueNode = properties?.[`d:${field}`];
      const date =
        typeof dateNode === "string"
          ? dateNode
          : (dateNode as { "#text"?: string } | undefined)?.["#text"];
      const value =
        typeof valueNode === "number" || typeof valueNode === "string"
          ? valueNode
          : (valueNode as { "#text"?: number | string } | undefined)?.["#text"];
      if (typeof date !== "string" || value === undefined) return [];
      const numeric = Number(value);
      return Number.isFinite(numeric)
        ? [{ date: date.slice(0, 10), value: numeric }]
        : [];
    })
    .sort((a, b) => a.date.localeCompare(b.date));
  const latest = rows.at(-1);
  if (!latest) throw new Error("Treasury data unavailable");
  return {
    value: latest.value,
    change_1d: round(latest.value - (rows.at(-2)?.value ?? latest.value)),
    change_5d: round(latest.value - (rows.at(-6)?.value ?? latest.value)),
    updated_at: latest.date,
    source_name: "U.S. Department of the Treasury",
    source_url:
      "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
  };
};

const component = (
  value: number | null | undefined,
  scale: number,
  weight: number,
  inverse = false,
) => {
  if (value === null || value === undefined) return 0;
  return clamp((inverse ? -value : value) / scale, -1, 1) * weight;
};

const scoreDirection = (score: number) => {
  if (score >= 40) return ["强烈看多", "strong_bullish"];
  if (score >= 15) return ["谨慎看多", "cautiously_bullish"];
  if (score <= -40) return ["强烈看空", "strong_bearish"];
  if (score <= -15) return ["谨慎看空", "cautiously_bearish"];
  return ["中性", "neutral"];
};

const factorSignal = (score: number, weight: number) => {
  const ratio = weight ? score / weight : 0;
  if (ratio >= 0.45) return ["偏多", "bullish"];
  if (ratio >= 0.12) return ["轻微偏多", "slightly_bullish"];
  if (ratio <= -0.45) return ["偏空", "bearish"];
  if (ratio <= -0.12) return ["轻微偏空", "slightly_bearish"];
  return ["中性", "neutral"];
};

const manualScore = (
  config: Record<string, unknown>,
  key: string,
  limit: number,
) => {
  const item = config[key] as Record<string, unknown> | undefined;
  const updated = Date.parse(String(item?.updated_at ?? ""));
  const expires = Date.parse(String(item?.expires_at ?? ""));
  const now = Date.now();
  if (!Number.isFinite(updated) || (Number.isFinite(expires) && now > expires)) return 0;
  const value = Number(item?.score ?? 0);
  return Number.isFinite(value) ? clamp(value, -limit, limit) : 0;
};

const goldSignal = (key: string, change: number | null | undefined) => {
  const meta = INDICATOR_META[key];
  if (change === null || change === undefined) {
    return ["数据不足", meta.sensitivity > 0 ? "direct" : "inverse", meta.rationale];
  }
  const adjusted = change * meta.sensitivity;
  const signal =
    adjusted > meta.threshold
      ? "利多黄金"
      : adjusted < -meta.threshold
        ? "利空黄金"
        : "中性";
  return [signal, meta.sensitivity > 0 ? "direct" : "inverse", meta.rationale];
};

export const generateOnlineAnalysis = async (
  snapshot: Record<string, any>,
  config: Record<string, any>,
) => {
  const tasks: Array<[string, Promise<MarketItem>]> = [
    ["spot", spot()],
    ...Object.entries(SYMBOLS).map(
      ([key, symbol]) => [key, yahoo(symbol)] as [string, Promise<MarketItem>],
    ),
    ["real_10y", treasury("real")],
    ["nominal_10y", treasury("nominal")],
  ];
  const settled = await Promise.allSettled(tasks.map(([, task]) => task));
  const data: Record<string, MarketItem> = {};
  const errors: string[] = [];
  settled.forEach((result, index) => {
    const key = tasks[index][0];
    if (result.status === "fulfilled") data[key] = result.value;
    else errors.push(key);
  });
  if (!data.gc?.price && !data.spot?.price) throw new Error("gold price unavailable");

  const fed = Math.round(
    component(data.real_10y?.change_5d, 0.18, 20, true) +
      component(data.nominal_10y?.change_5d, 0.22, 10, true) +
      component(data.dxy?.change_5d, 1.6, 15, true) +
      manualScore(config, "fed_policy", 5),
  );
  const stocks = Math.round(
    component(data.sp500?.change_5d, 2.5, 3, true) +
      component(data.nasdaq?.change_5d, 3, 2, true) +
      component(data.vix?.change_5d, 18, 5),
  );
  const momentum = Math.round(
    component(data.gld?.change_5d, 2.2, 10) +
      component(data.gld?.volume_change_5avg, 35, 5) +
      component(data.gc?.change_5d, 2.2, 10) +
      component(data.gc?.volume_change_5avg, 35, 5),
  );
  const central = Math.round(manualScore(config, "central_bank", 10));
  const factorDefs = [
    ["fed", "美联储政策与利率", 50, fed, "实际收益率、名义收益率、美元和人工政策输入。"],
    ["stocks", "股票与避险情绪", 10, stocks, "标普、纳斯达克与VIX的避险关系。"],
    ["fund_flow", "黄金市场量价动能", 30, momentum, "GLD与COMEX黄金的量价动能，不代表真实资金流。"],
    ["central_bank", "全球央行购金", 10, central, String(config.central_bank?.note ?? "人工治理输入。")],
  ] as const;
  const factors = factorDefs.map(([id, name, weight, score, summary]) => {
    const [signal, signalCode] = factorSignal(score, weight);
    return {
      id,
      name,
      weight,
      score,
      signal,
      signal_code: signalCode,
      summary,
      data_completeness: id === "central_bank" ? (central ? 100 : 0) : 100,
    };
  });
  const score = clamp(factors.reduce((sum, factor) => sum + factor.score, 0), -100, 100);
  let [direction, directionCode] = scoreDirection(score);
  const expectedKeys = ["spot", ...Object.keys(SYMBOLS), "real_10y", "nominal_10y"];
  const completeness = Math.round(
    (expectedKeys.filter((key) => data[key]).length / expectedKeys.length) * 100,
  );
  let strength = Math.round(clamp(20 + completeness * 0.28 + Math.abs(score) * 0.45 - errors.length * 3, 20, 90));
  if (completeness < 70) {
    direction = "数据不足";
    directionCode = "insufficient";
    strength = Math.min(strength, 45);
  }
  const benchmark = data.gc ?? data.spot;
  const price = Number(benchmark.price);
  const volatility =
    data.gc?.volatility_20d && data.gc.volatility_20d > 0
      ? data.gc.volatility_20d
      : 0.012;
  const horizon = Number(config.forecast_horizon_trading_days ?? 5);
  const move = price * volatility * Math.sqrt(Math.max(1, horizon)) * 1.15;
  const now = new Date().toISOString();
  const result = structuredClone(snapshot);

  result.model_version = "rules-v1.2.0-netlify";
  result.current_model_version = "rules-v1.2.0-netlify";
  result.analysis_id = `gold-${now}`;
  result.generated_at = now;
  result.market_as_of = benchmark.updated_at;
  result.instrument = {
    ...result.instrument,
    symbol: data.gc ? "COMEX GC" : "XAUUSD",
    name: data.gc ? "COMEX黄金期货" : "国际现货黄金",
    price: round(price, 2),
    change_percent: data.gc?.change_1d ?? null,
    session: "最新可用行情",
  };
  result.market_quotes = [
    ...(data.spot
      ? [{
          symbol: "XAUUSD",
          name: "国际现货黄金",
          description: "国际现货黄金兑美元报价",
          price: round(data.spot.price, 2),
          unit: "USD/oz",
          change_percent: null,
          updated_at: data.spot.updated_at,
          source_name: data.spot.source_name,
          source_url: data.spot.source_url,
        }]
      : []),
    ...(data.gc
      ? [{
          symbol: "COMEX GC",
          name: "COMEX黄金期货",
          description: "纽约商品交易所黄金连续主力期货",
          contract: "GC连续主力",
          price: data.gc.price,
          unit: "USD/oz",
          change_percent: data.gc.change_1d,
          basis:
            data.spot?.price === null || data.spot?.price === undefined
              ? null
              : round(Number(data.gc.price) - Number(data.spot.price), 2),
          updated_at: data.gc.updated_at,
          source_name: data.gc.source_name,
          source_url: data.gc.source_url,
        }]
      : []),
  ];
  result.forecast = {
    ...result.forecast,
    horizon: `未来${horizon}个交易日`,
    horizon_trading_days: horizon,
    direction,
    direction_code: directionCode,
    score,
    signal_strength: strength,
    confidence: strength,
    confidence_is_probability: false,
    strength_label: "模型一致度",
    strength_method: "启发式规则评分，未经过历史概率校准",
    benchmark_symbol: data.gc ? "COMEX GC" : "XAUUSD",
    benchmark_name: data.gc ? "COMEX黄金期货" : "国际现货黄金",
    benchmark_contract: data.gc?.symbol ?? "XAUUSD",
    benchmark_type: data.gc ? "continuous_front_month" : "spot",
    roll_adjusted: false,
    summary: `四大因子综合评分为${score >= 0 ? "+" : ""}${score}，当前判断为${direction}。数据完整度${completeness}%。`,
    expected_range: {
      low: round(price - move, 2),
      high: round(price + move, 2),
      unit: "USD/oz",
      method: "20日历史波动率启发式区间",
      event_adjusted: false,
      historical_coverage: null,
    },
  };
  result.factors = factors;
  result.events = config.events ?? [];
  result.indicators = (result.indicators ?? []).map((indicator: Record<string, any>) => {
    const item = data[indicator.id];
    const meta = INDICATOR_META[indicator.id];
    if (!item || !meta) {
      return meta
        ? { ...indicator, value: null, change_1d: null, change_5d: null, status: "missing" }
        : indicator;
    }
    const [signal, sensitivity, rationale] = goldSignal(indicator.id, item.change_5d);
    return {
      ...indicator,
      value: item.price ?? item.value ?? null,
      change_1d: item.change_1d ?? null,
      change_5d: item.change_5d ?? null,
      signal,
      gold_sensitivity: sensitivity,
      signal_rationale: rationale,
      updated_at: item.updated_at,
      source_name: item.source_name,
      source_url: item.source_url,
      status: "ok",
    };
  });
  result.data_quality = {
    ...result.data_quality,
    completeness,
    freshness: 100,
    missing_count: errors.length,
    delayed_count: 0,
    delayed_inputs: [],
    oldest_core_data_at: Object.values(data)
      .map((item) => item.updated_at)
      .filter(Boolean)
      .sort()[0] ?? null,
    status: completeness >= 85 ? "good" : completeness >= 70 ? "degraded" : "poor",
    message:
      errors.length === 0
        ? "云端已完成实时在线采集，核心数据源均返回成功。"
        : `云端在线采集完成，部分数据源暂不可用：${errors.join("、")}。`,
  };
  delete result._warning;
  return result;
};
