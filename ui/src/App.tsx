import React from 'react';
import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Layout, Menu, theme } from 'antd';
import type { MenuProps } from 'antd';
import {
  DatabaseOutlined,
  TableOutlined,
  TagsOutlined,
  BookOutlined,
  HomeOutlined,
  ApiOutlined,
  ShareAltOutlined,
  BulbOutlined,
  MessageOutlined
} from '@ant-design/icons';

import './styles/Header.css';
import './styles/global-styles.css';

import HomePage from './pages/HomePage';
import ConnectionsPage from './pages/ConnectionsPage';
import SchemaManagementPage from './pages/SchemaManagementPage';
import ValueMappingsPage from './pages/ValueMappingsPage';
import GraphVisualizationPage from './pages/GraphVisualizationPage';
import HybridQAPage from './pages/HybridQA';
import SmartChatPage from './pages/SmartChat';

const { Header, Content } = Layout;

const App: React.FC = () => {
  const location = useLocation();

  const {
    token: { colorBgContainer },
  } = theme.useToken();

  // 子菜单项
  const items: MenuProps['items'] = [
    {
      key: '/',
      icon: <HomeOutlined />,
      label: <Link to="/">工作台</Link>,
    },
    {
      key: '/smart-chat',
      icon: <MessageOutlined />,
      label: <Link to="/smart-chat">智能查询</Link>,
    },
    {
      key: '/hybrid-qa',
      icon: <BookOutlined />,
      label: <Link to="/hybrid-qa">问答库</Link>,
    },
    {
      key: '/graph-visualization',
      icon: <ShareAltOutlined />,
      label: <Link to="/graph-visualization">知识图谱</Link>,
    },
    {
      key: '/value-mappings',
      icon: <TagsOutlined />,
      label: <Link to="/value-mappings">语义配置</Link>,
    },
    {
      key: '/schema',
      icon: <TableOutlined />,
      label: <Link to="/schema">数据模型</Link>,
    },
    {
      key: '/connections',
      icon: <DatabaseOutlined />,
      label: <Link to="/connections">数据源</Link>,
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header className="app-header">
        <ApiOutlined style={{ fontSize: '28px', color: '#f59e0b', marginRight: '16px' }} />
        <div className="app-title">
          问数 · 智能数据查询平台
        </div>
        <Menu
          className="app-menu"
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={items}
        />
      </Header>
      <Content style={{
        padding: location.pathname === '/' || location.pathname === '/smart-chat' ? '0' : '0 50px',
        marginTop: location.pathname === '/' || location.pathname === '/smart-chat' ? 0 : 16,
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden'
      }}>
        <div style={{
          padding: location.pathname === '/' || location.pathname === '/smart-chat' ? 0 : 24,
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          background: location.pathname === '/' || location.pathname === '/smart-chat' ? 'transparent' : colorBgContainer,
          borderRadius: location.pathname === '/' || location.pathname === '/smart-chat' ? '0' : '2px',
          overflow: 'hidden'
        }}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/hybrid-qa" element={<HybridQAPage />} />
            <Route path="/smart-chat" element={<SmartChatPage />} />
            <Route path="/connections" element={<ConnectionsPage />} />
            <Route path="/schema" element={<SchemaManagementPage />} />
            <Route path="/graph-visualization" element={<GraphVisualizationPage />} />
            <Route path="/value-mappings" element={<ValueMappingsPage />} />
          </Routes>
        </div>
      </Content>
    </Layout>
  );
};

export default App;
