import { useRef, useEffect, useCallback, useState } from 'react';
import Sigma from 'sigma';
import Graph from 'graphology';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import noverlap from 'graphology-layout-noverlap';
import EdgeCurveProgram from '@sigma/edge-curve';
import NodeGlowProgram from '../lib/node-glow-program';
import type { SigmaNodeAttributes, SigmaEdgeAttributes } from '../lib/graph-adapter';

// ---------------------------------------------------------------------------
// 颜色工具函数
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
const dimColor = (hex: string, amount: number): string => {
  const rgb = hexToRgb(hex);
  const darkBg = { r: 15, g: 15, b: 26 }; // #0f0f1a
  return rgbToHex(
    darkBg.r + (rgb.r - darkBg.r) * amount,
    darkBg.g + (rgb.g - darkBg.g) * amount,
    darkBg.b + (rgb.b - darkBg.b) * amount,
  );
};

/** 提亮颜色 */
const brightenColor = (hex: string, factor: number): string => {
  const rgb = hexToRgb(hex);
  return rgbToHex(
    rgb.r + ((255 - rgb.r) * (factor - 1)) / factor,
    rgb.g + ((255 - rgb.g) * (factor - 1)) / factor,
    rgb.b + ((255 - rgb.b) * (factor - 1)) / factor,
  );
};

// ---------------------------------------------------------------------------
// ForceAtlas2 自适应参数（gitnexus 配置 —— 更低的 gravity，更高的 scalingRatio，
// 让结构节点充分展开，子节点围绕父节点聚集）
// ---------------------------------------------------------------------------

const getFA2Settings = (nodeCount: number) => {
  const isSmall = nodeCount < 500;
  const isMedium = nodeCount >= 500 && nodeCount < 2000;
  const isLarge = nodeCount >= 2000 && nodeCount < 10000;

  return {
    gravity: isSmall ? 0.8 : isMedium ? 0.5 : isLarge ? 0.3 : 0.15,
    scalingRatio: isSmall ? 15 : isMedium ? 30 : isLarge ? 60 : 100,
    slowDown: isSmall ? 1 : isMedium ? 2 : isLarge ? 3 : 5,
    barnesHutOptimize: nodeCount > 200,
    barnesHutTheta: isLarge ? 0.8 : 0.6,
    strongGravityMode: false,
    outboundAttractionDistribution: true,
    linLogMode: false,
    adjustSizes: true,
    edgeWeightInfluence: 1,
  };
};

const getLayoutDuration = (nodeCount: number): number => {
  if (nodeCount > 10000) return 45000;
  if (nodeCount > 5000) return 35000;
  if (nodeCount > 2000) return 30000;
  if (nodeCount > 1000) return 30000;
  if (nodeCount > 500) return 25000;
  return 20000;
};

const NOVERLAP_SETTINGS = {
  maxIterations: 20,
  ratio: 1.1,
  margin: 10,
  expansion: 1.05,
};

// ---------------------------------------------------------------------------
// Hook 接口
// ---------------------------------------------------------------------------

interface UseSigmaOptions {
  onNodeClick?: (nodeId: string) => void;
  onNodeHover?: (nodeId: string | null) => void;
  onStageClick?: () => void;
}

interface UseSigmaReturn {
  containerRef: React.RefObject<HTMLDivElement>;
  setGraph: (graph: Graph<SigmaNodeAttributes, SigmaEdgeAttributes>) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetZoom: () => void;
  focusNode: (nodeId: string) => void;
  isLayoutRunning: boolean;
  startLayout: () => void;
  stopLayout: () => void;
  selectedNode: string | null;
  setSelectedNode: (nodeId: string | null) => void;
}

export const useSigma = (options: UseSigmaOptions = {}): UseSigmaReturn => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph<SigmaNodeAttributes, SigmaEdgeAttributes> | null>(null);
  const layoutRef = useRef<FA2Layout | null>(null);
  const selectedNodeRef = useRef<string | null>(null);
  const layoutTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const draggedNodeRef = useRef<string | null>(null);
  const isDraggingRef = useRef(false);
  const dragInitialPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const [isLayoutRunning, setIsLayoutRunning] = useState(false);
  const [selectedNode, setSelectedNodeState] = useState<string | null>(null);

  const setSelectedNode = useCallback((nodeId: string | null) => {
    if (selectedNodeRef.current === nodeId) return;
    selectedNodeRef.current = nodeId;
    setSelectedNodeState(nodeId);
    sigmaRef.current?.refresh();
  }, []);

  // -----------------------------------------------------------------
  // Sigma 初始化（仅一次）
  // -----------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;

    const graph = new Graph<SigmaNodeAttributes, SigmaEdgeAttributes>();
    graphRef.current = graph;

    const sigma = new Sigma(graph, containerRef.current, {
      renderLabels: true,
      labelFont: "'Inter', 'Segoe UI', system-ui, sans-serif",
      labelSize: 11,
      labelWeight: '500',
      labelColor: { color: '#e0e0e0' },
      labelRenderedSizeThreshold: 8,
      labelDensity: 0.1,
      labelGridCellSize: 70,

      defaultNodeColor: '#9ca3af',
      defaultEdgeColor: '#3f3f46',

      defaultEdgeType: 'curved',
      edgeProgramClasses: {
        curved: EdgeCurveProgram,
      },

      // 发光节点 —— 用自定义光晕程序替换 Sigma 默认的 NodeCircleProgram
      nodeProgramClasses: {
        circle: NodeGlowProgram,
      },

      // 自定义 hover 渲染 —— 深色背景 pill + 发光环
      defaultDrawNodeHover: (context, data, settings) => {
        const label = data.label;
        if (!label) return;

        const size = settings.labelSize || 11;
        const font = settings.labelFont || "'Inter', sans-serif";
        const weight = settings.labelWeight || '500';
        context.font = `${weight} ${size}px ${font}`;
        const textWidth = context.measureText(label).width;

        const nodeSize = data.size || 8;
        const x = data.x;
        const y = data.y - nodeSize - 10;
        const paddingX = 8;
        const paddingY = 5;
        const height = size + paddingY * 2;
        const width = textWidth + paddingX * 2;
        const radius = 4;

        // 背景 pill
        context.fillStyle = '#1e1e2e';
        context.beginPath();
        (context as any).roundRect(x - width / 2, y - height / 2, width, height, radius);
        context.fill();

        // 边框
        context.strokeStyle = data.color || '#6366f1';
        context.lineWidth = 2;
        context.stroke();

        // 文字
        context.fillStyle = '#f5f5f7';
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(label, x, y);

        // 发光环
        context.beginPath();
        context.arc(data.x, data.y, nodeSize + 4, 0, Math.PI * 2);
        context.strokeStyle = data.color || '#6366f1';
        context.lineWidth = 2;
        context.globalAlpha = 0.5;
        context.stroke();
        context.globalAlpha = 1;
      },

      minCameraRatio: 0.002,
      maxCameraRatio: 50,
      hideEdgesOnMove: true,
      zIndex: true,

      // 节点渲染 reducer —— 选中高亮、邻居高亮、其他淡化
      nodeReducer: (node, data) => {
        const res = { ...data };
        if (data.hidden) {
          res.hidden = true;
          return res;
        }

        const currentSelected = selectedNodeRef.current;
        if (currentSelected) {
          const g = graphRef.current;
          if (g) {
            const isSelected = node === currentSelected;
            const isNeighbor =
              g.hasEdge(node, currentSelected) || g.hasEdge(currentSelected, node);

            if (isSelected) {
              res.color = data.color;
              res.size = (data.size || 8) * 1.8;
              res.zIndex = 2;
              res.highlighted = true;
            } else if (isNeighbor) {
              res.color = data.color;
              res.size = (data.size || 8) * 1.3;
              res.zIndex = 1;
            } else {
              res.color = dimColor(data.color, 0.25);
              res.size = (data.size || 8) * 0.6;
              res.zIndex = 0;
            }
          }
        }
        return res;
      },

      // 边渲染 reducer
      edgeReducer: (edge, data) => {
        const res = { ...data };
        const currentSelected = selectedNodeRef.current;
        if (currentSelected) {
          const g = graphRef.current;
          if (g) {
            const [source, target] = g.extremities(edge);
            const isConnected = source === currentSelected || target === currentSelected;

            if (isConnected) {
              res.color = brightenColor(data.color, 1.5);
              res.size = Math.max(3, (data.size || 1) * 4);
              res.zIndex = 2;
            } else {
              res.color = dimColor(data.color, 0.1);
              res.size = 0.3;
              res.zIndex = 0;
            }
          }
        }
        return res;
      },
    });

    sigmaRef.current = sigma;

    sigma.on('clickNode', ({ node }) => {
      if (isDraggingRef.current) return;
      setSelectedNode(node);
      options.onNodeClick?.(node);
    });

    sigma.on('clickStage', () => {
      setSelectedNode(null);
      options.onStageClick?.();
    });

    sigma.on('enterNode', ({ node }) => {
      options.onNodeHover?.(node);
      if (containerRef.current) containerRef.current.style.cursor = 'pointer';
    });

    sigma.on('leaveNode', () => {
      options.onNodeHover?.(null);
      if (containerRef.current) containerRef.current.style.cursor = 'grab';
    });

    // -----------------------------------------------------------------
    // 节点拖拽 —— 拖拽节点时邻居节点跟随移动（拉伸效果）
    // -----------------------------------------------------------------
    const handleWindowMouseMove = (e: MouseEvent) => {
      if (!draggedNodeRef.current || !sigmaRef.current || !graphRef.current) return;

      const graph = graphRef.current;
      const sigma = sigmaRef.current;
      const dragged = draggedNodeRef.current;

      // 标记为正在拖拽
      if (!isDraggingRef.current) {
        isDraggingRef.current = true;
      }

      // 使用 container bounding rect 精确计算相对坐标（支持鼠标移出容器）
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const offsetX = e.clientX - rect.left;
      const offsetY = e.clientY - rect.top;

      const pos = sigma.viewportToGraph({ x: offsetX, y: offsetY });

      const initial = dragInitialPositionsRef.current;
      if (!initial.has(dragged)) return;

      const dx = pos.x - initial.get(dragged)!.x;
      const dy = pos.y - initial.get(dragged)!.y;

      initial.forEach(({ x, y }, nodeId) => {
        graph.setNodeAttribute(nodeId, 'x', x + dx);
        graph.setNodeAttribute(nodeId, 'y', y + dy);
      });

      sigma.refresh();
    };

    const handleWindowMouseUp = () => {
      if (!draggedNodeRef.current) return;

      draggedNodeRef.current = null;
      dragInitialPositionsRef.current.clear();
      sigmaRef.current?.getCamera().enable();

      if (containerRef.current) {
        containerRef.current.style.cursor = 'grab';
      }

      // 延迟重置拖拽标志，避免 Sigma 的 clickNode 在 mouseup 后立即触发
      setTimeout(() => {
        isDraggingRef.current = false;
      }, 60);
    };

    sigma.on('downNode', (e) => {
      e.preventSigmaDefault();
      const graph = graphRef.current;
      if (!graph) return;

      // 彻底停止布局：kill Worker + 清除定时器，防止拖拽期间力导向拉扯节点
      if (layoutRef.current) {
        layoutRef.current.kill();
        layoutRef.current = null;
      }
      if (layoutTimeoutRef.current) {
        clearTimeout(layoutTimeoutRef.current);
        layoutTimeoutRef.current = null;
      }
      setIsLayoutRunning(false);

      // 关键：阻止 Sigma 的 MouseCaptor 进入画布拖拽模式。
      // MouseCaptor 在 emit downNode 前已将 isMouseDown 设为 true，
      // 会导致 handleMove 执行相机平移并 stopPropagation()，
      // 让我们的 window mousemove 永远收不到事件。
      const captor = (sigma as any).mouseCaptor;
      if (captor) {
        captor.isMouseDown = false;
      }

      draggedNodeRef.current = e.node;
      isDraggingRef.current = false;

      const positions = new Map<string, { x: number; y: number }>();
      const draggedPos = graph.getNodeAttributes(e.node);
      positions.set(e.node, { x: draggedPos.x, y: draggedPos.y });

      graph.forEachNeighbor(e.node, (neighbor) => {
        const attrs = graph.getNodeAttributes(neighbor);
        positions.set(neighbor, { x: attrs.x, y: attrs.y });
      });
      dragInitialPositionsRef.current = positions;

      sigma.getCamera().disable();
      if (containerRef.current) containerRef.current.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', handleWindowMouseMove);
    window.addEventListener('mouseup', handleWindowMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleWindowMouseMove);
      window.removeEventListener('mouseup', handleWindowMouseUp);
      if (layoutTimeoutRef.current) clearTimeout(layoutTimeoutRef.current);
      layoutRef.current?.kill();
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
  }, []);

  // -----------------------------------------------------------------
  // 布局
  // -----------------------------------------------------------------
  const runLayout = useCallback((graph: Graph<SigmaNodeAttributes, SigmaEdgeAttributes>) => {
    const nodeCount = graph.order;
    if (nodeCount === 0) return;

    if (layoutRef.current) {
      layoutRef.current.kill();
      layoutRef.current = null;
    }
    if (layoutTimeoutRef.current) {
      clearTimeout(layoutTimeoutRef.current);
      layoutTimeoutRef.current = null;
    }

    const inferred = forceAtlas2.inferSettings(graph);
    const custom = getFA2Settings(nodeCount);
    const settings = { ...inferred, ...custom };

    const layout = new FA2Layout(graph, { settings });
    layoutRef.current = layout;
    layout.start();
    setIsLayoutRunning(true);

    const duration = getLayoutDuration(nodeCount);
    layoutTimeoutRef.current = setTimeout(() => {
      if (layoutRef.current) {
        layoutRef.current.stop();
        layoutRef.current = null;
        noverlap.assign(graph, NOVERLAP_SETTINGS);
        sigmaRef.current?.refresh();
        setIsLayoutRunning(false);
      }
    }, duration);
  }, []);

  const setGraph = useCallback(
    (newGraph: Graph<SigmaNodeAttributes, SigmaEdgeAttributes>) => {
      const sigma = sigmaRef.current;
      if (!sigma) return;

      if (layoutRef.current) {
        layoutRef.current.kill();
        layoutRef.current = null;
      }
      if (layoutTimeoutRef.current) {
        clearTimeout(layoutTimeoutRef.current);
        layoutTimeoutRef.current = null;
      }

      graphRef.current = newGraph;
      sigma.setGraph(newGraph);

      selectedNodeRef.current = null;
      setSelectedNodeState(null);

      runLayout(newGraph);
      sigma.getCamera().animatedReset({ duration: 500 });
    },
    [runLayout],
  );

  const focusNode = useCallback((nodeId: string) => {
    const sigma = sigmaRef.current;
    const graph = graphRef.current;
    if (!sigma || !graph || !graph.hasNode(nodeId)) return;

    const alreadySelected = selectedNodeRef.current === nodeId;

    selectedNodeRef.current = nodeId;
    setSelectedNodeState(nodeId);

    if (!alreadySelected) {
      const attrs = graph.getNodeAttributes(nodeId);
      sigma.getCamera().animate({ x: attrs.x, y: attrs.y, ratio: 0.15 }, { duration: 400 });
    }

    sigma.refresh();
  }, []);

  const zoomIn = useCallback(() => {
    sigmaRef.current?.getCamera().animatedZoom({ duration: 200 });
  }, []);

  const zoomOut = useCallback(() => {
    sigmaRef.current?.getCamera().animatedUnzoom({ duration: 200 });
  }, []);

  const resetZoom = useCallback(() => {
    sigmaRef.current?.getCamera().animatedReset({ duration: 300 });
    setSelectedNode(null);
  }, [setSelectedNode]);

  const startLayout = useCallback(() => {
    const graph = graphRef.current;
    if (!graph || graph.order === 0) return;
    runLayout(graph);
  }, [runLayout]);

  const stopLayout = useCallback(() => {
    if (layoutTimeoutRef.current) {
      clearTimeout(layoutTimeoutRef.current);
      layoutTimeoutRef.current = null;
    }
    if (layoutRef.current) {
      layoutRef.current.stop();
      layoutRef.current = null;
      const graph = graphRef.current;
      if (graph) {
        noverlap.assign(graph, NOVERLAP_SETTINGS);
        sigmaRef.current?.refresh();
      }
      setIsLayoutRunning(false);
    }
  }, []);

  return {
    containerRef,
    setGraph,
    zoomIn,
    zoomOut,
    resetZoom,
    focusNode,
    isLayoutRunning,
    startLayout,
    stopLayout,
    selectedNode,
    setSelectedNode,
  };
};
