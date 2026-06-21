import { NextResponse } from "next/server";
import { createServerSupabase, isAdmin } from "@/lib/auth";

export async function POST(request: Request) {
  if (!(await isAdmin())) {
    return NextResponse.json({ success: false, error: "无权限" }, { status: 403 });
  }

  try {
    const { email } = await request.json();
    if (!email) {
      return NextResponse.json({ success: false, error: "邮箱不能为空" });
    }

    const action = await import("@/app/actions");
    const result = await action.sendTestPush(email);

    return NextResponse.json(result);
  } catch (e: any) {
    return NextResponse.json({ success: false, error: e.message });
  }
}
