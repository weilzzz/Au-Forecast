import { getStore } from "@netlify/blobs";

export const analysisStore = () =>
  getStore({ name: "aurum-analysis", consistency: "strong" });
