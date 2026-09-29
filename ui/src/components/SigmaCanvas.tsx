import React, { useState, useCallback, useEffect } from 'react';
import { Modal } from 'antd';
import { useSigma } from '../hooks/useSigma';
import type Graph from 'graphology';
import type { SigmaNodeAttributes, SigmaEdgeAttributes } from '../lib/graph-adapter';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  Focus,
  RotateCcw,
  Play,
  Pause,
  Trash2,
} from 'lucide-react';

interface SigmaCanvasProps {
  graph: Graph<SigmaNodeAttributes, SigmaEdgeAttributes> | null;
  onNodeClick?: (nodeId: string, data: any) => void;
  selectedNodeId?: string | null;
  activeTab?: 'schema' | 'memory';
  onDeleteNode?: (nodeId: string) => void;
}

const SigmaCanvas: React.FC<SigmaCanvasProps> = ({
  graph,
  onNodeClick,
  selectedNodeId,
  activeTab,
  onDeleteNode,
}) => {
  const [hoveredName, setHoveredName] = useState<string | null>(null);

  const {
    containerRef,
    setGraph: setSigmaGraph,
    zoomIn,
    zoomOut,
    resetZoom,
    focusNode,
    isLayoutRunning,
    startLayout,
    stopLayout,
    selectedNode,
    setSelectedNode,
  } = useSigma({
    onNodeClick: (nodeId) => {
      if (graph?.hasNode(nodeId)) {
        const data = graph.getNodeAttributes(nodeId);
        onNodeClick?.(nodeId, data);
      }
    },
    onNodeHover: (nodeId) => {
      if (nodeId && graph?.hasNode(nodeId)) {
        setHoveredName(graph.getNodeAttributes(nodeId).label);
      } else {
        setHoveredName(null);
      }
    },
    onStageClick: () => {
      onNodeClick?.('', null);
    },
  });

  // Sync external selectedNodeId
  useEffect(() => {
    if (selectedNodeId) {
      focusNode(selectedNodeId);
    } else {
      setSelectedNode(null);
    }
  }, [selectedNodeId, focusNode, setSelectedNode]);

  // Update Sigma graph when data changes
  useEffect(() => {
    if (graph) {
      setSigmaGraph(graph);
    }
  }, [graph, setSigmaGraph]);

  const handleFocusSelected = useCallback(() => {
    if (selectedNode) {
      focusNode(selectedNode);
    }
  }, [selectedNode, focusNode]);

  const handleClearSelection = useCallback(() => {
    setSelectedNode(null);
    onNodeClick?.('', null);
    resetZoom();
  }, [setSelectedNode, onNodeClick, resetZoom]);

  const handleDeleteClick = useCallback(() => {
    if (activeTab === 'memory' && selectedNode && onDeleteNode) {
      const label = graph?.getNodeAttributes(selectedNode).label || selectedNode;
      Modal.confirm({
        title: '确认删除节点',
        content: `确定要从记忆图谱中删除节点 "${label}" 吗？此操作不可恢复。`,
        okText: '删除',
        okType: 'danger',
        cancelText: '取消',
        onOk() {
          onDeleteNode(selectedNode);
        },
      });
    } else {
      handleClearSelection();
    }
  }, [activeTab, selectedNode, onDeleteNode, handleClearSelection, graph]);

  return (
    <div className="relative h-full w-full" style={{ background: '#0f0f1a' }}>
      {/* 背景径向渐变 */}
      <div className="pointer-events-none absolute inset-0">
        <div
          className="absolute inset-0"
          style={{
            background: `
              radial-gradient(circle at 50% 50%, rgba(124, 58, 237, 0.03) 0%, transparent 70%),
              linear-gradient(to bottom, #0f0f1a, #0a0a14)
            `,
          }}
        />
      </div>

      {/* Sigma 容器 */}
      <div
        ref={containerRef}
        className="h-full w-full"
        style={{ cursor: 'grab' }}
      />

      {/* 悬停提示 —— 仅未选中时显示 */}
      {hoveredName && !selectedNode && (
        <div
          className="pointer-events-none absolute top-4 left-1/2 z-20 -translate-x-1/2"
          style={{
            padding: '6px 12px',
            borderRadius: 8,
            background: 'rgba(30, 30, 46, 0.95)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <span style={{ fontFamily: 'monospace', fontSize: 13, color: '#e0e0e0' }}>
            {hoveredName}
          </span>
        </div>
      )}

      {/* 选中信息栏 */}
      {selectedNode && graph?.hasNode(selectedNode) && (
        <div
          className="absolute top-4 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2"
          style={{
            padding: '8px 16px',
            borderRadius: 12,
            background: 'rgba(99, 102, 241, 0.15)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <div
            className="h-2 w-2 animate-pulse rounded-full"
            style={{ background: '#818cf8' }}
          />
          <span style={{ fontFamily: 'monospace', fontSize: 13, color: '#e0e0e0' }}>
            {graph.getNodeAttributes(selectedNode).label}
          </span>
          <span style={{ fontSize: 11, color: '#888' }}>
            ({graph.getNodeAttributes(selectedNode).nodeType})
          </span>
          <button
            onClick={handleDeleteClick}
            style={{
              marginLeft: 8,
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              color: activeTab === 'memory' ? '#ff4d4f' : '#aaa',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (activeTab === 'memory') {
                (e.target as HTMLElement).style.color = '#ff7875';
                (e.target as HTMLElement).style.background = 'rgba(255,77,79,0.1)';
              } else {
                (e.target as HTMLElement).style.color = '#fff';
                (e.target as HTMLElement).style.background = 'rgba(255,255,255,0.1)';
              }
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLElement).style.color = activeTab === 'memory' ? '#ff4d4f' : '#aaa';
              (e.target as HTMLElement).style.background = 'transparent';
            }}
          >
            {activeTab === 'memory' ? '删除节点' : '清除'}
          </button>
        </div>
      )}

      {/* 控制面板 —— 右下 */}
      <div className="absolute right-4 bottom-4 z-10 flex flex-col gap-1">
        <ControlButton onClick={zoomIn} title="放大">
          <ZoomIn className="h-4 w-4" />
        </ControlButton>
        <ControlButton onClick={zoomOut} title="缩小">
          <ZoomOut className="h-4 w-4" />
        </ControlButton>
        <ControlButton onClick={resetZoom} title="适应屏幕">
          <Maximize2 className="h-4 w-4" />
        </ControlButton>

        <div style={{ width: '100%', height: 1, background: 'rgba(255,255,255,0.08)', margin: '4px 0' }} />

        {selectedNode && (
          <ControlButton
            onClick={handleFocusSelected}
            title="聚焦选中节点"
            active
          >
            <Focus className="h-4 w-4" />
          </ControlButton>
        )}

        {selectedNode && (
          <ControlButton onClick={handleClearSelection} title="清除选择">
            <RotateCcw className="h-4 w-4" />
          </ControlButton>
        )}

        <div style={{ width: '100%', height: 1, background: 'rgba(255,255,255,0.08)', margin: '4px 0' }} />

        <ControlButton
          onClick={isLayoutRunning ? stopLayout : startLayout}
          title={isLayoutRunning ? '停止布局' : '重新布局'}
          active={isLayoutRunning}
          pulsing={isLayoutRunning}
        >
          {isLayoutRunning ? (
            <Pause className="h-4 w-4" />
          ) : (
            <Play className="h-4 w-4" />
          )}
        </ControlButton>
      </div>

      {/* 布局运行指示器 */}
      {isLayoutRunning && (
        <div
          className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2"
          style={{
            padding: '6px 14px',
            borderRadius: 20,
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            backdropFilter: 'blur(8px)',
          }}
        >
          <div className="h-2 w-2 animate-ping rounded-full" style={{ background: '#34d399' }} />
          <span style={{ fontSize: 12, fontWeight: 500, color: '#34d399' }}>
            力导向布局优化中...
          </span>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// 控制按钮子组件
// ---------------------------------------------------------------------------

const ControlButton: React.FC<{
  onClick: () => void;
  title: string;
  children: React.ReactNode;
  active?: boolean;
  pulsing?: boolean;
}> = ({ onClick, title, children, active, pulsing }) => {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        width: 36,
        height: 36,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: 8,
        border: active
          ? '1px solid rgba(99, 102, 241, 0.5)'
          : '1px solid rgba(255, 255, 255, 0.08)',
        background: active
          ? 'rgba(99, 102, 241, 0.2)'
          : 'rgba(30, 30, 46, 0.8)',
        color: active ? '#a5b4fc' : '#9ca3af',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        animation: pulsing ? 'pulse-glow 2s ease-in-out infinite' : 'none',
      }}
      onMouseEnter={(e) => {
        const t = e.currentTarget;
        if (!active) {
          t.style.background = 'rgba(50, 50, 70, 0.9)';
          t.style.color = '#e0e0e0';
        }
      }}
      onMouseLeave={(e) => {
        const t = e.currentTarget;
        if (!active) {
          t.style.background = 'rgba(30, 30, 46, 0.8)';
          t.style.color = '#9ca3af';
        }
      }}
    >
      {children}
    </button>
  );
};

export default SigmaCanvas;
