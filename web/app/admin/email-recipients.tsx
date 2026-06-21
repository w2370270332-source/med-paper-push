"use client";

import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Input,
  message,
  Modal,
  Radio,
  Space,
  Table,
  Tag,
  TimePicker,
  Typography,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import { createClient } from "@/lib/supabase";
import dayjs from "dayjs";

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

interface Recipient {
  id: number;
  email: string;
  research_areas: string[];
  cas_quartiles: string[];
  push_frequency: string;
  push_days: string[];
  push_time: string;
  created_at: string;
}

const defaultPrefs = {
  research_areas: [] as string[],
  cas_quartiles: ["1", "2", "3", "4"],
  push_frequency: "daily",
  push_days: [] as string[],
  push_time: "08:00",
};

export function EmailRecipients() {
  const [recipients, setRecipients] = useState<Recipient[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState({ email: "", ...defaultPrefs });
  const [saving, setSaving] = useState(false);
  const supabase = createClient();

  const loadData = async () => {
    setLoading(true);
    const { data } = await supabase
      .from("email_recipients")
      .select("*")
      .order("created_at", { ascending: false });
    if (data) setRecipients(data);
    setLoading(false);
  };

  // Load on mount
  useEffect(() => { loadData(); }, []);

  const openAdd = () => {
    setEditingId(null);
    setForm({ email: "", ...defaultPrefs });
    setModalOpen(true);
  };

  const openEdit = (r: Recipient) => {
    setEditingId(r.id);
    setForm({
      email: r.email,
      research_areas: r.research_areas || [],
      cas_quartiles: r.cas_quartiles || ["1","2","3","4"],
      push_frequency: r.push_frequency || "daily",
      push_days: r.push_days || [],
      push_time: r.push_time || "08:00",
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.email) { message.warning("请输入邮箱"); return; }
    setSaving(true);
    const payload = {
      email: form.email,
      research_areas: form.research_areas,
      cas_quartiles: form.cas_quartiles,
      push_frequency: form.push_frequency,
      push_days: form.push_days,
      push_time: form.push_time,
    };

    let error;
    if (editingId) {
      ({ error } = await supabase.from("email_recipients").update(payload).eq("id", editingId));
    } else {
      ({ error } = await supabase.from("email_recipients").insert(payload));
    }

    setSaving(false);
    if (error) {
      message.error("保存失败: " + error.message);
    } else {
      message.success(editingId ? "已更新" : "已添加");
      setModalOpen(false);
      loadData();
    }
  };

  const handleDelete = async (id: number) => {
    const { error } = await supabase.from("email_recipients").delete().eq("id", id);
    if (error) {
      message.error("删除失败: " + error.message);
    } else {
      message.success("已删除");
      loadData();
    }
  };

  const columns = [
    { title: "邮箱", dataIndex: "email", key: "email" },
    {
      title: "研究领域",
      dataIndex: "research_areas",
      key: "areas",
      render: (v: string[]) => v?.length ? v.map(a => <Tag key={a} color="blue">{a}</Tag>) : <Tag>全部</Tag>,
    },
    {
      title: "频率",
      dataIndex: "push_frequency",
      key: "freq",
      width: 70,
      render: (v: string) => ({ daily: "每天", weekly: "每周", weekdays: "工作日" }[v] || v),
    },
    {
      title: "推送时间",
      dataIndex: "push_time",
      key: "time",
      width: 80,
    },
    {
      title: "添加时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (v: string) => new Date(v).toLocaleString("zh-CN"),
    },
    {
      title: "操作",
      key: "action",
      width: 160,
      render: (_: any, r: Recipient) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(r.id)}>删除</Button>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="邮件管理"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>
          添加邮箱
        </Button>
      }
    >
      <Table dataSource={recipients} columns={columns} rowKey="id" loading={loading} pagination={{ pageSize: 20 }} />

      <Modal
        title={editingId ? "编辑邮箱偏好" : "添加邮箱"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        width={600}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Text strong>邮箱</Text>
            <Input
              value={form.email}
              onChange={e => setForm({ ...form, email: e.target.value })}
              placeholder="输入邮箱地址"
              disabled={!!editingId}
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
              <Text type="secondary" style={{ marginLeft: 8 }}>（当地时间）</Text>
            </div>
          </div>

          <div>
            <Text strong>研究领域</Text>
            <Checkbox.Group
              options={RESEARCH_AREAS}
              value={form.research_areas}
              onChange={v => setForm({ ...form, research_areas: v as string[] })}
            />
          </div>

          <div>
            <Text strong>中科院分区</Text>
            <Checkbox.Group
              options={CAS_QUARTILES}
              value={form.cas_quartiles}
              onChange={v => setForm({ ...form, cas_quartiles: v as string[] })}
            />
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
                  onChange={v => setForm({ ...form, push_days: v as string[] })}
                />
              </div>
            )}
          </div>
        </Space>
      </Modal>
    </Card>
  );
}
