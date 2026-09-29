import api, { API_BASE_URL } from './api';

export interface SchemaNode {
  id: string;
  name: string;
  columns: Array<{
    name: string;
    type: string;
    keyType?: string;
    nullable?: string;
  }>;
}

export interface SchemaLink {
  source: number;
  target: number;
}

export interface SchemaData {
  nodes: SchemaNode[];
  links: SchemaLink[];
}

export interface Graph {
  id: string;
  name: string;
}

const API_CONFIG = {
  STREAM_BOUNDARY: '|||FALKORDB_MESSAGE_BOUNDARY|||',
};

export class DatabaseService {
  static async getGraphs(): Promise<string[]> {
    const response = await api.get('/graphs');
    return response.data;
  }

  static async getGraphData(graphId: string): Promise<SchemaData> {
    const response = await api.get(`/graphs/${graphId}/data`);
    return response.data;
  }

  static async connectDatabase(url: string, connectionId?: number): Promise<Response> {
    return fetch(`${API_BASE_URL}/database`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ url, connection_id: connectionId }),
    });
  }

  static async deleteGraph(graphId: string): Promise<void> {
    await api.delete(`/graphs/${graphId}`);
  }

  static parseStreamChunks(
    text: string,
    buffer: string,
    onStep: (message: string, status: 'pending' | 'success' | 'error') => void,
    onComplete: (success: boolean, message: string) => void,
  ): string {
    const delimiter = API_CONFIG.STREAM_BOUNDARY;
    const parts = (buffer + text).split(delimiter);
    const remaining = parts.pop() || '';

    for (const part of parts) {
      if (!part.trim()) continue;
      try {
        const obj = JSON.parse(part);
        if (obj.type === 'reasoning_step') {
          onStep(obj.message || 'Working...', 'pending');
        } else if (obj.type === 'final_result') {
          onStep(obj.message || 'Completed', obj.success ? 'success' : 'error');
          onComplete(obj.success, obj.message || '');
        } else if (obj.type === 'error') {
          onStep(obj.message || 'Error', 'error');
          onComplete(false, obj.message || 'Unknown error');
        }
      } catch {
        // Skip invalid JSON
      }
    }

    return remaining;
  }
}
