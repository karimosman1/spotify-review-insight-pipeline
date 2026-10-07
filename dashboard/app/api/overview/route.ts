import { NextResponse } from "next/server";
import { getRun, getSeverityMix, getIntentMix } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET() {
  const [run, severity, intent] = await Promise.all([getRun(), getSeverityMix(), getIntentMix()]);
  return NextResponse.json({ run, severity, intent });
}
