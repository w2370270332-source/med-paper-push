"use server";

import { createServerSupabase } from "@/lib/auth";

interface PushResult {
  success: boolean;
  error?: string;
  paperCount?: number;
}

export async function sendTestPush(email: string): Promise<PushResult> {
  try {
    const supabase = await createServerSupabase();

    // 获取最近 5 篇论文作为测试内容
    const { data: papers } = await supabase
      .from("paper_pool")
      .select("*")
      .order("fetched_at", { ascending: false })
      .limit(5);

    if (!papers || papers.length === 0) {
      return { success: false, error: "论文池为空，请先运行文献抓取" };
    }

    // 生成简单的测试报告
    const lines = ["# 📚 文献推送测试", "", `测试邮箱: ${email}`, ""];
    for (const p of papers) {
      lines.push(`## ${p.title_cn || p.title}`);
      lines.push(`**来源：**${p.source || "未知"}`);
      if (p.findings) lines.push(`**发现：**${p.findings}`);
      lines.push("");
    }

    const report = lines.join("\n");

    // 调用发送逻辑（复用 send_email.py 的环境变量）
    const sendResult = await sendViaEmail(email, "文献推送测试", report);

    return sendResult;
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

async function sendViaEmail(
  to: string,
  subject: string,
  content: string,
): Promise<PushResult> {
  const { createTransport } = await import("nodemailer");

  const transporter = createTransport({
    host: process.env.EMAIL_SMTP_HOST || "smtp.qq.com",
    port: Number(process.env.EMAIL_SMTP_PORT) || 465,
    secure: true,
    auth: {
      user: process.env.EMAIL_SENDER,
      pass: process.env.EMAIL_PASSWORD,
    },
  });

  await transporter.sendMail({
    from: process.env.EMAIL_SENDER,
    to,
    subject,
    text: content,
  });

  return { success: true, paperCount: 5 };
}
