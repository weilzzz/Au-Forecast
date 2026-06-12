import type { Context } from "@netlify/functions";

import { generateOnlineAnalysis } from "./_shared/online-analysis.mjs";
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
  if (request.method !== "POST") {
    return json({ error: "method_not_allowed" }, 405);
  }

  try {
    const [snapshotResponse, configResponse] = await Promise.all([
      fetch(new URL("/analysis.json", request.url)),
      fetch(new URL("/config.json", request.url)),
    ]);
    if (!snapshotResponse.ok || !configResponse.ok) {
      throw new Error("deploy snapshot unavailable");
    }
    const analysis = await generateOnlineAnalysis(
      await snapshotResponse.json(),
      await configResponse.json(),
    );
    await analysisStore().setJSON("latest", analysis);
    return json(analysis);
  } catch {
    return json(
      {
        error: "refresh_failed",
        message: "云端刷新失败，请稍后重试。",
      },
      503,
    );
  }
};
