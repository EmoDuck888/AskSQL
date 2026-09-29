// 真实数据库结构模拟器 - 生成类似真实数据库的图谱数据

export interface MockNode {
  id: string;
  label: string;
  type: string;
  data: {
    label: string;
    nodeType: string;
    tableName?: string;
    columnName?: string;
    dataType?: string;
    isPrimaryKey?: boolean;
    isForeignKey?: boolean;
    isNullable?: boolean;
    [key: string]: any;
  };
}

export interface MockEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  label?: string;
  relationshipType?: string;
}

export interface MockGraphData {
  nodes: MockNode[];
  edges: MockEdge[];
}

// 真实的电商数据库表结构
const realDatabaseTables = [
  {
    name: 'users',
    description: '用户表',
    columns: [
      { name: 'id', type: 'BIGINT', isPrimaryKey: true, isNullable: false },
      { name: 'username', type: 'VARCHAR(50)', isPrimaryKey: false, isNullable: false },
      { name: 'email', type: 'VARCHAR(100)', isPrimaryKey: false, isNullable: false },
      { name: 'password_hash', type: 'VARCHAR(255)', isPrimaryKey: false, isNullable: false },
      { name: 'created_at', type: 'TIMESTAMP', isPrimaryKey: false, isNullable: false },
      { name: 'updated_at', type: 'TIMESTAMP', isPrimaryKey: false, isNullable: true }
    ]
  },
  {
    name: 'products',
    description: '商品表',
    columns: [
      { name: 'id', type: 'BIGINT', isPrimaryKey: true, isNullable: false },
      { name: 'name', type: 'VARCHAR(200)', isPrimaryKey: false, isNullable: false },
      { name: 'description', type: 'TEXT', isPrimaryKey: false, isNullable: true },
      { name: 'price', type: 'DECIMAL(10,2)', isPrimaryKey: false, isNullable: false },
      { name: 'category_id', type: 'BIGINT', isPrimaryKey: false, isNullable: false, isForeignKey: true },
      { name: 'stock_quantity', type: 'INT', isPrimaryKey: false, isNullable: false },
      { name: 'created_at', type: 'TIMESTAMP', isPrimaryKey: false, isNullable: false }
    ]
  },
  {
    name: 'categories',
    description: '商品分类表',
    columns: [
      { name: 'id', type: 'BIGINT', isPrimaryKey: true, isNullable: false },
      { name: 'name', type: 'VARCHAR(100)', isPrimaryKey: false, isNullable: false },
      { name: 'parent_id', type: 'BIGINT', isPrimaryKey: false, isNullable: true, isForeignKey: true },
      { name: 'description', type: 'TEXT', isPrimaryKey: false, isNullable: true }
    ]
  },
  {
    name: 'orders',
    description: '订单表',
    columns: [
      { name: 'id', type: 'BIGINT', isPrimaryKey: true, isNullable: false },
      { name: 'user_id', type: 'BIGINT', isPrimaryKey: false, isNullable: false, isForeignKey: true },
      { name: 'total_amount', type: 'DECIMAL(10,2)', isPrimaryKey: false, isNullable: false },
      { name: 'status', type: 'VARCHAR(20)', isPrimaryKey: false, isNullable: false },
      { name: 'created_at', type: 'TIMESTAMP', isPrimaryKey: false, isNullable: false },
      { name: 'shipped_at', type: 'TIMESTAMP', isPrimaryKey: false, isNullable: true }
    ]
  },
  {
    name: 'order_items',
    description: '订单商品表',
    columns: [
      { name: 'id', type: 'BIGINT', isPrimaryKey: true, isNullable: false },
      { name: 'order_id', type: 'BIGINT', isPrimaryKey: false, isNullable: false, isForeignKey: true },
      { name: 'product_id', type: 'BIGINT', isPrimaryKey: false, isNullable: false, isForeignKey: true },
      { name: 'quantity', type: 'INT', isPrimaryKey: false, isNullable: false },
      { name: 'unit_price', type: 'DECIMAL(10,2)', isPrimaryKey: false, isNullable: false }
    ]
  }
];

// 生成真实的表节点
export const generateTableNodes = (tableNames?: string[]): MockNode[] => {
  const tablesToUse = tableNames ?
    realDatabaseTables.filter(t => tableNames.includes(t.name)) :
    realDatabaseTables;

  return tablesToUse.map(table => ({
    id: `table-${table.name}`,
    label: table.name,
    type: 'table',
    data: {
      label: table.name,
      nodeType: 'table',
      tableName: table.name,
      description: table.description,
      columnCount: table.columns.length
    }
  }));
};

// 生成真实的列节点
export const generateColumnNodes = (tableNames?: string[]): MockNode[] => {
  const tablesToUse = tableNames ?
    realDatabaseTables.filter(t => tableNames.includes(t.name)) :
    realDatabaseTables;

  const nodes: MockNode[] = [];

  tablesToUse.forEach(table => {
    table.columns.forEach((column, index) => {
      nodes.push({
        id: `column-${table.name}-${column.name}`,
        label: column.name,
        type: 'column',
        data: {
          label: column.name,
          nodeType: 'column',
          tableName: table.name,
          columnName: column.name,
          dataType: column.type,
          isPrimaryKey: column.isPrimaryKey || false,
          isForeignKey: column.isForeignKey || false,
          isNullable: column.isNullable
        }
      });
    });
  });

  return nodes;
};

// 生成模拟的关系节点
export const generateRelationNodes = (count: number): MockNode[] => {
  const relationTypes = [
    'one-to-many', 'many-to-one', 'one-to-one', 'many-to-many'
  ];
  
  return Array.from({ length: count }, (_, index) => ({
    id: `relation-${index}`,
    label: relationTypes[index % relationTypes.length],
    type: 'relation',
    data: {
      label: relationTypes[index % relationTypes.length],
      nodeType: 'relation',
      description: `${relationTypes[index % relationTypes.length]} relationship`
    }
  }));
};

// 生成模拟的边
export const generateMockEdges = (nodes: MockNode[]): MockEdge[] => {
  const edges: MockEdge[] = [];
  const edgeTypes = ['animated', 'pulse', 'rainbow', 'electric', 'enhanced'];
  
  // 表之间的关系
  const tableNodes = nodes.filter(n => n.type === 'table');
  for (let i = 0; i < tableNodes.length - 1; i++) {
    edges.push({
      id: `edge-table-${i}`,
      source: tableNodes[i].id,
      target: tableNodes[i + 1].id,
      type: edgeTypes[i % edgeTypes.length],
      label: 'references'
    });
  }
  
  // 表到列的关系
  const columnNodes = nodes.filter(n => n.type === 'column');
  columnNodes.forEach((column, index) => {
    const tableId = column.data.tableId;
    if (tableId) {
      edges.push({
        id: `edge-table-column-${index}`,
        source: tableId,
        target: column.id,
        type: edgeTypes[index % edgeTypes.length],
        label: 'contains'
      });
    }
  });
  
  // 关系节点的连接
  const relationNodes = nodes.filter(n => n.type === 'relation');
  relationNodes.forEach((relation, index) => {
    if (tableNodes.length > index * 2 + 1) {
      edges.push({
        id: `edge-relation-${index}-1`,
        source: tableNodes[index * 2].id,
        target: relation.id,
        type: edgeTypes[index % edgeTypes.length]
      });
      edges.push({
        id: `edge-relation-${index}-2`,
        source: relation.id,
        target: tableNodes[index * 2 + 1].id,
        type: edgeTypes[(index + 1) % edgeTypes.length]
      });
    }
  });
  
  return edges;
};

// 生成完整的模拟图数据
export const generateMockGraphData = (
  complexity: 'simple' | 'standard' | 'complex' = 'standard',
  includeColumns: boolean = true,
  includeRelations: boolean = true
): MockGraphData => {
  const nodes: MockNode[] = [];

  // 根据复杂度选择表
  let tableNames: string[];
  switch (complexity) {
    case 'simple':
      tableNames = ['users', 'orders'];
      break;
    case 'complex':
      tableNames = realDatabaseTables.map(t => t.name);
      break;
    case 'standard':
    default:
      tableNames = ['users', 'products', 'categories', 'orders'];
      break;
  }

  // 添加表节点
  nodes.push(...generateTableNodes(tableNames));

  // 添加列节点
  if (includeColumns) {
    nodes.push(...generateColumnNodes(tableNames));
  }

  // 添加关系节点
  if (includeRelations) {
    const relationCount = Math.max(1, Math.floor(tableNames.length / 2));
    nodes.push(...generateRelationNodes(relationCount));
  }

  // 生成边
  const edges = generateMockEdges(nodes);

  return { nodes, edges };
};

// 预定义的示例数据集
export const sampleGraphData: MockGraphData = generateMockGraphData('standard', true, true);

// 简单的图数据（用于快速测试）
export const simpleGraphData: MockGraphData = {
  nodes: [
    {
      id: 'table-1',
      label: 'Users',
      type: 'table',
      data: { label: 'Users', nodeType: 'table' }
    },
    {
      id: 'table-2',
      label: 'Orders',
      type: 'table',
      data: { label: 'Orders', nodeType: 'table' }
    },
    {
      id: 'column-1',
      label: 'user_id',
      type: 'column',
      data: { label: 'user_id', nodeType: 'column' }
    },
    {
      id: 'column-2',
      label: 'order_id',
      type: 'column',
      data: { label: 'order_id', nodeType: 'column' }
    },
    {
      id: 'relation-1',
      label: 'one-to-many',
      type: 'relation',
      data: { label: 'one-to-many', nodeType: 'relation' }
    }
  ],
  edges: [
    {
      id: 'edge-1',
      source: 'table-1',
      target: 'column-1',
      type: 'animated',
      label: 'contains'
    },
    {
      id: 'edge-2',
      source: 'table-2',
      target: 'column-2',
      type: 'pulse',
      label: 'contains'
    },
    {
      id: 'edge-3',
      source: 'table-1',
      target: 'relation-1',
      type: 'rainbow'
    },
    {
      id: 'edge-4',
      source: 'relation-1',
      target: 'table-2',
      type: 'electric'
    }
  ]
};

// 复杂的图数据（用于性能测试）
export const complexGraphData: MockGraphData = generateMockGraphData('complex', true, true);
