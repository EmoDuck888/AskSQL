import React, { useEffect, useRef, useState, useCallback } from 'react';
import type { Data, FalkorDBCanvas, GraphNode } from '@falkordb/canvas';
import { Button, Spin, message } from 'antd';
import { ZoomInOutlined, ZoomOutOutlined, CompressOutlined } from '@ant-design/icons';
import { DatabaseService } from '../../services/database';

interface SchemaNode {
  id: number;
  userId: string;
  name: string;
  columns: Array<string | { name: string; type?: string; dataType?: string }>;
}

interface SchemaLink {
  source: number;
  target: number;
}

interface SchemaData {
  nodes: SchemaNode[];
  links: SchemaLink[];
  nodesMap: Map<number, SchemaNode>;
}

interface SchemaViewerProps {
  graphId: string | null;
}

const NODE_WIDTH = 160;

const SchemaViewer: React.FC<SchemaViewerProps> = ({ graphId }) => {
  const canvasRef = useRef<FalkorDBCanvas>(null);
  const [schemaData, setSchemaData] = useState<SchemaData | null>(null);
  const [loading, setLoading] = useState(false);
  const [canvasLoaded, setCanvasLoaded] = useState(false);

  // Load falkordb-canvas dynamically
  useEffect(() => {
    import('@falkordb/canvas')
      .then(() => setCanvasLoaded(true))
      .catch(() => message.error('Failed to load FalkorDB Canvas'));
  }, []);

  useEffect(() => {
    if (graphId) {
      loadSchemaData();
    }
  }, [graphId]);

  const loadSchemaData = async () => {
    if (!graphId) return;
    setLoading(true);
    try {
      const data = await DatabaseService.getGraphData(graphId);

      // Create a mapping from old IDs to new IDs
      const oldIdToNewId = new Map<string, number>();

      // Remap nodes with new sequential IDs
      data.nodes = data.nodes.map((node: any, index: number) => {
        const newId = index + 1;
        oldIdToNewId.set(String(node.id), newId);
        return {
          ...node,
          userId: String(node.id),
          id: newId,
        };
      });

      // Update links to use the new node IDs
      data.links = data.links.map((link: any) => ({
        ...link,
        source: oldIdToNewId.get(String(link.source)) || link.source,
        target: oldIdToNewId.get(String(link.target)) || link.target,
      }));

      const nodesMap = new Map<number, SchemaNode>(
        data.nodes.map((node: any) => [node.id, node])
      );

      setSchemaData({ nodes: data.nodes, links: data.links, nodesMap });
    } catch (error) {
      console.error('Failed to load schema:', error);
      message.error('Failed to load schema data');
      setSchemaData({ nodes: [], links: [], nodesMap: new Map() });
    } finally {
      setLoading(false);
    }
  };

  const handleZoomIn = () => {
    const canvas = canvasRef.current;
    if (canvas) canvas.zoom(canvas.getZoom() * 1.1);
  };

  const handleZoomOut = () => {
    const canvas = canvasRef.current;
    if (canvas) canvas.zoom(canvas.getZoom() * 0.9);
  };

  const handleCenter = useCallback(() => {
    const canvas = canvasRef.current;
    if (canvas) canvas.zoomToFit();
  }, []);

  // Convert schema data to canvas format
  const convertToCanvasData = useCallback((data: SchemaData): Data => {
    const nodes = data.nodes.map((node) => {
      const columns = node.columns || [];
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;
      const size = Math.max(NODE_WIDTH / 2, nodeHeight / 2);

      return {
        id: node.id,
        labels: ['Table'],
        color: '#3b82f6',
        visible: true,
        size,
        data: {
          name: node.name,
          columns: node.columns,
        },
      };
    });

    const links = data.links.map((link, index) => ({
      id: index + 1,
      relationship: 'REFERENCES',
      color: '#4b5563',
      visible: true,
      source: link.source,
      target: link.target,
      data: {},
    }));

    return { nodes, links };
  }, []);

  // Set up canvas configuration and data
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !canvasLoaded || !schemaData) return;

    const nodeCanvasObject = (node: GraphNode, ctx: CanvasRenderingContext2D) => {
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const fontSize = 12;

      const textColor = '#f5f5f5';
      const fillColor = '#191919';
      const strokeColor = '#374151';
      const columnTextColor = '#e5e7eb';
      const typeTextColor = '#9ca3af';

      const schemaNode = schemaData.nodesMap.get(node.id);
      if (!schemaNode) return;

      const columns = schemaNode.columns || [];
      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;

      ctx.fillStyle = fillColor;
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = 1;
      ctx.fillRect(
        (node.x || 0) - NODE_WIDTH / 2,
        (node.y || 0) - nodeHeight / 2,
        NODE_WIDTH,
        nodeHeight
      );
      ctx.strokeRect(
        (node.x || 0) - NODE_WIDTH / 2,
        (node.y || 0) - nodeHeight / 2,
        NODE_WIDTH,
        nodeHeight
      );

      ctx.fillStyle = textColor;
      ctx.font = `bold ${fontSize}px Arial`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(
        node.displayName?.[1] ?? schemaNode.name,
        node.x || 0,
        (node.y || 0) - nodeHeight / 2 + headerHeight / 2 + padding / 2
      );

      ctx.font = `${fontSize - 2}px Arial`;
      ctx.textAlign = 'left';
      const startX = (node.x || 0) - NODE_WIDTH / 2 + padding;
      let colY = (node.y || 0) - nodeHeight / 2 + headerHeight + padding;

      columns.forEach((col: any) => {
        let name = col;
        let type = null;
        if (typeof col === 'object') {
          name = col.name || '';
          type = col.type || col.dataType || null;
        }

        ctx.textAlign = 'left';
        ctx.fillStyle = columnTextColor;
        ctx.fillText(name, startX, colY);

        if (type) {
          ctx.fillStyle = typeTextColor;
          const nameWidth = ctx.measureText(name).width;
          const available = NODE_WIDTH - padding * 2 - nameWidth - 8;
          let typeText = String(type);
          if (available > 0) {
            if (ctx.measureText(typeText).width > available) {
              while (
                typeText.length > 0 &&
                ctx.measureText(typeText + '…').width > available
              ) {
                typeText = typeText.slice(0, -1);
              }
              typeText = typeText + '…';
            }
            ctx.textAlign = 'right';
            ctx.fillText(typeText, (node.x || 0) + NODE_WIDTH / 2 - padding, colY);
          }
          ctx.fillStyle = columnTextColor;
          ctx.textAlign = 'left';
        }

        colY += lineHeight;
      });
    };

    const nodePointerAreaPaint = (node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
      const schemaNode = schemaData.nodesMap.get(node.id);
      if (!schemaNode) return;

      const columns = schemaNode.columns || [];
      const lineHeight = 14;
      const padding = 8;
      const headerHeight = 20;
      const nodeHeight = headerHeight + columns.length * lineHeight + padding * 2;

      ctx.fillStyle = color;
      const areaPadding = 5;
      ctx.fillRect(
        (node.x || 0) - NODE_WIDTH / 2 - areaPadding,
        (node.y || 0) - nodeHeight / 2 - areaPadding,
        NODE_WIDTH + areaPadding * 2,
        nodeHeight + areaPadding * 2
      );
    };

    const canvasData = convertToCanvasData(schemaData);

    canvas.setConfig({
      autoStopOnSettle: false,
      node: {
        nodeCanvasObject,
        nodePointerAreaPaint,
      },
    });

    canvas.setBackgroundColor('#191919');
    canvas.setForegroundColor('#f5f5f5');
    canvas.setData(canvasData);
  }, [schemaData, canvasLoaded, convertToCanvasData]);

  if (!graphId) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#999' }}>
        <div style={{ textAlign: 'center' }}>
          <p>请选择数据库连接以查看 Schema</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #e8e8e8', display: 'flex', gap: 8 }}>
        <Button size="small" icon={<ZoomInOutlined />} onClick={handleZoomIn}>放大</Button>
        <Button size="small" icon={<ZoomOutOutlined />} onClick={handleZoomOut}>缩小</Button>
        <Button size="small" icon={<CompressOutlined />} onClick={handleCenter}>居中</Button>
      </div>
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#191919' }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10 }}>
            <Spin size="large" tip="Loading schema..." />
          </div>
        )}
        {canvasLoaded && schemaData && schemaData.nodes.length > 0 && (
          <falkordb-canvas ref={canvasRef} node-mode="replace" style={{ width: '100%', height: '100%' }} />
        )}
        {!loading && (!schemaData || schemaData.nodes.length === 0) && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>
            <div style={{ textAlign: 'center' }}>
              <p>没有 Schema 数据</p>
              <p style={{ fontSize: 12 }}>请先在连接管理中连接数据库</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default SchemaViewer;
