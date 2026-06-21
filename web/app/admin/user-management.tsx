"use client";

import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  message,
  Modal,
  Radio,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import { EditOutlined } from "@ant-design/icons";
import { createClient } from "@/lib/supabase";

const { Text } = Typography;

const RESEARCH_AREAS = [
  "肥胖与代谢", "心血管与代谢疾病", "肠道菌群",
  "糖尿病与血糖管理", "营养流行病学", "公共卫生营养",
  "母婴营养", "衰老与营养", "食品政策与安全",
  "膳食干预与临床营养", "营养生物化学",
  "流行病学", "生物统计学", "AI驱动的健康研究",
];

const CAS_QUARTILES = [
  { label: "1区", value: "1" },
  { label: "2区", value: "2" },
  { label: "3区", value: "3" },
  { label: "4区", value: "4" },
];

const FREQ_OPTIONS = [
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

interface UserInfo {
  user_id: string;
  email: string;
  joined_at: string;
  research_areas: string[];
  cas_quartiles: string[];
  push_frequency: string;
  push_days: string[];
  push_time: string;
  enabled: boolean;
}

export function UserManagement() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserInfo | null>(null);
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();
  const supabase = createClient();

  const loadUsers = async () => {
    setLoading(true);
    const { data } = await supabase.from("user_info").select("*").order("joined_at", { ascending: false });
    if (data) setUsers(data);
    setLoading(false);
  };

  useEffect(() => { loadUsers(); }, []);

  const openEdit = (u: UserInfo) => {
    setEditingUser(u);
    setForm({
      research_areas: u.research_areas || [],
      cas_quartiles: u.cas_quartiles || ["1","2","3","4"],
      push_frequency: u.push_frequency || "daily",
      push_days: u.push_days || [],
      push_time: u.push_time || "08:00",
      enabled: u.enabled !== false,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!editingUser) return;
    setSaving(true);
    const { error: updateErr } = await supabase
      .from("user_preferences")
      .update({
        research_areas: form.research_areas,
        cas_quartiles: form.cas_quartiles,
        push_frequency: form.push_frequency,
        push_days: form.push_days,
        push_time: form.push_time,
        enabled: form.enabled,
        updated_at: new Date().toISOString(),
      })
      .eq("user_id", editingUser.user_id);

    let error = updateErr;
    if (updateErr?.code === "PGRST116") {
      const { error: insertErr } = await supabase
        .from("user_preferences")
        .insert({
          user_id: editingUser.user_id,
          research_areas: form.research_areas,
          cas_quartiles: form.cas_quartiles,
          push_frequency: form.push_frequency,
          push_days: form.push_days,
          push_time: form.push_time,
          enabled: form.enabled,
        });
      error = insertErr;
    }

    setSaving(false);
    if (error) {
      messageApi.error("保存失败: " + error.message);
    } else {
      messageApi.success("已更新");
      setModalOpen(false);
      loadUsers();
    }
  };

  const columns = [
    {
      title: "邮箱",
      dataIndex: "email",
      key: "email",
      width: 220,
    },
    {
      title: "研究领域",
      dataIndex: "research_areas",
      key: "areas",
      render: (v: string[]) =>
        v?.length ? (
          <Space wrap>{v.slice(0,3).map(a => <Tag key={a}>{a}</Tag>)}{v.length > 3 && <Tag>+{v.length-3}</Tag>}</Space>
        ) : <Tag>全部</Tag>,
    },
    {
      title: "推送频率",
      dataIndex: "push_frequency",
      key: "freq",
      width: 70,
      render: (v: string) => ({ daily: "每天", weekly: "每周", weekdays: "工作日" }[v] || v),
    },
    {
      title: "推送时间",
      dataIndex: "push_time",
      key: "time",
      width: 70,
    },
    {
      title: "状态",
      dataIndex: "enabled",
      key: "enabled",
      width: 70,
      render: (v: boolean) =>
        v !== false ? <Tag color="success">启用</Tag> : <Tag color="default">停用</Tag>,
    },
    {
      title: "注册时间",
      dataIndex: "joined_at",
      key: "joined_at",
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "action",
      width: 80,
      render: (_: any, r: UserInfo) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <>
      {contextHolder}
      <Card title="用户管理">
      <Table dataSource={users} columns={columns} rowKey="user_id" loading={loading} pagination={{ pageSize: 20 }} />

      <Modal
        title={`编辑偏好 — ${editingUser?.email}`}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={600}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Text strong>状态</Text>
            <div>
              <Switch
                checked={form.enabled}
                onChange={v => setForm({ ...form, enabled: v })}
                checkedChildren="启用"
                unCheckedChildren="停用"
              />
            </div>
          </div>

          <div>
            <Text strong>研究领域</Text>
            <Checkbox.Group
              options={RESEARCH_AREAS}
              value={form.research_areas}
              onChange={v => setForm({ ...form, research_areas: v })}
            />
          </div>

          <div>
            <Text strong>中科院分区</Text>
            <Checkbox.Group
              options={CAS_QUARTILES}
              value={form.cas_quartiles}
              onChange={v => setForm({ ...form, cas_quartiles: v })}
            />
          </div>

          <div>
            <Text strong>推送时间</Text>
            <div>
              <input
                type="time"
                value={form.push_time}
                onChange={e => setForm({ ...form, push_time: e.target.value })}
                style={{ padding: "4px 8px", fontSize: 14, borderRadius: 6, border: "1px solid #d9d9d9" }}
              />
              <Text type="secondary" style={{ marginLeft: 8 }}>（北京时间）</Text>
            </div>
          </div>

          <div>
            <Text strong>推送频率</Text>
            <Radio.Group
              options={FREQ_OPTIONS}
              value={form.push_frequency}
              onChange={e => setForm({ ...form, push_frequency: e.target.value })}
            />
            {form.push_frequency === "weekdays" && (
              <div style={{ marginTop: 8 }}>
                <Checkbox.Group
                  options={WEEKDAYS}
                  value={form.push_days}
                  onChange={v => setForm({ ...form, push_days: v })}
                />
              </div>
            )}
          </div>
        </Space>
      </Modal>
    </Card>
    </>
  );
}
