import React, { useState, useEffect } from 'react';
import {
  Card, Select, Button, Table, Spin, message,
  Typography, Form, Input, Modal, Popconfirm, Space, Tabs
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import * as api from '../services/api';

const { Option } = Select;
const { Title } = Typography;
const { TabPane } = Tabs;

interface DBConnection {
  id: number;
  name: string;
  falkordb_graph_id?: string | null;
}

interface BusinessMetric {
  id: number;
  connection_id: number;
  name: string;
  formula: string;
  related_table?: string;
  filter_condition?: string;
  description?: string;
}

interface SemanticColumn {
  name: string;
  type: string;
  description: string;
  business_name: string;
  synonyms: string;
  enum_descriptions: string;
  key_type: string;
}

interface SemanticTable {
  name: string;
  description: string;
  business_name: string;
  synonyms: string;
  columns: SemanticColumn[];
}

const ValueMappingsPage: React.FC = () => {
  const [connections, setConnections] = useState<DBConnection[]>([]);
  const [selectedConnection, setSelectedConnection] = useState<number | null>(null);
  const [selectedGraphId, setSelectedGraphId] = useState<string | null>(null);

  // Business metrics state
  const [metrics, setMetrics] = useState<BusinessMetric[]>([]);
  const [bmLoading, setBmLoading] = useState<boolean>(false);
  const [bmModalVisible, setBmModalVisible] = useState<boolean>(false);
  const [editingMetric, setEditingMetric] = useState<BusinessMetric | null>(null);
  const [bmForm] = Form.useForm();

  // Semantic model state
  const [semanticTables, setSemanticTables] = useState<SemanticTable[]>([]);
  const [semanticLoading, setSemanticLoading] = useState(false);
  const [semanticSaving, setSemanticSaving] = useState(false);
  const [semanticTable, setSemanticTable] = useState<string>('');
  const [semanticColumn, setSemanticColumn] = useState<string>('');
  const [semanticForm] = Form.useForm();

  const [activeTab, setActiveTab] = useState<string>('semantic-model');

  // ── Fetch helpers ───────────────────────────────────────

  const fetchConnections = async () => {
    try {
      const response = await api.getConnections();
      const conns: DBConnection[] = response.data || [];
      setConnections(conns);
    } catch (error) {
      message.error('获取连接失败');
      console.error(error);
    }
  };

  const fetchSemanticSchema = async (graphId: string) => {
    if (!graphId) return;
    setSemanticLoading(true);
    try {
      const res = await api.getSchemaDetail(graphId);
      setSemanticTables(res.data.tables || []);
    } catch (e) {
      console.error(e);
      message.error('获取语义模型失败');
    } finally {
      setSemanticLoading(false);
    }
  };

  const fetchBusinessMetrics = async (connectionId: number) => {
    setBmLoading(true);
    try {
      const response = await api.getBusinessMetrics(connectionId);
      setMetrics(response.data);
    } catch (error) {
      message.error('获取业务指标失败');
      console.error(error);
    } finally {
      setBmLoading(false);
    }
  };

  // ── Effects ─────────────────────────────────────────────

  useEffect(() => {
    fetchConnections();
  }, []);

  useEffect(() => {
    if (selectedConnection) {
      fetchBusinessMetrics(selectedConnection);
    }
  }, [selectedConnection]);

  useEffect(() => {
    if (activeTab === 'semantic-model' && selectedGraphId) {
      fetchSemanticSchema(selectedGraphId);
    }
  }, [activeTab, selectedGraphId]);

  // ── Handlers: Value Mappings ────────────────────────────

  const handleConnectionChange = (value: number) => {
    setSelectedConnection(value);
    const conn = connections.find(c => c.id === value);
    if (conn?.falkordb_graph_id) {
      setSelectedGraphId(conn.falkordb_graph_id);
    } else {
      setSelectedGraphId(null);
      setSemanticTables([]);
      setSemanticTable('');
      setSemanticColumn('');
    }
  };

  // ── Handlers: Business Metrics ──────────────────────────

  const showBmModal = (metric?: BusinessMetric) => {
    setEditingMetric(metric || null);
    bmForm.resetFields();
    if (metric) {
      bmForm.setFieldsValue({
        name: metric.name,
        formula: metric.formula,
        related_table: metric.related_table,
        filter_condition: metric.filter_condition,
        description: metric.description,
      });
    }
    setBmModalVisible(true);
  };

  const handleBmSubmit = async () => {
    try {
      const values = await bmForm.validateFields();
      if (editingMetric) {
        await api.updateBusinessMetric(selectedConnection!, editingMetric.id, values);
        message.success('业务指标更新成功');
      } else {
        await api.createBusinessMetric(selectedConnection!, values);
        message.success('业务指标创建成功');
      }
      setBmModalVisible(false);
      fetchBusinessMetrics(selectedConnection!);
    } catch (error) {
      message.error('保存业务指标失败');
      console.error(error);
    }
  };

  const handleBmDelete = async (id: number) => {
    try {
      await api.deleteBusinessMetric(selectedConnection!, id);
      message.success('业务指标删除成功');
      fetchBusinessMetrics(selectedConnection!);
    } catch (error) {
      message.error('删除业务指标失败');
      console.error(error);
    }
  };

  // ── Handlers: Semantic Model ────────────────────────────

  const handleSemanticTableChange = (value: string) => {
    setSemanticTable(value);
    setSemanticColumn('');
    semanticForm.resetFields();
    const table = semanticTables.find(t => t.name === value);
    if (table) {
      semanticForm.setFieldsValue({
        business_name: table.business_name || '',
        synonyms: table.synonyms || '',
        description: table.description || '',
        enum_descriptions: '',
      });
    }
  };

  const handleSemanticColumnChange = (value: string | undefined) => {
    setSemanticColumn(value || '');
    const table = semanticTables.find(t => t.name === semanticTable);
    if (!table) return;
    if (value) {
      const col = table.columns.find(c => c.name === value);
      if (col) {
        semanticForm.setFieldsValue({
          business_name: col.business_name || '',
          synonyms: col.synonyms || '',
          description: col.description || '',
          enum_descriptions: col.enum_descriptions || '',
        });
      }
    } else {
      semanticForm.setFieldsValue({
        business_name: table.business_name || '',
        synonyms: table.synonyms || '',
        description: table.description || '',
        enum_descriptions: '',
      });
    }
  };

  const handleSemanticSave = async () => {
    if (!selectedGraphId || !semanticTable) return;
    try {
      const values = await semanticForm.validateFields();
      setSemanticSaving(true);
      if (semanticColumn) {
        await api.updateNode(selectedGraphId, 'Column', semanticColumn, values);
      } else {
        await api.updateNode(selectedGraphId, 'Table', semanticTable, values);
      }
      message.success('语义模型保存成功');
      fetchSemanticSchema(selectedGraphId);
    } catch (error) {
      message.error('保存语义模型失败');
      console.error(error);
    } finally {
      setSemanticSaving(false);
    }
  };

  // ── Render ──────────────────────────────────────────────

  const bmColumns = [
    { title: '指标名称', dataIndex: 'name', key: 'name' },
    { title: '计算公式', dataIndex: 'formula', key: 'formula', ellipsis: true },
    { title: '关联表', dataIndex: 'related_table', key: 'related_table' },
    { title: '过滤条件', dataIndex: 'filter_condition', key: 'filter_condition', ellipsis: true },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: BusinessMetric) => (
        <Space size="middle">
          <Button icon={<EditOutlined />} onClick={() => showBmModal(record)} size="small">编辑</Button>
          <Popconfirm title="确定要删除这个指标吗？" onConfirm={() => handleBmDelete(record.id)} okText="是" cancelText="否">
            <Button danger icon={<DeleteOutlined />} size="small">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16, alignItems: 'center' }}>
          <Title level={4}>语义配置</Title>
          <Select
            placeholder="选择数据库连接"
            style={{ width: 280 }}
            onChange={handleConnectionChange}
            value={selectedConnection || undefined}
          >
            {connections.map(conn => (
              <Option key={conn.id} value={conn.id}>{conn.name}</Option>
            ))}
          </Select>
        </div>

        <Tabs activeKey={activeTab} onChange={setActiveTab}>
          <TabPane tab="业务指标" key="business-metrics">
            {selectedConnection && (
              <div style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => showBmModal()}>
                  添加业务指标
                </Button>
              </div>
            )}

            {bmLoading ? (
              <div style={{ textAlign: 'center', padding: '20px' }}><Spin /></div>
            ) : selectedConnection ? (
              <Table columns={bmColumns} dataSource={metrics} rowKey="id" pagination={{ pageSize: 10 }} />
            ) : (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <p>请先选择数据库连接</p>
              </div>
            )}
          </TabPane>

          <TabPane tab="语义模型配置" key="semantic-model">
            <div style={{ marginBottom: 16 }}>
              <p style={{ color: '#666', fontSize: 13 }}>
                为表和列配置业务名称、同义词、枚举值说明等语义信息，帮助 AI 更准确地理解自然语言查询。
              </p>
            </div>

            <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
              <Select
                placeholder="选择表"
                style={{ width: 240 }}
                onChange={handleSemanticTableChange}
                value={semanticTable || undefined}
                disabled={!selectedGraphId || semanticLoading}
                loading={semanticLoading}
              >
                {semanticTables.map(table => (
                  <Option key={table.name} value={table.name}>{table.name}</Option>
                ))}
              </Select>
              <Select
                placeholder="选择列（留空则编辑表属性）"
                style={{ width: 280 }}
                onChange={handleSemanticColumnChange}
                value={semanticColumn || undefined}
                disabled={!semanticTable}
                allowClear
              >
                {semanticTables
                  .find(t => t.name === semanticTable)?.columns.map(col => (
                    <Option key={col.name} value={col.name}>{col.name} ({col.type})</Option>
                  ))}
              </Select>
            </div>

            {semanticLoading ? (
              <div style={{ textAlign: 'center', padding: '20px' }}><Spin /></div>
            ) : semanticTable ? (
              <Form form={semanticForm} layout="vertical" style={{ maxWidth: 600 }}>
                <Form.Item name="business_name" label="业务名称">
                  <Input placeholder="如：订单表" />
                </Form.Item>
                <Form.Item name="synonyms" label="同义词">
                  <Input placeholder="多个同义词用逗号分隔，如：订单, 购买记录" />
                </Form.Item>
                <Form.Item name="description" label="描述">
                  <Input.TextArea rows={2} placeholder="该表或列的业务含义描述" />
                </Form.Item>
                {semanticColumn && (
                  <Form.Item name="enum_descriptions" label="枚举值说明">
                    <Input.TextArea rows={2} placeholder='如：{"1": "启用", "0": "禁用"}' />
                  </Form.Item>
                )}
                <Form.Item>
                  <Button type="primary" onClick={handleSemanticSave} loading={semanticSaving}>
                    保存
                  </Button>
                </Form.Item>
              </Form>
            ) : (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <p>请先选择要配置的表</p>
              </div>
            )}

            {!selectedGraphId && (
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <p>请先选择具有 FalkorDB 图谱的数据库连接</p>
              </div>
            )}
          </TabPane>
        </Tabs>
      </Card>

      {/* Business Metric Modal */}
      <Modal
        title={editingMetric ? '编辑业务指标' : '添加业务指标'}
        open={bmModalVisible}
        onOk={handleBmSubmit}
        onCancel={() => setBmModalVisible(false)}
        width={560}
      >
        <Form form={bmForm} layout="vertical">
          <Form.Item name="name" label="指标名称" rules={[{ required: true, message: '请输入指标名称' }]}>
            <Input placeholder="如：GMV、销售额、订单数" />
          </Form.Item>
          <Form.Item name="formula" label="计算公式" rules={[{ required: true, message: '请输入计算公式' }]}>
            <Input placeholder="如：SUM(price2)、COUNT(*)" />
          </Form.Item>
          <Form.Item name="related_table" label="关联表">
            <Input placeholder="如：orders" />
          </Form.Item>
          <Form.Item name="filter_condition" label="过滤条件">
            <Input placeholder="如：status = 1 AND created_at >= '2024-01-01'" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="补充说明该指标的业务含义和使用场景" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ValueMappingsPage;
