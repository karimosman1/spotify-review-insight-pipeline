import { NextResponse } from "next/server";
import { getIssue, getIssueReviews } from "@/lib/db";
export const dynamic = "force-dynamic";
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const issue = await getIssue(id);
  if (!issue) return NextResponse.json({ error: "unknown issue" }, { status: 404 });
  return NextResponse.json({ issue, reviews: await getIssueReviews(id) });
}
