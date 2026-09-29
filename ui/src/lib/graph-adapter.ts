import Graph from 'graphology';

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

export interface SigmaNodeAttributes {
  x: number;
  y: number;
  size: number;
  color: string;
  label: string;
  nodeType: string;
  hidden?: boolean;
  zIndex?: number;
  highlighted?: boolean;
  mass?: number;
  properties?: Record<string, any>;
}

export interface SigmaEdgeAttributes {
  size: number;
  color: string;
  relationType: string;
  type?: string;
  curvature?: number;
  zIndex?: number;
}

// ---------------------------------------------------------------------------
// 颜色与尺寸配置
// ---------------------------------------------------------------------------

const NODE_COLORS: Record<string, string> = {
  // Schema
  table: '#3b82f6',
  column: '#10b981',
  // Memory
  entity: '#a855f7',
  query: '#f59e0b',
  episode: '#06b6d4',
  fact: '#ef4444',
  // Fallback
  unknown: '#8c8c8c',
};

const NODE_SIZES: Record<string, number> = {
  table: 14,
  entity: 14,
  column: 6,
  query: 10,
  episode: 8,
  fact: 7,
  unknown: 8,
};

/**
 * 边样式 —— 每种关系类型使用不同颜色，便于区分
 */
const EDGE_STYLES: Record<string, { color: string; sizeMultiplier: number }> = {
  // Schema 层级
  HAS_COLUMN:    { color: '#2d5a3d', sizeMultiplier: 0.4 },
  REFERENCES:    { color: '#1d4ed8', sizeMultiplier: 0.8 },

  // Memory 层级
  HAS_DATABASE:  { color: '#7c3aed', sizeMultiplier: 0.5 },
  HAS_EPISODE:   { color: '#06b6d4', sizeMultiplier: 0.5 },
  HAS_QUERY:     { color: '#f59e0b', sizeMultiplier: 0.5 },
  MEMBER_OF:     { color: '#818cf8', sizeMultiplier: 0.4 },
  CONTAINS:      { color: '#2d5a3d', sizeMultiplier: 0.4 },
  DEFINES:       { color: '#0e7490', sizeMultiplier: 0.5 },

  // Memory 关联
  SUCCESS:       { color: '#22c55e', sizeMultiplier: 0.6 },
  FAILED:        { color: '#ef4444', sizeMultiplier: 0.6 },
  MENTIONS:      { color: '#64748b', sizeMultiplier: 0.5 },
  NEXT_EPISODE:  { color: '#94a3b8', sizeMultiplier: 0.5 },

  // 代码关系（兼容）
  IMPORTS:       { color: '#1d4ed8', sizeMultiplier: 0.6 },
  CALLS:         { color: '#7c3aed', sizeMultiplier: 0.8 },
  EXTENDS:       { color: '#c2410c', sizeMultiplier: 1.0 },
  IMPLEMENTS:    { color: '#be185d', sizeMultiplier: 0.9 },
};

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

const hexToRgb = (hex: string): { r: number; g: number; b: number } => {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : { r: 100, g: 100, b: 100 };
};

const rgbToHex = (r: number, g: number, b: number): string => {
  return (
    '#' +
    [r, g, b]
      .map((x) => {
        const hex = Math.max(0, Math.min(255, Math.round(x))).toString(16);
        return hex.length === 1 ? '0' + hex : hex;
      })
      .join('')
  );
};

/** 将颜色按暗色背景淡化 */
export const dimColor = (hex: string, amount: number): string => {
  const rgb = hexToRgb(hex);
  const darkBg = { r: 15, g: 15, b: 26 };
  return rgbToHex(
    darkBg.r + (rgb.r - darkBg.r) * amount,
    darkBg.g + (rgb.g - darkBg.g) * amount,
    darkBg.b + (rgb.b - darkBg.b) * amount,
  );
};

/** 提亮颜色 */
export const brightenColor = (hex: string, factor: number): string => {
  const rgb = hexToRgb(hex);
  return rgbToHex(
    rgb.r + ((255 - rgb.r) * (factor - 1)) / factor,
    rgb.g + ((255 - rgb.g) * (factor - 1)) / factor,
    rgb.b + ((255 - rgb.b) * (factor - 1)) / factor,
  );
};

const getScaledNodeSize = (baseSize: number, nodeCount: number): number => {
  if (nodeCount > 50000) return Math.max(1, baseSize * 0.4);
  if (nodeCount > 20000) return Math.max(1.5, baseSize * 0.5);
  if (nodeCount > 5000) return Math.max(2, baseSize * 0.65);
  if (nodeCount > 1000) return Math.max(2.5, baseSize * 0.8);
  return baseSize;
};

const getNodeMass = (nodeType: string, nodeCount: number): number => {
  const multiplier = nodeCount > 5000 ? 2 : nodeCount > 1000 ? 1.5 : 1;
  switch (nodeType) {
    case 'table':
    case 'entity':
      return 20 * multiplier;
    case 'query':
      return 10 * multiplier;
    case 'episode':
      return 6 * multiplier;
    case 'column':
    case 'fact':
      return 3 * multiplier;
    default:
      return 4 * multiplier;
  }
};

// ---------------------------------------------------------------------------
// 分层 BFS 布局核心 —— 借鉴 gitnexus
// ---------------------------------------------------------------------------

interface HierarchyEdge {
  source: string;
  target: string;
}

/**
 * 执行分层初始布局：
 * 1. 结构节点按黄金角分布在宽圆周上
 * 2. BFS 遍历层次边，子节点围绕父节点小范围抖动
 */
const buildHierarchicalGraph = (
  nodes: Array<{ id: string; name: string; type: string; properties?: Record<string, any> }>,
  edges: Array<{ source: string; target: string; type: string; properties?: Record<string, any> }>,
  structuralTypes: Set<string>,
  hierarchyEdgeTypes: Set<string>,
): Graph<SigmaNodeAttributes, SigmaEdgeAttributes> => {
  const graph = new Graph<SigmaNodeAttributes, SigmaEdgeAttributes>();
  const nodeCount = nodes.length;

  // 构建父子关系映射
  const parentToChildren = new Map<string, string[]>();
  const childToParent = new Map<string, string>();

  edges.forEach((edge) => {
    if (hierarchyEdgeTypes.has(edge.type)) {
      if (!parentToChildren.has(edge.source)) {
        parentToChildren.set(edge.source, []);
      }
      parentToChildren.get(edge.source)!.push(edge.target);
      childToParent.set(edge.target, edge.source);
    }
  });

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // 结构节点：宽展开
  const structuralNodes = nodes.filter((n) => structuralTypes.has(n.type));
  const structuralSpread = Math.sqrt(nodeCount) * 40;
  const childJitter = Math.sqrt(nodeCount) * 3;

  const nodePositions = new Map<string, { x: number; y: number }>();

  // 先放置结构节点（黄金角分布）
  structuralNodes.forEach((node, index) => {
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const angle = index * goldenAngle;
    const radius = structuralSpread * Math.sqrt((index + 1) / Math.max(structuralNodes.length, 1));
    const jitter = structuralSpread * 0.15;
    const x = radius * Math.cos(angle) + (Math.random() - 0.5) * jitter;
    const y = radius * Math.sin(angle) + (Math.random() - 0.5) * jitter;

    nodePositions.set(node.id, { x, y });

    const baseSize = NODE_SIZES[node.type] || NODE_SIZES.unknown;
    graph.addNode(node.id, {
      x,
      y,
      size: getScaledNodeSize(baseSize, nodeCount),
      color: NODE_COLORS[node.type] || NODE_COLORS.unknown,
      label: node.name,
      nodeType: node.type,
      mass: getNodeMass(node.type, nodeCount),
      properties: node.properties,
    });
  });

  // BFS 放置子节点
  const addNodeWithPosition = (nodeId: string) => {
    if (graph.hasNode(nodeId)) return;
    const node = nodeMap.get(nodeId);
    if (!node) return;

    const parentId = childToParent.get(nodeId);
    const parentPos = parentId ? nodePositions.get(parentId) : null;

    let x: number, y: number;
    if (parentPos) {
      x = parentPos.x + (Math.random() - 0.5) * childJitter;
      y = parentPos.y + (Math.random() - 0.5) * childJitter;
    } else {
      x = (Math.random() - 0.5) * structuralSpread * 0.5;
      y = (Math.random() - 0.5) * structuralSpread * 0.5;
    }

    nodePositions.set(nodeId, { x, y });

    const baseSize = NODE_SIZES[node.type] || NODE_SIZES.unknown;
    graph.addNode(nodeId, {
      x,
      y,
      size: getScaledNodeSize(baseSize, nodeCount),
      color: NODE_COLORS[node.type] || NODE_COLORS.unknown,
      label: node.name,
      nodeType: node.type,
      mass: getNodeMass(node.type, nodeCount),
      properties: node.properties,
    });
  };

  // BFS 从结构节点开始
  const queue: string[] = structuralNodes.map((n) => n.id);
  const visited = new Set<string>(queue);

  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const children = parentToChildren.get(currentId) || [];
    for (const childId of children) {
      if (!visited.has(childId)) {
        visited.add(childId);
        addNodeWithPosition(childId);
        queue.push(childId);
      }
    }
  }

  // 补充孤立节点
  nodes.forEach((node) => {
    if (!graph.hasNode(node.id)) {
      addNodeWithPosition(node.id);
    }
  });

  // 添加边
  const edgeBaseSize = nodeCount > 20000 ? 0.4 : nodeCount > 5000 ? 0.6 : 1.0;

  edges.forEach((edge) => {
    if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
      if (!graph.hasEdge(edge.source, edge.target)) {
        const style = EDGE_STYLES[edge.type] || { color: '#4a4a5a', sizeMultiplier: 0.5 };
        const curvature = 0.12 + Math.random() * 0.08;

        graph.addEdge(edge.source, edge.target, {
          size: edgeBaseSize * style.sizeMultiplier,
          color: style.color,
          relationType: edge.type,
          type: 'curved',
          curvature,
        });
      }
    }
  });

  return graph;
};

// ---------------------------------------------------------------------------
// Schema 数据转换
// ---------------------------------------------------------------------------

export interface SchemaGraphData {
  nodes: Array<{
    id: string;
    name: string;
    columns?: Array<{
      name: string;
      type: string;
      keyType?: string;
      nullable?: string;
    }>;
  }>;
  links?: Array<{
    source: string | number;
    target: string | number;
  }>;
}

export const schemaToGraphology = (data: SchemaGraphData): Graph<SigmaNodeAttributes, SigmaEdgeAttributes> => {
  const graph = new Graph<SigmaNodeAttributes, SigmaEdgeAttributes>();
  const nodeCount = (data.nodes?.length || 0) + (data.nodes?.reduce((sum, n) => sum + (n.columns?.length || 0), 0) || 0);

  // 表节点 -> 结构节点，宽展开
  const structuralSpread = Math.sqrt(nodeCount) * 40;
  const childJitter = Math.sqrt(nodeCount) * 3;
  const nodePositions = new Map<string, { x: number; y: number }>();

  data.nodes?.forEach((table, idx) => {
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const angle = idx * goldenAngle;
    const radius = structuralSpread * Math.sqrt((idx + 1) / Math.max(data.nodes!.length, 1));
    const jitter = structuralSpread * 0.15;
    const x = radius * Math.cos(angle) + (Math.random() - 0.5) * jitter;
    const y = radius * Math.sin(angle) + (Math.random() - 0.5) * jitter;

    nodePositions.set(`table-${table.id}`, { x, y });

    const baseSize = NODE_SIZES.table;
    graph.addNode(`table-${table.id}`, {
      x,
      y,
      size: getScaledNodeSize(baseSize, nodeCount),
      color: NODE_COLORS.table,
      label: table.name,
      nodeType: 'table',
      mass: getNodeMass('table', nodeCount),
      properties: { name: table.name, columnCount: table.columns?.length || 0 },
    });

    // 列节点围绕表节点小范围抖动
    table.columns?.forEach((col, cidx) => {
      const cx = x + (Math.random() - 0.5) * childJitter;
      const cy = y + (Math.random() - 0.5) * childJitter;

      const colId = `column-${table.id}-${cidx}`;
      nodePositions.set(colId, { x: cx, y: cy });

      graph.addNode(colId, {
        x: cx,
        y: cy,
        size: getScaledNodeSize(NODE_SIZES.column, nodeCount),
        color: NODE_COLORS.column,
        label: col.name,
        nodeType: 'column',
        mass: getNodeMass('column', nodeCount),
        properties: { ...col, tableName: table.name },
      });

      graph.addEdge(`table-${table.id}`, colId, {
        size: 1,
        color: EDGE_STYLES.HAS_COLUMN?.color || '#4a4a5a',
        relationType: 'HAS_COLUMN',
        type: 'curved',
        curvature: 0.1,
      });
    });
  });

  // 表间关系
  data.links?.forEach((link) => {
    const source = `table-${link.source}`;
    const target = `table-${link.target}`;
    if (graph.hasNode(source) && graph.hasNode(target)) {
      if (!graph.hasEdge(source, target)) {
        graph.addEdge(source, target, {
          size: 2,
          color: EDGE_STYLES.REFERENCES?.color || '#4a4a5a',
          relationType: 'REFERENCES',
          type: 'curved',
          curvature: 0.12 + Math.random() * 0.08,
        });
      }
    }
  });

  return graph;
};

// ---------------------------------------------------------------------------
// Memory 数据转换 —— 使用统一的分层 BFS 布局
// ---------------------------------------------------------------------------

export interface MemoryGraphData {
  nodes: Array<{
    id: string;
    name: string;
    type: string;
    labels: string[];
    properties: Record<string, any>;
  }>;
  edges: Array<{
    source: string;
    target: string;
    type: string;
    properties: Record<string, any>;
  }>;
}

const MEMORY_HIERARCHY_EDGES = new Set([
  'HAS_DATABASE',
  'HAS_EPISODE',
  'HAS_QUERY',
  'MEMBER_OF',
  'CONTAINS',
  'DEFINES',
]);

const MEMORY_STRUCTURAL_TYPES = new Set(['entity']);

export const memoryToGraphology = (data: MemoryGraphData): Graph<SigmaNodeAttributes, SigmaEdgeAttributes> => {
  const normalizedNodes = data.nodes?.map((n) => ({
    id: n.id,
    name: n.name,
    type: n.type || 'unknown',
    properties: { ...n.properties, labels: n.labels },
  })) || [];

  const normalizedEdges = data.edges?.map((e) => ({
    source: e.source,
    target: e.target,
    type: e.type,
    properties: e.properties,
  })) || [];

  return buildHierarchicalGraph(
    normalizedNodes,
    normalizedEdges,
    MEMORY_STRUCTURAL_TYPES,
    MEMORY_HIERARCHY_EDGES,
  );
};
