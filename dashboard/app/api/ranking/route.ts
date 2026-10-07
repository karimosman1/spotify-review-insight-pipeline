import { NextResponse } from "next/server";
import { getRanking, getClaims } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET() {
  const [ranking, claims] = await Promise.all([getRanking(), getClaims()]);
  return NextResponse.json({ ranking, claims });
}
