import { NextResponse } from "next/server";
import { getEvals } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({ metrics: await getEvals() });
}
