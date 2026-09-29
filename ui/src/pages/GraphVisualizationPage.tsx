import React, { useState, useEffect, useCallback } from 'react';
import {
  Tabs,
  Select,
  Spin,
  Empty,
  Typography,
  Tag,
  Card,
  Space,
  Button,
  Badge,
  Modal,
  message,
} from 'antd';
import {
  DatabaseOutlined,
  ShareAltOutlined,
  NodeIndexOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import type Graph from 'graphology';
import SigmaCanvas from '../components/SigmaCanvas';
import { getGraphs, getGraphData, getMemoryGraphData, deleteGraph, deleteMemoryNode } from '../services/api';
import {
  schemaToGraphology,
  memoryToGraphology,
  type SigmaNodeAttributes,
  type SigmaEdgeAttributes,
} from '../lib/graph-adapter';

const { Title, Text } = Typography;

const GraphVisualizationPage: React.FC = () => {
  interface GraphItem {
    id: string;
    name: string;
    db_type: string;
    connection_id: number;
  }

  const [graphs, setGraphs] = useState<GraphItem[]>([]);
  const [selectedGraph, setSelectedGraph] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'schema' | 'memory'>('schema');
  const [loading, setLoading] = useState(false);
  const [selectedNodeData, setSelectedNodeData] = useState<any>(null);
  const [sigmaGraph, setSigmaGraph] = useState<Graph<SigmaNodeAttributes, SigmaEdgeAttributes> | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // 加载图谱列表
  const loadGraphList = useCallback(async () => {
    try {
      const res = await getGraphs();
      const list: GraphItem[] = res.data || [];
      setGraphs(list);
      if (list.length > 0 && !selectedGraph) {
        setSelectedGraph(list[0].id);
      }
    } catch (e) {
      console.error('Failed to load graph list:', e);
    }
  }, [selectedGraph]);

  useEffect(() => {
    loadGraphList();
  }, [loadGraphList]);

  // 删除图谱
  const handleDeleteGraph = useCallback(async () => {
    if (!selectedGraph) return;
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除图谱 "${selectedGraph}" 吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      async onOk() {
        try {
          await deleteGraph(selectedGraph);
          setSelectedGraph('');
          setSigmaGraph(null);
          await loadGraphList();
        } catch (e) {
          console.error('Failed to delete graph:', e);
          Modal.error({ title: '删除失败', content: '删除图谱时出错，请稍后重试。' });
        }
      },
    });
  }, [selectedGraph, loadGraphList]);

  // 加载图谱数据
  const loadData = useCallback(async () => {
    if (!selectedGraph) return;
    setLoading(true);
    setSelectedNodeData(null);
    setSelectedNodeId(null);

    try {
      let graph: Graph<SigmaNodeAttributes, SigmaEdgeAttributes> | null = null;
      if (activeTab === 'schema') {
        const res = await getGraphData(selectedGraph);
        graph = schemaToGraphology(res.data);
      } else {
        const res = await getMemoryGraphData(selectedGraph);
        graph = memoryToGraphology(res.data);
      }
      setSigmaGraph(graph);
    } catch (e) {
      console.error('Failed to load graph data:', e);
      setSigmaGraph(null);
    } finally {
      setLoading(false);
    }
  }, [selectedGraph, activeTab]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleNodeClick = useCallback((nodeId: string, data: any) => {
    if (!nodeId || !data) {
      setSelectedNodeData(null);
      setSelectedNodeId(null);
      return;
    }
    setSelectedNodeId(nodeId);
    setSelectedNodeData({
      label: data.label,
      nodeType: data.nodeType,
      properties: data.properties || {},
    });
  }, []);

  const handleDeleteNode = useCallback(async (nodeId: string) => {
    if (!selectedGraph || activeTab !== 'memory') return;
    try {
      await deleteMemoryNode(selectedGraph, nodeId);
      message.success('节点已删除');
      // 刷新图谱数据
      await loadData();
      setSelectedNodeData(null);
      setSelectedNodeId(null);
    } catch (e) {
      console.error('Failed to delete node:', e);
      message.error('删除节点失败');
    }
  }, [selectedGraph, activeTab, loadData]);

  const tabItems = [
    {
      key: 'schema',
      label: (
        <span>
          <DatabaseOutlined /> Schema 图谱
        </span>
      ),
    },
    {
      key: 'memory',
      label: (
        <span>
          <NodeIndexOutlined /> 记忆图谱
        </span>
      ),
    },
  ];

  const nodeCount = sigmaGraph?.order || 0;
  const edgeCount = sigmaGraph?.size || 0;

  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        height: '100%',
      }}
    >
      {/* 工具栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          padding: '0 0 12px 0',
          borderBottom: '1px solid #f0f0f0',
          flexWrap: 'wrap',
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          <ShareAltOutlined /> 知识图谱
        </Title>

        <Select
          style={{ width: 280 }}
          placeholder="选择数据库图谱"
          value={selectedGraph || undefined}
          onChange={(val) => setSelectedGraph(val)}
          options={graphs.map((g) => ({
            label: `${g.name} (${g.db_type})`,
            value: g.id,
          }))}
          allowClear
        />

        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'schema' | 'memory')}
          items={tabItems}
          style={{ marginBottom: 0 }}
        />

        <Button
          icon={<ReloadOutlined />}
          onClick={loadData}
          loading={loading}
          disabled={!selectedGraph}
        >
          刷新
        </Button>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 12, alignItems: 'center' }}>
          <Button
            size="small"
            type="text"
            danger
            onClick={handleDeleteGraph}
            disabled={!selectedGraph}
          >
            删除图谱
          </Button>
          <Badge count={nodeCount} overflowCount={9999} color="#334155">
            <Text type="secondary">节点</Text>
          </Badge>
          <Badge count={edgeCount} overflowCount={9999} color="#52c41a">
            <Text type="secondary">关系</Text>
          </Badge>
        </div>
      </div>

      {/* 主内容区 */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          marginTop: 12,
          gap: 16,
        }}
      >
        {/* 图谱画布 */}
        <div
          style={{
            flex: 1,
            position: 'relative',
            border: '1px solid #1e1e2e',
            borderRadius: 12,
            overflow: 'hidden',
            background: '#0f0f1a',
          }}
        >
          <SigmaCanvas
            graph={sigmaGraph}
            onNodeClick={handleNodeClick}
            selectedNodeId={selectedNodeId}
            activeTab={activeTab}
            onDeleteNode={handleDeleteNode}
          />

          {loading && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'rgba(15, 15, 26, 0.8)',
                zIndex: 10,
              }}
            >
              <Spin size="large" tip="加载图谱中..." />
            </div>
          )}

          {nodeCount === 0 && !loading && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: '#0f0f1a',
              }}
            >
              <Empty
                description={
                  selectedGraph
                    ? '暂无图谱数据，请先在"智能查询"或"数据模型"中生成图谱'
                    : '请先选择一个数据库图谱'
                }
              />
            </div>
          )}
        </div>

        {/* 详情侧边栏 */}
        {selectedNodeData && (
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <InfoCircleOutlined />
                <span>节点详情</span>
              </div>
            }
            size="small"
            style={{
              width: 320,
              overflowY: 'auto',
              maxHeight: '100%',
              flexShrink: 0,
            }}
            bodyStyle={{ padding: 12 }}
          >
            <Space direction="vertical" style={{ width: '100%' }} size="small">
              <div>
                <Text strong>名称：</Text>
                <Text>{selectedNodeData.label}</Text>
              </div>
              <div>
                <Text strong>类型：</Text>
                <Tag color="blue">{selectedNodeData.nodeType}</Tag>
              </div>

              {selectedNodeData.properties &&
                Object.entries(selectedNodeData.properties).map(([key, value]: [string, any]) => (
                  <div key={key}>
                    <Text strong>{key}：</Text>
                    <Text
                      style={{
                        wordBreak: 'break-all',
                        display: 'block',
                        marginTop: 2,
                        padding: 4,
                        background: '#f5f5f5',
                        borderRadius: 4,
                        fontSize: 12,
                      }}
                    >
                      {String(value)}
                    </Text>
                  </div>
                ))}
            </Space>
          </Card>
        )}
      </div>
    </div>
  );
};

export default GraphVisualizationPage;
