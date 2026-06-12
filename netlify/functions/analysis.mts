import type { Context } from "@netlify/functions";

import { analysisStore } from "./_shared/store.mjs";

const json = (payload: object, status = 200) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json; charset=utf-8",
    },
  });

export default async (request: Request, _context: Context) => {
  if (request.method !== "GET") {
    return json({ error: "method_not_allowed" }, 405);
  }

  try {
    const stored = await analysisStore().get("latest", { type: "json" });
    if (stored) return json(stored);
  } catch {
    // Fall back to the deploy snapshot if storage is temporarily unavailable.
  }

  const snapshot = await fetch(new URL("/analysis.json", request.url));
  if (!snapshot.ok) {
    return json(
      {
        error: "analysis_unavailable",
        message: "分析暂时不可用，请稍后重试。",
      },
      503,
    );
  }
  return json(await snapshot.json());
};
