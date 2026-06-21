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

    // 生成测试报告
    const lines = [
      "# 📚 文献推送系统 — 测试邮件",
      "",
      `测试邮箱: ${email}`,
      `发送时间: ${new Date().toLocaleString("zh-CN")}`,
      "",
      "---",
      "",
    ];

    if (!papers || papers.length === 0) {
      lines.push(
        "> ⚠️ 论文池当前为空，请等待 GitHub Actions 自动抓取运行后补充数据。",
        "",
        "推送系统已正常运行，此邮件仅为测试 SMTP 连通性。",
      );
    } else {
      lines.push(`论文池共 ${papers.length} 篇论文，以下是最近 5 篇：`, "");
      for (const p of papers) {
        lines.push(`## ${p.title_cn || p.title}`);
        lines.push(`**来源：**${p.source || "未知"}`);
        if (p.findings) lines.push(`**发现：**${p.findings}`);
        lines.push("");
      }
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
