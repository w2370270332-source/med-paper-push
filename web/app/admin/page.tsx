"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  App,
  Button,
  Card,
  Col,
  Divider,
  Input,
  Layout,
  Menu,
  message,
  Modal,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  theme,
} from "antd";
import {
  LogoutOutlined,
  KeyOutlined,
  TeamOutlined,
  SendOutlined,
  DashboardOutlined,
  CopyOutlined,
} from "@ant-design/icons";
import { createClient } from "@/lib/supabase";

const { Title, Text } = Typography;
const { Header, Sider, Content } = Layout;

export default function AdminPage() {
  const [tab, setTab] = useState("dashboard");
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ users: 0, papers: 0, pushes: 0 });
  const [inviteCodes, setInviteCodes] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [generating, setGenerating] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [testing, setTesting] = useState(false);

  const router = useRouter();
  const supabase = createClient();
  const { token } = theme.useToken();

  const loadStats = useCallback(async () => {
    const [usersR, prefsR, papersR, pushesR] = await Promise.all([
      supabase.from("invite_codes").select("*", { count: "exact", head: true }).neq("used_by", null),
      supabase.from("user_preferences").select("*", { count: "exact", head: true }),
      supabase.from("paper_pool").select("*", { count: "exact", head: true }),
      supabase.from("push_history").select("*", { count: "exact", head: true }),
    ]);
    setStats({
      users: prefsR.count || 0,
      papers: papersR.count || 0,
      pushes: pushesR.count || 0,
    });
    setLoading(false);
  }, [supabase]);

  const loadInvites = useCallback(async () => {
    const { data } = await supabase
      .from("invite_codes")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(50);
    if (data) setInviteCodes(data);
  }, [supabase]);

  const loadUsers = useCallback(async () => {
    const { data: prefs } = await supabase
      .from("user_preferences")
      .select("*");
    if (prefs) setUsers(prefs);
  }, [supabase]);

  useEffect(() => {
    loadStats();
    loadInvites();
    loadUsers();
  }, [loadStats, loadInvites, loadUsers]);

  const handleGenerate = async () => {
    setGenerating(true);
    const code = Array.from({ length: 8 }, () =>
      "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".charAt(
        Math.floor(Math.random() * 32),
      ),
    ).join("");

    const { error } = await supabase.from("invite_codes").insert({ code });
    setGenerating(false);
    if (error) {
      message.error("生成失败: " + error.message);
    } else {
      message.success(`邀请码已生成: ${code}`);
      loadInvites();
    }
  };

  const handleTestPush = async () => {
    if (!testEmail) {
      message.warning("请输入测试邮箱");
      return;
    }
    setTesting(true);
    try {
      const resp = await fetch("/api/test-push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: testEmail }),
      });
      const data = await resp.json();
      if (data.success) {
        message.success("测试推送已发送");
      } else {
        message.error("测试推送失败: " + data.error);
      }
    } catch (e: any) {
      message.error("请求失败: " + e.message);
    }
    setTesting(false);
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code);
    message.success("已复制");
  };

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  const inviteColumns = [
    {
      title: "邀请码",
      dataIndex: "code",
      key: "code",
      render: (v: string) => (
        <Space>
          <Tag color="blue" style={{ fontFamily: "monospace", fontSize: 14 }}>
            {v}
          </Tag>
          <Button size="small" icon={<CopyOutlined />} onClick={() => copyCode(v)} />
        </Space>
      ),
    },
    {
      title: "状态",
      key: "status",
      render: (_: any, r: any) =>
        r.used_by ? (
          <Tag color="default">已使用</Tag>
        ) : (
          <Tag color="success">可用</Tag>
        ),
    },
    {
      title: "使用时间",
      dataIndex: "used_at",
      key: "used_at",
      render: (v: string | null) => (v ? new Date(v).toLocaleString("zh-CN") : "-"),
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
  ];

  const userColumns = [
    {
      title: "用户 ID",
      dataIndex: "user_id",
      key: "user_id",
      ellipsis: true,
      width: 200,
    },
    {
      title: "研究领域",
      dataIndex: "research_areas",
      key: "research_areas",
      render: (v: string[]) =>
        v?.length
          ? v.map((a) => (
              <Tag key={a} color="blue">
                {a}
              </Tag>
            ))
          : "-",
    },
    {
      title: "推送频率",
      dataIndex: "push_frequency",
      key: "push_frequency",
      width: 80,
      render: (v: string) => ({ daily: "每天", weekly: "每周", weekdays: "工作日" }[v] || v),
    },
    {
      title: "状态",
      dataIndex: "enabled",
      key: "enabled",
      width: 80,
      render: (v: boolean) =>
        v ? <Tag color="success">启用</Tag> : <Tag color="default">停用</Tag>,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
  ];

  return (
    <App>
      <Layout style={{ minHeight: "100vh" }}>
        <Sider
          breakpoint="lg"
          collapsedWidth={0}
          style={{ background: token.colorBgContainer }}
        >
          <div
            style={{
              padding: "16px",
              textAlign: "center",
              fontWeight: 600,
              fontSize: 16,
              color: token.colorPrimary,
            }}
          >
            🔧 管理后台
          </div>
          <Menu
            mode="inline"
            selectedKeys={[tab]}
            onClick={({ key }) => setTab(key)}
            items={[
              { key: "dashboard", icon: <DashboardOutlined />, label: "概览" },
              { key: "invites", icon: <KeyOutlined />, label: "邀请码" },
              { key: "users", icon: <TeamOutlined />, label: "用户管理" },
              { key: "test", icon: <SendOutlined />, label: "测试推送" },
            ]}
          />
        </Sider>
        <Layout>
          <Header
            style={{
              background: token.colorBgContainer,
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              padding: "0 24px",
            }}
          >
            <Button icon={<LogoutOutlined />} onClick={handleLogout}>
              退出登录
            </Button>
          </Header>
          <Content style={{ margin: 24 }}>
            {tab === "dashboard" && (
              <>
                <Row gutter={16}>
                  <Col span={8}>
                    <Card>
                      <Statistic title="注册用户" value={stats.users} suffix="人" />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <Statistic title="论文库" value={stats.papers} suffix="篇" />
                    </Card>
                  </Col>
                  <Col span={8}>
                    <Card>
                      <Statistic title="累计推送" value={stats.pushes} suffix="次" />
                    </Card>
                  </Col>
                </Row>
              </>
            )}

            {tab === "invites" && (
              <Card
                title="邀请码管理"
                extra={
                  <Button type="primary" loading={generating} onClick={handleGenerate}>
                    生成邀请码
                  </Button>
                }
              >
                <Table
                  dataSource={inviteCodes}
                  columns={inviteColumns}
                  rowKey="id"
                  pagination={{ pageSize: 20 }}
                />
              </Card>
            )}

            {tab === "users" && (
              <Card title="用户管理">
                <Table
                  dataSource={users}
                  columns={userColumns}
                  rowKey="user_id"
                  pagination={{ pageSize: 20 }}
                />
              </Card>
            )}

            {tab === "test" && (
              <Card title="测试推送">
                <Space direction="vertical" size="middle">
                  <div>
                    <Text>发送测试推送到指定邮箱：</Text>
                  </div>
                  <Input
                    placeholder="输入邮箱地址"
                    value={testEmail}
                    onChange={(e) => setTestEmail(e.target.value)}
                    style={{ width: 300 }}
                  />
                  <Button type="primary" loading={testing} onClick={handleTestPush}>
                    发送测试推送
                  </Button>
                </Space>
              </Card>
            )}
          </Content>
        </Layout>
      </Layout>
    </App>
  );
}
