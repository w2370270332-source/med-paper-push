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

export async function GET() {
  const now = new Date();
  const beijingHour = (now.getUTCHours() + 8) % 24;
  const beijingMinute = now.getUTCMinutes();
  const weekday = now.getUTCDay(); // 0=Sun
  const results: string[] = [];

  // 每天 8:00 北京时间 → 触发日报
  if (beijingHour === 8 && beijingMinute < 15) {
    const ok = await triggerWorkflow("daily-push.yml");
    results.push(`daily: ${ok ? "ok" : "fail"}`);
  }

  // 周日 20:00 北京时间 → 触发周报
  if (weekday === 0 && beijingHour === 20 && beijingMinute < 15) {
    const ok = await triggerWorkflow("weekly-push.yml");
    results.push(`weekly: ${ok ? "ok" : "fail"}`);
  }

  // 始终触发分发（分发脚本内部有时间检查）
  const distOk = await triggerWorkflow("distribute.yml");
  results.push(`distribute: ${distOk ? "ok" : "fail"}`);

  return NextResponse.json({ ok: true, results, time: now.toISOString() });
}
