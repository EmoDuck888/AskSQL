import React, { useState, useEffect } from 'react';
import {
  Table, Button, Modal, Form, Input, Select,
  Space, message, Popconfirm, Card, Typography, Switch, Tabs
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  CheckCircleOutlined, DatabaseOutlined, EyeOutlined,
  LinkOutlined
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import DatabaseConnectModal from '../components/modals/DatabaseConnectModal';

const { Option } = Select;
const { Title } = Typography;
const { TabPane } = Tabs;

interface Connection {
  id: number;
  name: string;
  db_type: string;
  host: string;
  port: number;
  username: string;
  database_name: string;
  connection_url: string;
  extra_params: Record<string, any>;
  falkordb_graph_id?: string;
  status: string;
  created_at: string;
  updated_at: string;
}

// Database type configurations
const DB_TYPES = [
  { value: 'mysql', label: 'MySQL', port: 3306 },
  { value: 'postgresql', label: 'PostgreSQL', port: 5432 },
  { value: 'sqlite', label: 'SQLite', port: null },
  { value: 'bigquery', label: 'BigQuery', port: null },
  { value: 'clickhouse', label: 'ClickHouse', port: 8123 },
  { value: 'duckdb', label: 'DuckDB', port: null },
  { value: 'mssql', label: 'SQL Server', port: 1433 },
  { value: 'oracle', label: 'Oracle', port: 1521 },
  { value: 'presto', label: 'Presto', port: 443 },
  { value: 'snowflake', label: 'Snowflake', port: null },
];

// Determine which fields are needed for each DB type
const getDbFieldConfig = (dbType: string) => {
  const config: Record<string, { showHost: boolean; showPort: boolean; showUsername: boolean; showPassword: boolean; showDatabase: boolean; showExtra: boolean; extraFields: string[] }> = {
    mysql: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: false, extraFields: [] },
    postgresql: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: false, extraFields: [] },
    sqlite: { showHost: false, showPort: false, showUsername: false, showPassword: false, showDatabase: true, showExtra: false, extraFields: [] },
    bigquery: { showHost: false, showPort: false, showUsername: false, showPassword: false, showDatabase: false, showExtra: true, extraFields: ['project_id', 'credentials_file', 'dataset'] },
    clickhouse: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: false, extraFields: [] },
    duckdb: { showHost: false, showPort: false, showUsername: false, showPassword: false, showDatabase: true, showExtra: false, extraFields: [] },
    mssql: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: false, extraFields: [] },
    oracle: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: false, extraFields: [] },
    presto: { showHost: true, showPort: true, showUsername: true, showPassword: true, showDatabase: true, showExtra: true, extraFields: ['catalog'] },
    snowflake: { showHost: false, showPort: false, showUsername: true, showPassword: true, showDatabase: true, showExtra: true, extraFields: ['account', 'warehouse', 'role'] },
  };
  return config[dbType] || config.mysql;
};

const ConnectionsPage: React.FC = () => {
  const navigate = useNavigate();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [connectModalVisible, setConnectModalVisible] = useState<boolean>(false);
  const [editingConnection, setEditingConnection] = useState<Connection | null>(null);
  const [discoveringSchema, setDiscoveringSchema] = useState<boolean>(false);
  const [useUrlMode, setUseUrlMode] = useState<boolean>(false);
  const [selectedDbType, setSelectedDbType] = useState<string>('mysql');
  const [form] = Form.useForm();

  useEffect(() => {
    fetchConnections();
  }, []);

  const fetchConnections = async () => {
    setLoading(true);
    try {
      const response = await api.getConnections();
      setConnections(response.data);
    } catch (error) {
      message.error('获取连接失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const showModal = (connection?: Connection) => {
    setEditingConnection(connection || null);
    setUseUrlMode(false);
    form.resetFields();
    if (connection) {
      setSelectedDbType(connection.db_type);
      setUseUrlMode(!!connection.connection_url);
      const baseValues: any = {
        name: connection.name,
        db_type: connection.db_type,
        host: connection.host,
        port: connection.port,
        username: connection.username,
        database_name: connection.database_name,
        connection_url: connection.connection_url,
      };
      // Populate extra params fields
      if (connection.extra_params) {
        Object.entries(connection.extra_params).forEach(([key, value]) => {
          baseValues[`extra_${key}`] = value;
        });
      }
      form.setFieldsValue(baseValues);
    } else {
      setSelectedDbType('mysql');
      form.setFieldsValue({ db_type: 'mysql', port: 3306 });
    }
    setModalVisible(true);
  };

  const handleCancel = () => {
    setModalVisible(false);
  };

  const buildPayload = (values: any) => {
    const payload: any = {
      name: values.name,
      db_type: values.db_type,
    };

    if (useUrlMode && values.connection_url) {
      payload.connection_url = values.connection_url;
    } else {
      const config = getDbFieldConfig(values.db_type);
      if (config.showHost) payload.host = values.host;
      if (config.showPort) payload.port = values.port ? parseInt(values.port) : null;
      if (config.showUsername) payload.username = values.username;
      if (config.showPassword) payload.password = values.password;
      if (config.showDatabase) payload.database_name = values.database_name;

      // Build extra_params
      if (config.showExtra && config.extraFields.length > 0) {
        const extra: Record<string, any> = {};
        config.extraFields.forEach((field) => {
          const val = values[`extra_${field}`];
          if (val !== undefined && val !== '') {
            extra[field] = val;
          }
        });
        if (Object.keys(extra).length > 0) {
          payload.extra_params = extra;
        }
      }
    }

    return payload;
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      const payload = buildPayload(values);

      if (editingConnection) {
        await api.updateConnection(editingConnection.id, payload);
        message.success('连接更新成功');
        setModalVisible(false);
        fetchConnections();
      } else {
        setModalVisible(false);
        const createResponse = await api.createConnection(payload);
        message.success('连接创建成功');
        fetchConnections();
        await handleDiscoverSchema(createResponse.data.id);
      }
    } catch (error) {
      message.error('保存连接失败');
      console.error(error);
    }
  };

  const handleDiscoverSchema = async (connectionId: number) => {
    try {
      setDiscoveringSchema(true);
      message.loading({ content: '正在分析数据库结构...', key: 'discoverSchema', duration: 0 });

      const response = await api.discoverAndSaveSchema(connectionId);

      if (response.data.status === 'success') {
        message.success({ content: '数据库结构分析完成', key: 'discoverSchema' });
      } else {
        message.error({ content: '数据库结构分析失败', key: 'discoverSchema' });
      }
    } catch (error) {
      console.error('Failed to discover schema:', error);
      message.error({ content: '数据库结构分析失败', key: 'discoverSchema' });
    } finally {
      setDiscoveringSchema(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await api.deleteConnection(id);
      message.success('连接删除成功');
      fetchConnections();
    } catch (error) {
      message.error('删除连接失败');
      console.error(error);
    }
  };

  const handleTest = async (id: number) => {
    try {
      const response = await api.testConnection(id);
      if (response.data.status === 'success') {
        message.success('连接测试成功');
      } else {
        message.error(`连接测试失败: ${response.data.message}`);
      }
    } catch (error) {
      message.error('连接测试失败');
      console.error(error);
    }
  };

  const handleViewSchema = (record: Connection) => {
    if (record.falkordb_graph_id) {
      navigate(`/schema?connection_id=${record.id}`);
    } else {
      message.warning('该连接尚未加载 Schema，请先连接数据库');
    }
  };

  const handleConnectDatabase = (record: Connection) => {
    setConnectModalVisible(true);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active': return 'green';
      case 'error': return 'red';
      case 'pending': return 'orange';
      default: return 'default';
    }
  };

  const getStatusText = (status: string) => {
    switch (status) {
      case 'active': return '已连接';
      case 'error': return '错误';
      case 'pending': return '待连接';
      default: return status;
    }
  };

  const handleDbTypeChange = (value: string) => {
    setSelectedDbType(value);
    const dbConfig = DB_TYPES.find((d) => d.value === value);
    if (dbConfig && dbConfig.port) {
      form.setFieldsValue({ port: dbConfig.port });
    } else {
      form.setFieldsValue({ port: undefined });
    }
  };

  const renderExtraFields = () => {
    const config = getDbFieldConfig(selectedDbType);
    if (!config.showExtra) return null;

    return config.extraFields.map((field) => (
      <Form.Item
        key={field}
        name={`extra_${field}`}
        label={field.charAt(0).toUpperCase() + field.slice(1).replace('_', ' ')}
      >
        <Input placeholder={`Enter ${field}`} />
      </Form.Item>
    ));
  };

  const renderBasicForm = () => {
    const config = getDbFieldConfig(selectedDbType);

    return (
      <>
        {config.showHost && (
          <Form.Item
            name="host"
            label="主机"
            rules={[{ required: true, message: '请输入主机' }]}
          >
            <Input placeholder="localhost" />
          </Form.Item>
        )}

        {config.showPort && (
          <Form.Item
            name="port"
            label="端口"
            rules={[{ required: true, message: '请输入端口' }]}
          >
            <Input type="number" placeholder={String(DB_TYPES.find(d => d.value === selectedDbType)?.port || '')} />
          </Form.Item>
        )}

        {config.showUsername && (
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="root" />
          </Form.Item>
        )}

        {config.showPassword && (
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: !editingConnection, message: '请输入密码' }]}
          >
            <Input.Password placeholder="密码" />
          </Form.Item>
        )}

        {config.showDatabase && (
          <Form.Item
            name="database_name"
            label={selectedDbType === 'sqlite' || selectedDbType === 'duckdb' ? '数据库文件路径' : '数据库名称'}
            rules={[{ required: true, message: '请输入数据库名称' }]}
          >
            <Input placeholder={selectedDbType === 'sqlite' ? '/path/to/database.db' : 'my_database'} />
          </Form.Item>
        )}

        {renderExtraFields()}
      </>
    );
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '类型',
      dataIndex: 'db_type',
      key: 'db_type',
      render: (type: string) => DB_TYPES.find(d => d.value === type)?.label || type,
    },
    {
      title: '主机',
      dataIndex: 'host',
      key: 'host',
    },
    {
      title: '端口',
      dataIndex: 'port',
      key: 'port',
    },
    {
      title: '数据库',
      dataIndex: 'database_name',
      key: 'database_name',
    },
    {
      title: '状态',
      key: 'status',
      render: (_: any, record: Connection) => (
        <span style={{ color: getStatusColor(record.status) }}>
          {getStatusText(record.status)}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: Connection) => (
        <Space size="middle">
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={() => handleTest(record.id)}
            size="small"
          >
            测试
          </Button>
          <Button
            icon={<LinkOutlined />}
            onClick={() => handleConnectDatabase(record)}
            size="small"
          >
            连接数据库
          </Button>
          <Button
            icon={<EyeOutlined />}
            onClick={() => handleViewSchema(record)}
            size="small"
            disabled={!record.falkordb_graph_id}
          >
            查看Schema
          </Button>
          <Button
            icon={<DatabaseOutlined />}
            onClick={() => handleDiscoverSchema(record.id)}
            size="small"
            loading={discoveringSchema}
          >
            分析结构
          </Button>
          <Button
            icon={<EditOutlined />}
            onClick={() => showModal(record)}
            size="small"
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个连接吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="是"
            cancelText="否"
          >
            <Button
              danger
              icon={<DeleteOutlined />}
              size="small"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4}>数据源</Title>
          <Space>
            <Button
              icon={<LinkOutlined />}
              onClick={() => setConnectModalVisible(true)}
            >
              连接数据库
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => showModal()}
              disabled={discoveringSchema}
            >
              添加连接
            </Button>
          </Space>
        </div>

        <Table
          columns={columns}
          dataSource={connections}
          rowKey="id"
          loading={loading || discoveringSchema}
        />
      </Card>

      <Modal
        title={editingConnection ? '编辑连接' : '添加连接'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={handleCancel}
        width={640}
        confirmLoading={discoveringSchema}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ db_type: 'mysql', port: 3306 }}
          disabled={discoveringSchema}
        >
          <Form.Item
            name="name"
            label="连接名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="我的数据库" />
          </Form.Item>

          <Form.Item
            name="db_type"
            label="数据库类型"
            rules={[{ required: true, message: '请选择数据库类型' }]}
          >
            <Select placeholder="选择数据库类型" onChange={handleDbTypeChange}>
              {DB_TYPES.map((db) => (
                <Option key={db.value} value={db.value}>{db.label}</Option>
              ))}
            </Select>
          </Form.Item>

          <div style={{ marginBottom: 16 }}>
            <span style={{ marginRight: 8 }}>连接方式:</span>
            <Switch
              checked={useUrlMode}
              onChange={setUseUrlMode}
              checkedChildren="URL模式"
              unCheckedChildren="表单模式"
            />
          </div>

          {useUrlMode ? (
            <Form.Item
              name="connection_url"
              label="连接URL"
              rules={[{ required: true, message: '请输入连接URL' }]}
            >
              <Input.TextArea
                rows={3}
                placeholder={getUrlPlaceholder(selectedDbType)}
              />
            </Form.Item>
          ) : (
            renderBasicForm()
          )}
        </Form>
      </Modal>

      <DatabaseConnectModal
        open={connectModalVisible}
        onClose={() => setConnectModalVisible(false)}
        onSuccess={() => {
          message.success('数据库连接成功');
          fetchConnections();
        }}
      />
    </div>
  );
};

function getUrlPlaceholder(dbType: string): string {
  const placeholders: Record<string, string> = {
    mysql: 'mysql://user:password@localhost:3306/database',
    postgresql: 'postgresql://user:password@localhost:5432/database',
    sqlite: '/path/to/database.db',
    bigquery: 'project_id=my-project;credentials_file=/path/to/key.json;dataset=my_dataset',
    clickhouse: 'clickhouse://user:password@localhost:8123/database',
    duckdb: '/path/to/database.duckdb',
    mssql: 'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost,1433;DATABASE=mydb;UID=user;PWD=password',
    oracle: 'user=scott;password=tiger;dsn=localhost:1521/ORCL',
    presto: 'host=localhost;port=443;username=user;password=pass;catalog=hive;schema=default',
    snowflake: 'account=myaccount;user=myuser;password=mypass;database=mydb;warehouse=mywh;role=myrole',
  };
  return placeholders[dbType] || '请输入连接URL';
}

export default ConnectionsPage;
