import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  Row,
  Col,
  Button,
  Typography,
  Space,
  Badge
} from 'antd';
import {
  RocketOutlined,
  DatabaseOutlined,
  TableOutlined,
  TagsOutlined,
  ShareAltOutlined,
  MessageOutlined,
  BookOutlined,
  ThunderboltOutlined,
  ArrowRightOutlined
} from '@ant-design/icons';

const { Title: AntTitle, Paragraph, Text } = Typography;

const HomePage: React.FC = () => {
  const navigate = useNavigate();

  const features = [
    {
      icon: <MessageOutlined />,
      title: '智能查询',
      desc: '自然语言转 SQL，零代码完成复杂数据分析',
      color: '#334155',
      tag: '核心',
      tagColor: '#334155'
    },
    {
      icon: <BookOutlined />,
      title: '问答库',
      desc: '沉淀高频业务问题，持续优化查询准确率',
      color: '#475569',
      tag: '知识',
      tagColor: '#475569'
    },
    {
      icon: <ShareAltOutlined />,
      title: '知识图谱',
      desc: '可视化 Schema 与记忆图谱，洞察数据关系',
      color: '#f59e0b',
      tag: '可视化',
      tagColor: '#d97706'
    },
    {
      icon: <TagsOutlined />,
      title: '语义配置',
      desc: '配置业务语义与同义词，提升 NL2SQL 理解能力',
      color: '#0d9488',
      tag: '增强',
      tagColor: '#0f766e'
    },
    {
      icon: <TableOutlined />,
      title: '数据模型',
      desc: '自动发现数据库结构，一键构建分析模型',
      color: '#059669',
      tag: '建模',
      tagColor: '#047857'
    },
    {
      icon: <DatabaseOutlined />,
      title: '数据源',
      desc: '统一管理多源数据库连接，支持多种数据库类型',
      color: '#dc2626',
      tag: '基础',
      tagColor: '#b91c1c'
    }
  ];

  const stats = [
    { label: '支持数据库', value: 'MySQL / PG / SQLite / ...' },
    { label: '查询准确率', value: '持续提升' },
    { label: '响应方式', value: '流式实时输出' }
  ];

  return (
    <div style={{ padding: '20px', minHeight: '100vh', background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%)' }}>
      {/* Hero 区域 */}
      <div style={{ textAlign: 'center', marginBottom: '48px' }}>
        <Card
          style={{
            borderRadius: '24px',
            background: 'rgba(255, 255, 255, 0.95)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            maxWidth: 900,
            margin: '0 auto'
          }}
          bodyStyle={{ padding: '48px 32px' }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            {/* 顶部徽章 */}
            <Badge
              count="NL2SQL"
              style={{ backgroundColor: '#f59e0b', fontSize: 12, fontWeight: 600, padding: '0 8px' }}
            />

            <ThunderboltOutlined style={{ fontSize: '72px', color: '#f59e0b' }} />

            <AntTitle
              level={1}
              style={{
                margin: 0,
                background: 'linear-gradient(45deg, #334155, #f59e0b)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                fontSize: '42px',
                fontWeight: 800
              }}
            >
              问数 · 智能数据查询平台
            </AntTitle>

            <Paragraph style={{ fontSize: '18px', color: '#555', maxWidth: '600px', margin: '0 auto', lineHeight: 1.6 }}>
              基于大语言模型与知识图谱的下一代数据查询平台，
              <br />
              让业务人员用自然语言即可获取深度数据洞察
            </Paragraph>

            {/* 核心指标 */}
            <Row gutter={48} justify="center" style={{ margin: '16px 0' }}>
              {stats.map((s, i) => (
                <Col key={i}>
                  <div style={{ textAlign: 'center' }}>
                    <Text strong style={{ fontSize: 16, color: '#f59e0b' }}>{s.value}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 12 }}>{s.label}</Text>
                  </div>
                </Col>
              ))}
            </Row>

            <Button
              type="primary"
              size="large"
              icon={<RocketOutlined />}
              onClick={() => navigate('/smart-chat')}
              style={{
                height: '56px',
                fontSize: '18px',
                borderRadius: '28px',
                padding: '0 48px',
                boxShadow: '0 8px 24px rgba(245,158,11,0.35)',
                fontWeight: 600
              }}
            >
              开始对话
              <ArrowRightOutlined style={{ marginLeft: 8 }} />
            </Button>
          </Space>
        </Card>
      </div>

      {/* 功能特性区域 */}
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        <AntTitle
          level={2}
          style={{
            textAlign: 'center',
            color: 'white',
            marginBottom: '8px',
            fontWeight: 700
          }}
        >
          核心能力
        </AntTitle>
        <Paragraph style={{ textAlign: 'center', color: 'rgba(255,255,255,0.8)', marginBottom: '36px', fontSize: 15 }}>
          从数据连接到智能查询，覆盖数据分析全链路
        </Paragraph>

        <Row gutter={[24, 24]}>
          {features.map((feature, index) => (
            <Col xs={24} sm={12} md={8} key={index}>
              <Card
                hoverable
                onClick={() => {
                  const routeMap: Record<string, string> = {
                    '智能查询': '/smart-chat',
                    '问答库': '/hybrid-qa',
                    '知识图谱': '/graph-visualization',
                    '语义配置': '/value-mappings',
                    '数据模型': '/schema',
                    '数据源': '/connections'
                  };
                  if (routeMap[feature.title]) navigate(routeMap[feature.title]);
                }}
                style={{
                  minHeight: '220px',
                  borderRadius: '16px',
                  background: 'rgba(255, 255, 255, 0.95)',
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'transform 0.3s, box-shadow 0.3s'
                }}
                bodyStyle={{ padding: '28px 20px' }}
              >
                <Badge.Ribbon text={feature.tag} color={feature.tagColor} style={{ fontSize: 11 }}>
                  <div style={{ paddingTop: 12 }}>
                    <div style={{ fontSize: '44px', color: feature.color, marginBottom: '12px' }}>
                      {feature.icon}
                    </div>
                    <AntTitle level={4} style={{ margin: '8px 0', color: '#1f1f1f', fontSize: 18 }}>
                      {feature.title}
                    </AntTitle>
                    <Paragraph style={{ color: '#666', fontSize: '13px', lineHeight: 1.6, margin: 0 }}>
                      {feature.desc}
                    </Paragraph>
                  </div>
                </Badge.Ribbon>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </div>
  );
};

export default HomePage;
