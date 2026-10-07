import { NextResponse } from "next/server";
import { getMemo, getAlternatives, getClaims, getReviewsByIds } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET() {
  const memo = await getMemo();
  if (!memo) return NextResponse.json({ error: "no memo loaded" }, { status: 404 });
  const [alternatives, claims, cited] = await Promise.all([
    getAlternatives(memo.id), getClaims(), getReviewsByIds(memo.cited_review_ids),
  ]);
  return NextResponse.json({ memo, alternatives, claims, cited_reviews: cited });
}
