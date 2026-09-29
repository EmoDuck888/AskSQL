// 混合问答对管理页面

import React, { useState, useEffect } from 'react';
import {
  Card,
  Table,
  Button,
  Space,
  Tag,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Switch,
  message,
  Tabs,
  Row,
  Col,
  Statistic,
  Progress,
  Tooltip,
  Divider
} from 'antd';
import {
  PlusOutlined,
  SearchOutlined,
  EyeOutlined,
  RobotOutlined,
  DatabaseOutlined,
  BulbOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
  CloudUploadOutlined
} from '@ant-design/icons';
import { hybridQAService } from '../../services/hybridQA';
import { getConnections } from '../../services/api';
import QAFeedbackModal from '../../components/QAFeedbackModal';
import type { QAPair, SimilarQAPair, QAPairCreate } from '../../types/hybridQA';
import type { DBConnection } from '../../types/api';

const { TabPane } = Tabs;
const { TextArea } = Input;
const { Option } = Select;

const HybridQAPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [feedbackModalVisible, setFeedbackModalVisible] = useState(false);
  const [selectedQAPair, setSelectedQAPair] = useState<QAPair | null>(null);
  const [searchResults, setSearchResults] = useState<SimilarQAPair[]>([]);
  const [stats, setStats] = useState<any>({});
  const [connections, setConnections] = useState<DBConnection[]>([]);
  const [selectedConnectionId, setSelectedConnectionId] = useState<number | null>(null);
  const [loadingConnections, setLoadingConnections] = useState(false);
  const [injectingId, setInjectingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [searchForm] = Form.useForm();

  useEffect(() => {
    loadConnections();
    loadStats();
  }, []);

  useEffect(() => {
    if (selectedConnectionId) {
      loadStats(selectedConnectionId);
    }
  }, [selectedConnectionId]);

  const loadConnections = async () => {
    try {
      setLoadingConnections(true);
      const response = await getConnections();
      setConnections(response.data);
    } catch (error) {
      message.error('获取数据库连接失败');
      console.error('获取连接失败:', error);
    } finally {
      setLoadingConnections(false);
    }
  };

  const loadStats = async (connectionId?: number) => {
    try {
      const response = await hybridQAService.getStats(connectionId);
      setStats(response);
    } catch (error) {
      console.error('加载统计信息失败:', error);
    }
  };

  const handleCreateQAPair = async (values: QAPairCreate & { inject_to_memory?: boolean }) => {
    try {
      setLoading(true);
      const { inject_to_memory, ...qaData } = values;
      const response = await hybridQAService.createQAPair(qaData);
      message.success('问答对创建成功');

      // 如果勾选了注入记忆图谱，自动注入
      if (inject_to_memory && response.qa_id) {
        try {
          setInjectingId(response.qa_id);
          await hybridQAService.injectToMemory(response.qa_id);
          message.success('已成功注入记忆图谱');
        } catch (injectError) {
          console.error('注入记忆图谱失败:', injectError);
          message.warning('问答对已创建，但注入记忆图谱失败');
        } finally {
          setInjectingId(null);
        }
      }

      setCreateModalVisible(false);
      form.resetFields();
      loadStats(selectedConnectionId || undefined); // 重新加载统计信息
    } catch (error) {
      message.error('创建失败');
      console.error('创建问答对失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInjectToMemory = async (qaPair: QAPair) => {
    try {
      setInjectingId(qaPair.id);
      await hybridQAService.injectToMemory(qaPair.id);
      message.success('已成功注入记忆图谱');
    } catch (error) {
      message.error('注入记忆图谱失败');
      console.error('注入记忆图谱失败:', error);
    } finally {
      setInjectingId(null);
    }
  };

  const handleSearchSimilar = async (values: any) => {
    const connectionId = values.connection_id || selectedConnectionId;
    if (!values.question && !connectionId) {
      message.warning('请输入问题或选择数据库连接');
      return;
    }
    try {
      setLoading(true);
      const results = await hybridQAService.searchSimilar({
        question: values.question,
        connection_id: connectionId,
        top_k: values.top_k || 5
      });
      setSearchResults(results);
    } catch (error) {
      message.error('搜索失败');
      console.error('搜索相似问答对失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = (qaPair: QAPair) => {
    setSelectedQAPair(qaPair);
    setDetailModalVisible(true);
  };

  const getQueryTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      'SELECT': 'blue',
      'JOIN': 'green',
      'AGGREGATE': 'orange',
      'GROUP_BY': 'purple',
      'ORDER_BY': 'cyan'
    };
    return colors[type] || 'default';
  };

  const getDifficultyColor = (level: number) => {
    const colors = ['#52c41a', '#334155', '#f59e0b', '#ff7a45', '#f5222d'];
    return colors[level - 1] || '#d9d9d9';
  };

  const searchColumns = [
    {
      title: '问题',
      dataIndex: ['qa_pair', 'question'],
      key: 'question',
      ellipsis: true,
      width: 300,
    },
    {
      title: 'SQL',
      dataIndex: ['qa_pair', 'sql'],
      key: 'sql',
      ellipsis: true,
      width: 400,
      render: (sql: string) => (
        <code style={{ fontSize: '12px', background: '#f5f5f5', padding: '2px 4px' }}>
          {sql}
        </code>
      ),
    },
    {
      title: '查询类型',
      dataIndex: ['qa_pair', 'query_type'],
      key: 'query_type',
      width: 100,
      render: (type: string) => (
        <Tag color={getQueryTypeColor(type)}>{type}</Tag>
      ),
    },
    {
      title: '数据库连接',
      dataIndex: ['qa_pair', 'connection_id'],
      key: 'connection_id',
      width: 120,
      render: (connectionId: number) => {
        const connection = connections.find(conn => conn.id === connectionId);
        return connection ? (
          <Tooltip title={`${connection.db_type} - ${connection.database_name}`}>
            <Tag color="blue">{connection.name}</Tag>
          </Tooltip>
        ) : (
          <Tag color="default">ID: {connectionId}</Tag>
        );
      },
    },
    {
      title: '相关度',
      dataIndex: 'final_score',
      key: 'final_score',
      width: 120,
      render: (score: number) => (
        <Progress
          percent={Math.round(score * 100)}
          size="small"
          status={score > 0.8 ? 'success' : score > 0.6 ? 'normal' : 'exception'}
        />
      ),
    },
    {
      title: '推荐理由',
      dataIndex: 'explanation',
      key: 'explanation',
      ellipsis: true,
      width: 200,
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      render: (_: any, record: SimilarQAPair) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              type="text"
              icon={<EyeOutlined />}
              onClick={() => handleViewDetail(record.qa_pair)}
            />
          </Tooltip>
          <Tooltip title="注入记忆图谱">
            <Button
              type="text"
              icon={<CloudUploadOutlined />}
              loading={injectingId === record.qa_pair.id}
              onClick={() => handleInjectToMemory(record.qa_pair)}
            />
          </Tooltip>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setSelectedQAPair(record.qa_pair);
              setFeedbackModalVisible(true);
            }}
          >
            反馈
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Card title="问答库" style={{ marginBottom: '24px' }}>
        {/* 数据库连接选择器 */}
        <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <span style={{ marginRight: '8px' }}>数据库连接:</span>
            <Select
              placeholder="选择数据库连接（可选）"
              value={selectedConnectionId}
              onChange={setSelectedConnectionId}
              loading={loadingConnections}
              style={{ width: 300 }}
              allowClear
            >
              {connections.map(conn => (
                <Option key={conn.id} value={conn.id}>
                  {conn.name} ({conn.db_type} - {conn.database_name})
                </Option>
              ))}
            </Select>
          </div>
          <Tooltip title="选择数据库连接后，统计信息和搜索结果将仅显示该连接下的问答对">
            <QuestionCircleOutlined style={{ color: '#999' }} />
          </Tooltip>
        </div>

        <Row gutter={16} style={{ marginBottom: '24px' }}>
          <Col span={6}>
            <Statistic
              title="总问答对数"
              value={stats.total_qa_pairs || 0}
              prefix={<DatabaseOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="已验证数"
              value={stats.verified_qa_pairs || 0}
              prefix={<BulbOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="平均成功率"
              value={stats.average_success_rate || 0}
              precision={2}
              suffix="%"
              prefix={<RobotOutlined />}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="验证率"
              value={stats.total_qa_pairs > 0 ?
                ((stats.verified_qa_pairs / stats.total_qa_pairs) * 100) : 0}
              precision={1}
              suffix="%"
            />
          </Col>
        </Row>

        <Space style={{ marginBottom: '16px' }}>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setCreateModalVisible(true);
              // 如果选择了连接，设置为默认值
              if (selectedConnectionId) {
                form.setFieldsValue({ connection_id: selectedConnectionId });
              }
            }}
          >
            创建问答对
          </Button>
        </Space>

        <Tabs defaultActiveKey="search">
          <TabPane tab="智能搜索" key="search">
            <Card size="small" style={{ marginBottom: '16px' }}>
              <Form
                form={searchForm}
                layout="inline"
                onFinish={handleSearchSimilar}
              >
                <Form.Item
                  name="question"
                >
                  <Input
                    placeholder="输入自然语言问题（可选，留空则查询该连接下所有问答对）"
                    style={{ width: 400 }}
                  />
                </Form.Item>
                <Form.Item name="connection_id">
                  <Select
                    placeholder="选择数据库连接"
                    style={{ width: 200 }}
                    allowClear
                  >
                    {connections.map(conn => (
                      <Option key={conn.id} value={conn.id}>
                        {conn.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>
                <Form.Item name="top_k" initialValue={5}>
                  <InputNumber
                    placeholder="返回数量"
                    min={1}
                    max={20}
                    style={{ width: 100 }}
                  />
                </Form.Item>
                <Form.Item>
                  <Button
                    type="primary"
                    htmlType="submit"
                    loading={loading}
                    icon={<SearchOutlined />}
                  >
                    搜索
                  </Button>
                </Form.Item>
              </Form>
            </Card>

            <Table
              columns={searchColumns}
              dataSource={searchResults}
              loading={loading}
              rowKey={(record) => record.qa_pair.id}
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showQuickJumper: true,
                showTotal: (total) => `共 ${total} 条记录`,
              }}
              scroll={{ x: 1200 }}
            />
          </TabPane>

          <TabPane tab="统计分析" key="stats">
            <Row gutter={16}>
              <Col span={12}>
                <Card title="查询类型分布" size="small">
                  {stats.query_types && Object.entries(stats.query_types).map(([type, count]: [string, any]) => (
                    <div key={type} style={{ marginBottom: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Tag color={getQueryTypeColor(type)} style={{ fontSize: '12px' }}>{type}</Tag>
                        <span>{count}</span>
                      </div>
                      <Progress
                        percent={stats.total_qa_pairs > 0 ? (count / stats.total_qa_pairs) * 100 : 0}
                        size="small"
                        showInfo={false}
                      />
                    </div>
                  ))}
                </Card>
              </Col>
              <Col span={12}>
                <Card title="难度分布" size="small">
                  {stats.difficulty_distribution && Object.entries(stats.difficulty_distribution).map(([level, count]: [string, any]) => (
                    <div key={level} style={{ marginBottom: '8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span>难度 {level}</span>
                        <span>{count}</span>
                      </div>
                      <Progress
                        percent={stats.total_qa_pairs > 0 ? (count / stats.total_qa_pairs) * 100 : 0}
                        size="small"
                        showInfo={false}
                        strokeColor={getDifficultyColor(parseInt(level))}
                      />
                    </div>
                  ))}
                </Card>
              </Col>
            </Row>
          </TabPane>
        </Tabs>
      </Card>

      {/* 创建问答对模态框 */}
      <Modal
        title="创建问答对"
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={null}
        width={800}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreateQAPair}
        >
          <Form.Item
            name="question"
            label="自然语言问题"
            rules={[{ required: true, message: '请输入问题' }]}
          >
            <TextArea rows={3} placeholder="输入自然语言问题" />
          </Form.Item>

          <Form.Item
            name="sql"
            label="SQL语句"
            rules={[{ required: true, message: '请输入SQL语句' }]}
          >
            <TextArea rows={5} placeholder="输入对应的SQL语句" />
          </Form.Item>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="connection_id"
                label="数据库连接"
                rules={[{ required: true, message: '请选择数据库连接' }]}
              >
                <Select
                  style={{ width: '100%' }}
                  placeholder="选择数据库连接"
                  loading={loadingConnections}
                >
                  {connections.map(conn => (
                    <Option key={conn.id} value={conn.id}>
                      {conn.name} ({conn.db_type})
                    </Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="query_type"
                label="查询类型"
                initialValue="SELECT"
              >
                <Select>
                  <Option value="SELECT">SELECT</Option>
                  <Option value="JOIN">JOIN</Option>
                  <Option value="AGGREGATE">AGGREGATE</Option>
                  <Option value="GROUP_BY">GROUP_BY</Option>
                  <Option value="ORDER_BY">ORDER_BY</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="difficulty_level"
                label="难度等级"
                initialValue={3}
              >
                <InputNumber min={1} max={5} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="verified"
            label="已验证"
            valuePropName="checked"
            initialValue={false}
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="inject_nl2sql"
            label="注入 NL2SQL"
            valuePropName="checked"
            initialValue={false}
          >
            <Switch />
          </Form.Item>

          <Form.Item
            name="inject_to_memory"
            label="注入记忆图谱"
            valuePropName="checked"
            initialValue={true}
            tooltip="创建后自动将该问答对注入知识图谱记忆系统，供智能查询时检索"
          >
            <Switch />
          </Form.Item>

          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                创建
              </Button>
              <Button onClick={() => setCreateModalVisible(false)}>
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情模态框 */}
      <Modal
        title="问答对详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={[
          selectedQAPair ? (
            <Button
              key="inject"
              type="primary"
              icon={<CloudUploadOutlined />}
              loading={injectingId === selectedQAPair.id}
              onClick={() => handleInjectToMemory(selectedQAPair)}
            >
              注入记忆图谱
            </Button>
          ) : null,
          <Button key="close" onClick={() => setDetailModalVisible(false)}>
            关闭
          </Button>
        ]}
        width={800}
      >
        {selectedQAPair && (
          <div>
            <Divider orientation="left">基本信息</Divider>
            <Row gutter={16}>
              <Col span={12}>
                <p><strong>ID:</strong> {selectedQAPair.id}</p>
                <p><strong>查询类型:</strong> <Tag color={getQueryTypeColor(selectedQAPair.query_type)}>{selectedQAPair.query_type}</Tag></p>
                <p><strong>难度等级:</strong> {selectedQAPair.difficulty_level}</p>
                <p><strong>数据库连接:</strong> {(() => {
                  const connection = connections.find(conn => conn.id === selectedQAPair.connection_id);
                  return connection ? (
                    <Tag color="blue">{connection.name} ({connection.db_type})</Tag>
                  ) : (
                    <Tag color="default">ID: {selectedQAPair.connection_id}</Tag>
                  );
                })()}</p>
              </Col>
              <Col span={12}>
                <p><strong>成功率:</strong> {(selectedQAPair.success_rate * 100).toFixed(1)}%</p>
                <p><strong>已验证:</strong> {selectedQAPair.verified ? '是' : '否'}</p>
                <p><strong>创建时间:</strong> {new Date(selectedQAPair.created_at).toLocaleString()}</p>
              </Col>
            </Row>

            <Divider orientation="left">问题</Divider>
            <p style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px' }}>
              {selectedQAPair.question}
            </p>

            <Divider orientation="left">SQL语句</Divider>
            <pre style={{ background: '#f5f5f5', padding: '12px', borderRadius: '4px', overflow: 'auto' }}>
              {selectedQAPair.sql}
            </pre>

            <Divider orientation="left">使用的表</Divider>
            <div>
              {selectedQAPair.used_tables?.map((table, index) => (
                <Tag key={index} color="blue">{table}</Tag>
              ))}
            </div>

            <Divider orientation="left">提及的实体</Divider>
            <div>
              {selectedQAPair.mentioned_entities?.map((entity, index) => (
                <Tag key={index} color="green">{entity}</Tag>
              ))}
            </div>
          </div>
        )}
      </Modal>

      {/* 反馈模态框 */}
      <QAFeedbackModal
        visible={feedbackModalVisible}
        onCancel={() => setFeedbackModalVisible(false)}
        qaPair={selectedQAPair}
        onFeedbackSubmitted={() => {
          // 重新加载统计信息
          loadStats(selectedConnectionId || undefined);
        }}
      />
    </div>
  );
};

export default HybridQAPage;
