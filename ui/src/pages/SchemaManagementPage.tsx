/**
 * Database Schema 页面 - 使用 FalkorDB Canvas 可视化
 * 支持 Semantic Model 编辑（business_name, synonyms, enum_descriptions）
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  Select,
  message,
  Form,
  Input,
  Button,
  Divider,
  Typography,
  Space,
  Spin,
} from 'antd';
import SchemaViewer from '../components/schema/SchemaViewer';
import * as api from '../services/api';

const { Option } = Select;
const { TextArea } = Input;
const { Title, Text } = Typography;

interface DBConnection {
  id: number;
  name: string;
  falkordb_graph_id?: string;
}

interface ColumnDetail {
  name: string;
  type: string;
  description: string;
  business_name: string;
  synonyms: string;
  enum_descriptions: string;
  key_type: string;
  nullable: string;
}

interface TableDetail {
  name: string;
  description: string;
  business_name: string;
  synonyms: string;
  columns: ColumnDetail[];
}

const SchemaManagementPage: React.FC = () => {
  const [connections, setConnections] = useState<DBConnection[]>([]);
  const [selectedConnection, setSelectedConnection] = useState<number | null>(null);
  const [selectedGraphId, setSelectedGraphId] = useState<string | null>(null);

  const [tables, setTables] = useState<TableDetail[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [saving, setSaving] = useState(false);

  const [selectedTable, setSelectedTable] = useState<string>('');
  const [selectedColumn, setSelectedColumn] = useState<string>('');

  const [form] = Form.useForm();

  useEffect(() => {
    fetchConnections();
  }, []);

  useEffect(() => {
    if (selectedGraphId) {
      fetchSchemaDetail();
    } else {
      setTables([]);
      setSelectedTable('');
      setSelectedColumn('');
    }
  }, [selectedGraphId]);

  useEffect(() => {
    const table = tables.find((t) => t.name === selectedTable);
    if (table) {
      if (selectedColumn) {
        const col = table.columns.find((c) => c.name === selectedColumn);
        if (col) {
          form.setFieldsValue({
            business_name: col.business_name,
            synonyms: col.synonyms,
            enum_descriptions: col.enum_descriptions,
            description: col.description,
          });
        }
      } else {
        form.setFieldsValue({
          business_name: table.business_name,
          synonyms: table.synonyms,
          enum_descriptions: '',
          description: table.description,
        });
      }
    }
  }, [selectedTable, selectedColumn, tables, form]);

  const fetchConnections = async () => {
    try {
      const response = await api.getConnections();
      const conns = response.data || [];
      setConnections(conns);
      const active = conns.find((c: DBConnection) => c.falkordb_graph_id);
      if (active) {
        setSelectedConnection(active.id);
        setSelectedGraphId(active.falkordb_graph_id || null);
      }
    } catch (error) {
      message.error('获取连接失败');
    }
  };

  const fetchSchemaDetail = async () => {
    if (!selectedGraphId) return;
    setLoadingDetail(true);
    try {
      const res = await api.getSchemaDetail(selectedGraphId);
      setTables(res.data.tables || []);
    } catch (e) {
      console.error(e);
      message.error('获取 Schema 详情失败');
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleConnectionChange = (value: number) => {
    setSelectedConnection(value);
    const conn = connections.find((c) => c.id === value);
    if (conn?.falkordb_graph_id) {
      setSelectedGraphId(conn.falkordb_graph_id);
    } else {
      setSelectedGraphId(null);
      message.warning('该连接尚未加载 Schema，请先在数据源中添加数据库连接');
    }
  };

  const handleTableChange = (value: string) => {
    setSelectedTable(value);
    setSelectedColumn('');
  };

  const handleColumnChange = (value: string) => {
    setSelectedColumn(value);
  };

  const handleSave = async (values: any) => {
    if (!selectedGraphId || !selectedTable) return;
    setSaving(true);
    try {
      const nodeType = selectedColumn ? 'Column' : 'Table';
      const nodeName = selectedColumn || selectedTable;
      await api.updateNode(selectedGraphId, nodeType, nodeName, {
        business_name: values.business_name,
        synonyms: values.synonyms,
        enum_descriptions: values.enum_descriptions,
        description: values.description,
      });
      message.success('保存成功');
      await fetchSchemaDetail();
    } catch (e) {
      console.error(e);
      message.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const currentTable = tables.find((t) => t.name === selectedTable);
  const isEditingColumn = !!selectedColumn;

  return (
    <div style={{ height: 'calc(100vh - 150px)', minHeight: 500 }}>
      <Card
        style={{ height: '100%' }}
        styles={{ body: { height: '100%', display: 'flex', flexDirection: 'column', padding: 0 } }}
      >
        <div style={{ padding: '16px 24px', display: 'flex', alignItems: 'center', gap: 16, borderBottom: '1px solid #f0f0f0' }}>
          <Title level={5} style={{ margin: 0 }}>Database Schema</Title>
          <Select
            placeholder="选择数据库连接"
            style={{ width: 300 }}
            value={selectedConnection || undefined}
            onChange={handleConnectionChange}
          >
            {connections.map((conn) => (
              <Option key={conn.id} value={conn.id}>
                {conn.name}
                {conn.falkordb_graph_id ? '' : ' (未连接)'}
              </Option>
            ))}
          </Select>
        </div>

        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Canvas area */}
          <div style={{ flex: 1, borderRight: '1px solid #f0f0f0', overflow: 'hidden' }}>
            <SchemaViewer graphId={selectedGraphId} />
          </div>

          {/* Semantic Model editing panel */}
          <div
            style={{
              width: 360,
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #f0f0f0' }}>
              <Title level={5} style={{ margin: 0 }}>语义模型编辑</Title>
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
              {loadingDetail ? (
                <div style={{ textAlign: 'center', paddingTop: 40 }}>
                  <Spin />
                  <div style={{ marginTop: 8 }}>加载中...</div>
                </div>
              ) : !selectedGraphId ? (
                <Text type="secondary">请先选择数据库连接</Text>
              ) : tables.length === 0 ? (
                <Text type="secondary">暂无 Schema 数据</Text>
              ) : (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  <Select
                    placeholder="选择数据表"
                    style={{ width: '100%' }}
                    value={selectedTable || undefined}
                    onChange={handleTableChange}
                    allowClear
                  >
                    {tables.map((t) => (
                      <Option key={t.name} value={t.name}>
                        {t.business_name ? `${t.business_name} (${t.name})` : t.name}
                      </Option>
                    ))}
                  </Select>

                  {currentTable && (
                    <Select
                      placeholder="选择字段（留空则编辑表属性）"
                      style={{ width: '100%' }}
                      value={selectedColumn || undefined}
                      onChange={handleColumnChange}
                      allowClear
                    >
                      {currentTable.columns.map((c) => (
                        <Option key={c.name} value={c.name}>
                          {c.business_name
                            ? `${c.business_name} (${c.name})`
                            : c.name}{' '}
                          <Text type="secondary">{c.type}</Text>
                        </Option>
                      ))}
                    </Select>
                  )}

                  {selectedTable && (
                    <Form
                      form={form}
                      layout="vertical"
                      onFinish={handleSave}
                      style={{ marginTop: 8 }}
                    >
                      <Divider style={{ margin: '8px 0' }} />
                      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
                        正在编辑:{' '}
                        <Text strong>
                          {isEditingColumn
                            ? `${selectedTable}.${selectedColumn}`
                            : selectedTable}
                        </Text>
                      </Text>

                      <Form.Item
                        name="business_name"
                        label="业务名称"
                        rules={[{ max: 100 }]}
                      >
                        <Input placeholder="如：订单表、订单金额" />
                      </Form.Item>

                      <Form.Item
                        name="synonyms"
                        label="同义词"
                        rules={[{ max: 500 }]}
                      >
                        <TextArea
                          rows={2}
                          placeholder="多个同义词用逗号分隔，如：订单, purchase, sale"
                        />
                      </Form.Item>

                      {isEditingColumn && (
                        <Form.Item
                          name="enum_descriptions"
                          label="枚举值说明"
                          rules={[{ max: 1000 }]}
                        >
                          <TextArea
                            rows={3}
                            placeholder="如：0=未支付, 1=已支付, 2=已退款"
                          />
                        </Form.Item>
                      )}

                      <Form.Item
                        name="description"
                        label="描述"
                        rules={[{ max: 500 }]}
                      >
                        <TextArea
                          rows={2}
                          placeholder="补充说明该表/字段的业务含义"
                        />
                      </Form.Item>

                      <Form.Item style={{ marginBottom: 0 }}>
                        <Button type="primary" htmlType="submit" loading={saving} block>
                          保存
                        </Button>
                      </Form.Item>
                    </Form>
                  )}
                </Space>
              )}
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default SchemaManagementPage;
