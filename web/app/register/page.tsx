"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Form, Input, message, Typography } from "antd";
import { MailOutlined, LockOutlined, KeyOutlined } from "@ant-design/icons";
import { createClient } from "@/lib/supabase";

const { Title, Text, Link } = Typography;

export default function RegisterPage() {
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const supabase = createClient();

  const onFinish = async (values: {
    email: string;
    password: string;
    inviteCode: string;
  }) => {
    setLoading(true);
    const { error } = await supabase.auth.signUp({
      email: values.email,
      password: values.password,
      options: {
        data: { invite_code: values.inviteCode },
      },
    });
    setLoading(false);

    if (error) {
      message.error(error.message);
      return;
    }

    message.success("注册成功！请前往邮箱查收确认邮件，点击链接激活账号后即可登录。");
    setTimeout(() => router.push("/login"), 2000);
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
      }}
    >
      <Card style={{ width: 400, boxShadow: "0 8px 32px rgba(0,0,0,0.1)" }}>
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <Title level={3} style={{ marginBottom: 4 }}>
            📝 注册账号
          </Title>
          <Text type="secondary">需要有效的邀请码才能注册</Text>
        </div>

        <Form layout="vertical" onFinish={onFinish} size="large">
          <Form.Item
            name="email"
            rules={[
              { required: true, message: "请输入邮箱" },
              { type: "email", message: "邮箱格式不正确" },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱" />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: "请输入密码" },
              { min: 6, message: "密码至少 6 位" },
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码（至少6位）" />
          </Form.Item>

          <Form.Item
            name="inviteCode"
            rules={[{ required: true, message: "请输入邀请码" }]}
          >
            <Input prefix={<KeyOutlined />} placeholder="邀请码" />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              注册
            </Button>
          </Form.Item>
        </Form>

        <div style={{ textAlign: "center" }}>
          <Text type="secondary">
            已有账号？ <Link href="/login">返回登录</Link>
          </Text>
        </div>
      </Card>
    </div>
  );
}
