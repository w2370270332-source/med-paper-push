import { NextResponse } from "next/server";

const GITHUB_TOKEN = process.env.GH_PAT || "";
const REPO = "w2370270332-source/med-paper-push";

async function triggerWorkflow(filename: string) {
  if (!GITHUB_TOKEN) return false;
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${filename}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "master" }),
      },
    );
    return resp.ok || resp.status === 204;
  } catch {
    return false;
  }
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const mode = url.searchParams.get("mode") || "daily";
  const now = new Date();
  const results: string[] = [];

  if (mode === "daily") {
    // Vercel cron 只负责弥补 GitHub cron 的空窗：每天 8:00 北京触发日报
    const ok = await triggerWorkflow("daily-push.yml");
    results.push(`daily: ${ok ? "ok" : "fail"}`);
  } else if (mode === "weekly") {
    const ok = await triggerWorkflow("weekly-push.yml");
    results.push(`weekly: ${ok ? "ok" : "fail"}`);
  } else if (mode === "force-distribute") {
    // 手动调试用：传入 force=true
    const force = url.searchParams.get("force") === "true";
    const ok = await triggerWorkflow("distribute.yml");
    results.push(`distribute: ${ok ? "ok" : "fail"} (force=${force})`);
  }

  return NextResponse.json({ ok: true, results, time: now.toISOString() });
}
