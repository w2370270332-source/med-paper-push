"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Button,
  Card,
  Checkbox,
  Input,
  Layout,
  Menu,
  message,
  Radio,
  Slider,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  theme,
} from "antd";
import {
  LogoutOutlined,
  SettingOutlined,
  HistoryOutlined,
  SafetyOutlined,
} from "@ant-design/icons";
import { createClient } from "@/lib/supabase";

const { Title, Text } = Typography;
const { Header, Sider, Content } = Layout;

const RESEARCH_AREAS = [
  "肥胖与代谢",
  "心血管与代谢疾病",
  "肠道菌群",
  "糖尿病与血糖管理",
  "药食同源与植物化学物",
  "高尿酸血症与痛风",
  "炎症与免疫调节",
  "营养流行病学",
  "公共卫生营养",
  "母婴营养",
  "衰老与营养",
  "食品政策与安全",
  "膳食干预与临床营养",
  "营养生物化学",
  "流行病学",
  "生物统计学",
  "AI驱动的健康研究",
  "咖啡风味化学与品质",
];

const CAS_QUARTILES = [
  { label: "1区", value: "1" },
  { label: "2区", value: "2" },
  { label: "3区", value: "3" },
  { label: "4区", value: "4" },
];

const FREQUENCY_OPTIONS = [
  { label: "每天", value: "daily" },
  { label: "每周", value: "weekly" },
  { label: "工作日", value: "weekdays" },
];

const WEEKDAYS = [
  { label: "周一", value: "1" },
  { label: "周二", value: "2" },
  { label: "周三", value: "3" },
  { label: "周四", value: "4" },
  { label: "周五", value: "5" },
];

export default function DashboardPage() {
  const [tab, setTab] = useState<"preferences" | "history">("preferences");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [preferences, setPreferences] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  const router = useRouter();
  const supabase = createClient();
  const [messageApi, contextHolder] = message.useMessage();
  const { token } = theme.useToken();

  const loadPreferences = useCallback(async () => {
    const { data } = await supabase.auth.getUser();
    if (!data.user) return;
    const { data: pref } = await supabase
      .from("user_preferences")
      .select("*")
      .eq("user_id", data.user.id)
      .single();
    if (pref) setPreferences(pref);
    const isAdminUser = data.user?.app_metadata?.role === "admin";
    setIsAdmin(isAdminUser);
    setLoading(false);
  }, [supabase]);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    const { data } = await supabase.auth.getUser();
    if (!data.user) return;
    const { data: hist } = await supabase
      .from("push_history")
      .select("*")
      .eq("user_id", data.user.id)
      .order("pushed_at", { ascending: false })
      .limit(50);
    if (hist) setHistory(hist);
    setHistoryLoading(false);
  }, [supabase]);

  useEffect(() => {
    loadPreferences();
    loadHistory();
  }, [loadPreferences, loadHistory]);

  const handleSave = async () => {
    setSaving(true);
    const { data } = await supabase.auth.getUser();
    if (!data.user) return;

    const { error: updateErr } = await supabase
      .from("user_preferences")
      .update({
        research_areas: preferences.research_areas,
        cas_quartiles: preferences.cas_quartiles,
        push_frequency: preferences.push_frequency,
        push_days: preferences.push_days,
        push_time: preferences.push_time || "08:00",
        enabled: preferences.enabled,
        interest_description: preferences.interest_description || null,
        relevance_threshold: preferences.relevance_threshold ?? 5,
        updated_at: new Date().toISOString(),
      })
      .eq("user_id", data.user.id);

    let error = updateErr;
    // 如果记录不存在就创建
    if (updateErr?.code === "PGRST116") {
      const { error: insertErr } = await supabase
        .from("user_preferences")
        .insert({
          user_id: data.user.id,
          research_areas: preferences.research_areas,
          cas_quartiles: preferences.cas_quartiles,
          push_frequency: preferences.push_frequency,
          push_days: preferences.push_days,
          push_time: preferences.push_time || "08:00",
          enabled: preferences.enabled,
          interest_description: preferences.interest_description || null,
          relevance_threshold: preferences.relevance_threshold ?? 5,
        });
      error = insertErr;
    }

    setSaving(false);
    if (error) {
      messageApi.error("保存失败: " + error.message);
    } else {
      messageApi.success("偏好已保存");
    }
  };

  const handleLogout = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  const historyColumns = [
    {
      title: "推送时间",
      dataIndex: "pushed_at",
      key: "pushed_at",
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "论文数",
      dataIndex: "paper_count",
      key: "paper_count",
      width: 80,
    },
    {
      title: "操作",
      key: "action",
      width: 100,
      render: (_: any, record: any) => (
        <Button
          type="link"
          onClick={() => {
            const win = window.open("", "_blank")!;
            win.document.write(
              `<pre style="white-space:pre-wrap;font-family:monospace;padding:20px">${record.report_content || "（报告内容已过期）"}</pre>`,
            );
          }}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <>
      {contextHolder}
      <Layout style={{ minHeight: "100vh" }}>
        <Sider
          breakpoint="lg"
          collapsedWidth={0}
          style={{ background: token.colorBgContainer }}
        >
          <div style={{ padding: "16px", textAlign: "center", fontWeight: 600, fontSize: 16 }}>
            📚 文献推送
          </div>
          <Menu
            mode="inline"
            selectedKeys={[tab]}
            onClick={({ key }) => {
              if (key === "admin") { router.push("/admin"); return; }
              setTab(key as any);
            }}
            items={[
              { key: "preferences", icon: <SettingOutlined />, label: "推送偏好" },
              { key: "history", icon: <HistoryOutlined />, label: "推送历史" },
              ...(isAdmin
                ? [{ key: "admin", icon: <SafetyOutlined />, label: "管理后台" }]
                : []),
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
            {tab === "preferences" ? (
              <Card title="推送偏好设置">
                <div style={{ maxWidth: 600 }}>
                  <Title level={5} style={{ marginTop: 0 }}>
                    研究领域
                  </Title>
                  <Checkbox.Group
                    options={RESEARCH_AREAS}
                    value={preferences?.research_areas || []}
                    onChange={(v) =>
                      setPreferences({ ...preferences, research_areas: v })
                    }
                  />
                  <div style={{ height: 24 }} />

                  <Title level={5}>中科院分区</Title>
                  <Checkbox.Group
                    options={CAS_QUARTILES}
                    value={preferences?.cas_quartiles || []}
                    onChange={(v) =>
                      setPreferences({ ...preferences, cas_quartiles: v })
                    }
                  />
                  <div style={{ height: 24 }} />

                  <Title level={5}>推送时间</Title>
                  <input
                    type="time"
                    value={preferences?.push_time || "08:00"}
                    onChange={(e) =>
                      setPreferences({ ...preferences, push_time: e.target.value })
                    }
                    style={{ padding: "4px 8px", fontSize: 14, borderRadius: 6, border: "1px solid #d9d9d9" }}
                  />
                  <Text type="secondary" style={{ marginLeft: 8 }}>（北京时间）</Text>
                  <div style={{ height: 24 }} />

                  <Title level={5}>推送频率</Title>
                  <Radio.Group
                    options={FREQUENCY_OPTIONS}
                    value={preferences?.push_frequency || "daily"}
                    onChange={(e) =>
                      setPreferences({
                        ...preferences,
                        push_frequency: e.target.value,
                      })
                    }
                  />
                  {preferences?.push_frequency === "weekdays" && (
                    <>
                      <div style={{ height: 12 }} />
                      <Checkbox.Group
                        options={WEEKDAYS}
                        value={preferences?.push_days || []}
                        onChange={(v) =>
                          setPreferences({ ...preferences, push_days: v })
                        }
                      />
                    </>
                  )}
                  <div style={{ height: 24 }} />

                  <Title level={5}>研究兴趣描述</Title>
                  <Input.TextArea
                    rows={3}
                    placeholder="用自然语言描述研究兴趣，例如：关注肠道菌群与膳食干预的RCT研究，不关注纯流行病学调查..."
                    value={preferences?.interest_description || ''}
                    onChange={(e) =>
                      setPreferences({ ...preferences, interest_description: e.target.value })
                    }
                    style={{ width: '100%' }}
                  />
                  <Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                    用于 AI 辅助筛选更精准匹配的论文
                  </Text>
                  <div style={{ height: 24 }} />

                  <Title level={5}>最低相关度阈值</Title>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Slider
                      min={1}
                      max={10}
                      value={preferences?.relevance_threshold ?? 5}
                      onChange={(v) =>
                        setPreferences({ ...preferences, relevance_threshold: v })
                      }
                      style={{ flex: 1 }}
                    />
                    <Text strong style={{ minWidth: 24, textAlign: 'center' }}>
                      {preferences?.relevance_threshold ?? 5}
                    </Text>
                  </div>
                  <Text type="secondary">
                    分数 ≥ 此阈值的论文才会被推送（1 = 最宽松，10 = 最严格）
                  </Text>
                  <div style={{ height: 32 }} />

                  <Space>
                    <Button type="primary" loading={saving} onClick={handleSave}>
                      保存偏好
                    </Button>
                  </Space>
                </div>
              </Card>
            ) : (
              <Card title="推送历史">
                <Table
                  dataSource={history}
                  columns={historyColumns}
                  loading={historyLoading}
                  rowKey="id"
                  pagination={{ pageSize: 20 }}
                />
              </Card>
            )}
          </Content>
        </Layout>
      </Layout>
    </>
  );
}
