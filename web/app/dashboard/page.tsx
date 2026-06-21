"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  App,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Layout,
  Menu,
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
  "肠道菌群",
  "心血管预防",
  "糖尿病",
  "营养流行病学",
  "公共卫生营养",
  "慢性病预防",
  "母婴营养",
  "衰老与营养",
  "食品政策",
  "膳食干预",
  "微量营养素",
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
  const { message } = App.useApp();
  const supabase = createClient();
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

    const { error } = await supabase
      .from("user_preferences")
      .upsert({
        user_id: data.user.id,
        research_areas: preferences.research_areas,
        cas_quartiles: preferences.cas_quartiles,
        min_impact_factor: preferences.min_impact_factor,
        push_frequency: preferences.push_frequency,
        push_days: preferences.push_days,
        enabled: preferences.enabled,
        updated_at: new Date().toISOString(),
      });

    setSaving(false);
    if (error) {
      message.error("保存失败: " + error.message);
    } else {
      message.success("偏好已保存");
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
    <App>
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

                  <Title level={5}>
                    最低影响因子：{preferences?.min_impact_factor || 0}
                  </Title>
                  <Slider
                    min={0}
                    max={50}
                    step={1}
                    value={preferences?.min_impact_factor || 0}
                    onChange={(v) =>
                      setPreferences({ ...preferences, min_impact_factor: v })
                    }
                    style={{ maxWidth: 400 }}
                    marks={{ 0: "0", 10: "10", 20: "20", 30: "30", 50: "50" }}
                  />
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
    </App>
  );
}
