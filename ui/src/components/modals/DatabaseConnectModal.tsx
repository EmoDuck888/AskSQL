import React, { useState } from 'react';
import {
  Modal,
  Button,
  Input,
  Select,
  Form,
  Radio,
  Steps,
  Space,
  Alert,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
} from '@ant-design/icons';
import { DatabaseService } from '../../services/database';

const { Option } = Select;
const { Step } = Steps;

interface ConnectionStep {
  message: string;
  status: 'wait' | 'process' | 'finish' | 'error';
}

interface DatabaseConnectModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const DatabaseConnectModal: React.FC<DatabaseConnectModalProps> = ({
  open,
  onClose,
  onSuccess,
}) => {
  const [form] = Form.useForm();
  const [connectionMode, setConnectionMode] = useState<'url' | 'manual'>('manual');
  const [dbType, setDbType] = useState<string>('mysql');
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectionSteps, setConnectionSteps] = useState<ConnectionStep[]>([]);
  const [error, setError] = useState<string>('');

  const resetState = () => {
    setConnectionSteps([]);
    setError('');
    setIsConnecting(false);
    form.resetFields();
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleConnect = async () => {
    try {
      const values = await form.validateFields();
      setIsConnecting(true);
      setConnectionSteps([]);
      setError('');

      let dbUrl = '';
      if (connectionMode === 'url') {
        dbUrl = values.connectionUrl;
      } else {
        if (dbType === 'mysql') {
          dbUrl = `mysql://${values.username}:${values.password}@${values.host}:${values.port || 3306}/${values.database}`;
        } else if (dbType === 'postgresql') {
          dbUrl = `postgresql://${values.username}:${values.password}@${values.host}:${values.port || 5432}/${values.database}`;
        }
      }

      if (!dbUrl) {
        setError('请填写完整的连接信息');
        setIsConnecting(false);
        return;
      }

      const response = await DatabaseService.connectDatabase(dbUrl);
      if (!response.ok) {
        setError('连接请求失败');
        setIsConnecting(false);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        setError('无法读取流式响应');
        setIsConnecting(false);
        return;
      }

      const decoder = new TextDecoder();
      let buffer = '';
      let completed = false;

      while (!completed) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const delimiter = '|||FALKORDB_MESSAGE_BOUNDARY|||';
        const parts = buffer.split(delimiter);
        buffer = parts.pop() || '';

        for (const part of parts) {
          if (!part.trim()) continue;
          try {
            const obj = JSON.parse(part);
            if (obj.type === 'reasoning_step') {
              setConnectionSteps((prev) => {
                const updated = prev.map((s) =>
                  s.status === 'process' ? { ...s, status: 'finish' as const } : s
                );
                return [...updated, { message: obj.message, status: 'process' }];
              });
            } else if (obj.type === 'final_result') {
              setConnectionSteps((prev) => {
                const updated = prev.map((s) =>
                  s.status === 'process' ? { ...s, status: 'finish' as const } : s
                );
                if (obj.success) {
                  return [...updated, { message: obj.message, status: 'finish' }];
                } else {
                  return [...updated, { message: obj.message, status: 'error' }];
                }
              });
              completed = true;
              if (obj.success) {
                setTimeout(() => {
                  onSuccess();
                  handleClose();
                }, 1000);
              }
            } else if (obj.type === 'error') {
              setConnectionSteps((prev) => [
                ...prev.map((s) =>
                  s.status === 'process' ? { ...s, status: 'error' as const } : s
                ),
                { message: obj.message, status: 'error' },
              ]);
              completed = true;
            }
          } catch {
            // Skip invalid JSON
          }
        }
      }

      setIsConnecting(false);
    } catch {
      // Form validation failed
    }
  };

  const getStepIcon = (status: string) => {
    if (status === 'process') return <LoadingOutlined />;
    if (status === 'finish') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    if (status === 'error') return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    return undefined;
  };

  return (
    <Modal
      title="连接数据库"
      open={open}
      onCancel={handleClose}
      width={600}
      footer={[
        <Button key="cancel" onClick={handleClose} disabled={isConnecting}>
          取消
        </Button>,
        <Button
          key="connect"
          type="primary"
          onClick={handleConnect}
          loading={isConnecting}
        >
          {isConnecting ? '连接中...' : '连接'}
        </Button>,
      ]}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ dbType: 'mysql', host: 'localhost', port: 3306 }}
      >
        <Form.Item name="dbType" label="数据库类型">
          <Select onChange={setDbType} value={dbType}>
            <Option value="mysql">MySQL</Option>
            <Option value="postgresql">PostgreSQL</Option>
          </Select>
        </Form.Item>

        <Form.Item>
          <Radio.Group
            value={connectionMode}
            onChange={(e) => setConnectionMode(e.target.value)}
          >
            <Radio value="manual">手动输入</Radio>
            <Radio value="url">连接 URL</Radio>
          </Radio.Group>
        </Form.Item>

        {connectionMode === 'url' ? (
          <Form.Item
            name="connectionUrl"
            label="连接 URL"
            rules={[{ required: true, message: '请输入连接 URL' }]}
          >
            <Input
              placeholder={
                dbType === 'mysql'
                  ? 'mysql://username:password@host:3306/database'
                  : 'postgresql://username:password@host:5432/database'
              }
            />
          </Form.Item>
        ) : (
          <>
            <Form.Item
              name="host"
              label="主机"
              rules={[{ required: true, message: '请输入主机地址' }]}
            >
              <Input placeholder="localhost" />
            </Form.Item>
            <Form.Item
              name="port"
              label="端口"
              rules={[{ required: true, message: '请输入端口' }]}
            >
              <Input
                type="number"
                placeholder={dbType === 'mysql' ? '3306' : '5432'}
              />
            </Form.Item>
            <Form.Item
              name="database"
              label="数据库名"
              rules={[{ required: true, message: '请输入数据库名' }]}
            >
              <Input placeholder="my_database" />
            </Form.Item>
            <Form.Item
              name="username"
              label="用户名"
              rules={[{ required: true, message: '请输入用户名' }]}
            >
              <Input placeholder="root" />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[{ required: true, message: '请输入密码' }]}
            >
              <Input.Password placeholder="password" />
            </Form.Item>
          </>
        )}
      </Form>

      {error && (
        <Alert message={error} type="error" showIcon style={{ marginTop: 16 }} />
      )}

      {connectionSteps.length > 0 && (
        <div style={{ marginTop: 16, maxHeight: 300, overflow: 'auto' }}>
          <Steps direction="vertical" size="small">
            {connectionSteps.map((step, index) => (
              <Step
                key={index}
                title={step.message}
                status={step.status}
                icon={getStepIcon(step.status)}
              />
            ))}
          </Steps>
        </div>
      )}
    </Modal>
  );
};

export default DatabaseConnectModal;
