import React from 'react';

// SVG定义组件，用于渐变和滤镜效果
export const GraphDefinitions = () => {
  return (
    <svg style={{ position: 'absolute', width: 0, height: 0 }}>
      <defs>
        {/* 基础渐变 */}
        <linearGradient id="gradient-blue" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#3b82f6" stopOpacity="1" />
          <stop offset="50%" stopColor="#1d4ed8" stopOpacity="1" />
          <stop offset="100%" stopColor="#1e40af" stopOpacity="1" />
        </linearGradient>

        <linearGradient id="gradient-purple" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ec4899" stopOpacity="1" />
          <stop offset="50%" stopColor="#db2777" stopOpacity="1" />
          <stop offset="100%" stopColor="#be185d" stopOpacity="1" />
        </linearGradient>
        
        <linearGradient id="gradient-rainbow" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#ff6b6b" />
          <stop offset="16.66%" stopColor="#ffa726" />
          <stop offset="33.33%" stopColor="#ffeb3b" />
          <stop offset="50%" stopColor="#66bb6a" />
          <stop offset="66.66%" stopColor="#42a5f5" />
          <stop offset="83.33%" stopColor="#ab47bc" />
          <stop offset="100%" stopColor="#ff6b6b" />
          <animateTransform
            attributeName="gradientTransform"
            type="rotate"
            values="0;360"
            dur="4s"
            repeatCount="indefinite"
          />
        </linearGradient>
        
        <linearGradient id="gradient-electric" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#06b6d4" stopOpacity="1" />
          <stop offset="50%" stopColor="#0891b2" stopOpacity="1" />
          <stop offset="100%" stopColor="#0e7490" stopOpacity="1" />
        </linearGradient>
        
        {/* 发光滤镜 */}
        <filter id="glow-blue">
          <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
          <feMerge> 
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        
        <filter id="glow-purple">
          <feGaussianBlur stdDeviation="4" result="coloredBlur"/>
          <feMerge> 
            <feMergeNode in="coloredBlur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        
        {/* 电流效果滤镜 */}
        <filter id="electric-effect">
          <feTurbulence baseFrequency="0.9" numOctaves="4" result="noise" seed="1"/>
          <feDisplacementMap in="SourceGraphic" in2="noise" scale="2" />
          <feGaussianBlur stdDeviation="1" result="blur"/>
          <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
        
        {/* 阴影滤镜 */}
        <filter id="drop-shadow">
          <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
        </filter>
        
        {/* 节点渐变 */}
        <linearGradient id="node-gradient-table" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="100%" stopColor="#1e40af" />
        </linearGradient>

        <linearGradient id="node-gradient-column" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#ec4899" />
          <stop offset="100%" stopColor="#be185d" />
        </linearGradient>

        <linearGradient id="node-gradient-relation" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#06b6d4" />
          <stop offset="100%" stopColor="#0891b2" />
        </linearGradient>

        <linearGradient id="node-gradient-default" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#10b981" />
          <stop offset="100%" stopColor="#059669" />
        </linearGradient>
        
        {/* 动画标记 */}
        <marker id="arrowhead-animated" markerWidth="10" markerHeight="7" 
                refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#334155" />
          <animateTransform
            attributeName="transform"
            type="scale"
            values="1;1.2;1"
            dur="1s"
            repeatCount="indefinite"
          />
        </marker>
        
        <marker id="arrowhead-pulse" markerWidth="10" markerHeight="7" 
                refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#f5576c" />
          <animate
            attributeName="opacity"
            values="0.5;1;0.5"
            dur="2s"
            repeatCount="indefinite"
          />
        </marker>
        
        <marker id="arrowhead-rainbow" markerWidth="10" markerHeight="7" 
                refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="url(#gradient-rainbow)" />
        </marker>
        
        <marker id="arrowhead-electric" markerWidth="10" markerHeight="7" 
                refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="#00f2fe" />
          <animate
            attributeName="opacity"
            values="1;0.8;1"
            dur="0.1s"
            repeatCount="indefinite"
          />
        </marker>
      </defs>
    </svg>
  );
};
