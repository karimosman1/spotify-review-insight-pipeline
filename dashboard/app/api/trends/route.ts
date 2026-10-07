import { NextResponse } from "next/server";
import { getTrends } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({ trends: await getTrends() });
}
