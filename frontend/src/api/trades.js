import client from "./client";
import { recentTrades } from "../data/demoData";

export async function fetchTrades() {
  try {
    const { data } = await client.get("/api/trades");
    return { data: data?.trades || recentTrades, error: null };
  } catch (error) {
    return { data: recentTrades, error };
  }
}
