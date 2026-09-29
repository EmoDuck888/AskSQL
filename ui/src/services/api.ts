import axios from 'axios';
import { API_BASE_URL } from '../config';
export { API_BASE_URL };

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth tokens or other global handling
api.interceptors.request.use(
  (config) => config,
  (error) => Promise.reject(error)
);

// Response interceptor for global error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('API Error:', error.response?.status, error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// ─── Types ───────────────────────────────────────────────

export interface DBConnection {
  id?: number;
  name: string;
  db_type: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  description?: string;
}

export interface SchemaTable {
  id: number;
  name: string;
  description?: string;
  columns: SchemaColumn[];
}

export interface SchemaColumn {
  id: number;
  name: string;
  data_type: string;
  description?: string;
  is_primary_key?: boolean;
  is_foreign_key?: boolean;
}

export interface QueryRequest {
  query: string;
  connection_id?: number;
}

export interface UserRules {
  rules: string[];
}

export interface ApiKeyValidation {
  provider: string;
  api_key: string;
}

// ─── Database Connections ────────────────────────────────

export const getConnections = () => api.get<DBConnection[]>('/connections');
export const getConnection = (id: number) => api.get<DBConnection>(`/connections/${id}`);
export const createConnection = (data: DBConnection) => api.post<DBConnection>('/connections', data);
export const updateConnection = (id: number, data: Partial<DBConnection>) => api.put<DBConnection>(`/connections/${id}`, data);
export const deleteConnection = (id: number) => api.delete(`/connections/${id}`);
export const testConnection = (id: number) => api.post(`/connections/${id}/test`);
export const discoverAndSaveSchema = (id: number) => api.post(`/connections/${id}/discover-and-save`);

// ─── Schema Management ───────────────────────────────────

export const discoverSchema = (connectionId: number) => api.get(`/schema/${connectionId}/discover`);
export const getSchemaMetadata = (connectionId: number) => api.get(`/schema/${connectionId}/metadata`);
export const getSavedSchema = (connectionId: number) => api.get(`/schema/${connectionId}/saved`);
export const publishSchema = (connectionId: number, data: unknown) => api.post(`/schema/${connectionId}/publish`, data);
export const updateTable = (tableId: number, data: unknown) => api.put(`/schema/tables/${tableId}`, data);
export const updateColumn = (columnId: number, data: unknown) => api.put(`/schema/columns/${columnId}`, data);
export const syncToNeo4j = (connectionId: number) => api.post(`/schema/${connectionId}/sync-to-neo4j`);
export const discoverAndSyncSchema = (connectionId: number) => api.post(`/schema/${connectionId}/discover-and-sync`);

// ─── Intelligent Query ───────────────────────────────────

export const executeQuery = (data: QueryRequest) => api.post('/query', data);

// ─── Business Metrics ────────────────────────────────────

export interface BusinessMetric {
  id?: number;
  connection_id: number;
  name: string;
  formula: string;
  related_table?: string;
  filter_condition?: string;
  description?: string;
}

export const getBusinessMetrics = (connectionId: number) =>
  api.get<BusinessMetric[]>(`/connections/${connectionId}/business-metrics`);
export const createBusinessMetric = (connectionId: number, data: Omit<BusinessMetric, 'id' | 'connection_id'>) =>
  api.post<BusinessMetric>(`/connections/${connectionId}/business-metrics`, data);
export const updateBusinessMetric = (connectionId: number, metricId: number, data: Partial<Omit<BusinessMetric, 'id' | 'connection_id'>>) =>
  api.put<BusinessMetric>(`/connections/${connectionId}/business-metrics/${metricId}`, data);
export const deleteBusinessMetric = (connectionId: number, metricId: number) =>
  api.delete(`/connections/${connectionId}/business-metrics/${metricId}`);

// ─── Graph Visualization ─────────────────────────────────

export const getGraphVisualization = (connectionId: number) => api.get(`/graph-visualization/${connectionId}`);

// ─── Graphs & Databases (QueryWeaver integration) ─────────

export const getGraphs = () => api.get('/graphs');
export const getGraphData = (graphId: string) => api.get(`/graphs/${graphId}/data`);
export const getMemoryGraphData = (graphId: string) => api.get(`/graphs/${graphId}/memory`);
export const deleteGraph = (graphId: string) => api.delete(`/graphs/${graphId}`);
export const deleteMemoryNode = (graphId: string, nodeId: string) =>
  api.delete(`/graphs/${graphId}/memory-nodes/${nodeId}`);

export const getSchemaDetail = (graphId: string) => api.get(`/graphs/${graphId}/schema-detail`);

export interface NodeUpdateRequest {
  business_name?: string;
  synonyms?: string;
  enum_descriptions?: string;
  description?: string;
}

export const updateNode = (graphId: string, nodeType: string, nodeName: string, data: NodeUpdateRequest) =>
  api.put(`/graphs/${graphId}/nodes/${nodeType}/${nodeName}`, data);

// ─── User Rules ──────────────────────────────────────────

export const getUserRules = (graphId: string) => api.get<UserRules>(`/graphs/${graphId}/user-rules`);
export const setUserRules = (graphId: string, data: UserRules) => api.put(`/graphs/${graphId}/user-rules`, data);

// ─── Settings ────────────────────────────────────────────

export const validateApiKey = (data: ApiKeyValidation) => api.post('/settings/validate-api-key', data);

export default api;
