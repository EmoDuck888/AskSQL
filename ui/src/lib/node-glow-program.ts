import { NodeProgram } from 'sigma/rendering';
import { floatColor } from 'sigma/utils';
import type { NodeDisplayData, RenderParams } from 'sigma/types';
import type { ProgramInfo } from 'sigma/rendering';
import type { Attributes } from 'graphology-types';

// ---------------------------------------------------------------------------
// NodeGlowProgram —— 带光晕的发光节点渲染程序（替代 Sigma 默认的 NodeCircleProgram）
//
// 原理：
//   1. 顶点着色器把节点三角形放大 u_glowRatio 倍，为光晕留出空间；
//   2. 片元着色器用一条连续的径向衰减曲线渲染「实心亮点 + 柔和光晕」：
//      - 核心区域（r < core）：alpha 全亮，中心提亮、向外略压暗，模拟球体受光；
//      - 光晕区域（core < r < 边缘）：pow 曲线平滑衰减到 0，与核心无缝衔接；
//   3. 拾取（picking）模式下只保留核心圆盘作为命中区域，光晕不响应鼠标，
//      避免点击/悬停命中范围虚大。
// ---------------------------------------------------------------------------

// language=GLSL
const VERTEX_SHADER_SOURCE = /* glsl */ `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_position;
attribute float a_size;
attribute float a_angle;

uniform mat3 u_matrix;
uniform float u_sizeRatio;
uniform float u_correctionRatio;
uniform float u_glowRatio;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

const float bias = 255.0 / 254.0;

void main() {
  // 三角形整体放大 u_glowRatio 倍，外围空间用于渲染光晕
  float size = a_size * u_glowRatio * u_correctionRatio / u_sizeRatio * 4.0;
  vec2 diffVector = size * vec2(cos(a_angle), sin(a_angle));
  vec2 position = a_position + diffVector;
  gl_Position = vec4(
    (u_matrix * vec3(position, 1)).xy,
    0,
    1
  );

  v_diffVector = diffVector;
  v_radius = size / 2.0;

  #ifdef PICKING_MODE
  // For picking mode, we use the ID as the color:
  v_color = a_id;
  #else
  // For normal mode, we use the color:
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`;

// language=GLSL
const FRAGMENT_SHADER_SOURCE = /* glsl */ `
precision highp float;

varying vec4 v_color;
varying vec2 v_diffVector;
varying float v_radius;

uniform float u_correctionRatio;
uniform float u_glowRatio;
uniform float u_glowStrength;
uniform float u_glowFalloff;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);

void main(void) {
  float border = u_correctionRatio * 2.0;
  float dist = length(v_diffVector);
  float core = v_radius / u_glowRatio; // 实心核心半径（还原未放大的尺寸）

  // No antialiasing for picking mode:
  #ifdef PICKING_MODE
  // 拾取命中区仅限实心核心，光晕不响应鼠标
  if (dist > core + border)
    gl_FragColor = transparent;
  else
    gl_FragColor = v_color;

  #else
  // 全半径连续衰减曲线：中心 1 → 外缘 0，核心与光晕无缝衔接
  float t = clamp(dist / max(v_radius, 0.0001), 0.0, 1.0);
  // 光晕区按 u_glowStrength 压暗，核心内保持全亮
  float inCore = 1.0 - smoothstep(core * 0.85, core * 1.05, dist);
  float alpha = pow(1.0 - t, u_glowFalloff) * mix(u_glowStrength, 1.0, inCore);

  // 球体感：核心中心提亮、向外略压暗
  float inner = clamp(dist / max(core, 0.0001), 0.0, 1.0);
  float grad = 1.28 - 0.32 * inner * inner;
  vec3 rgb = v_color.rgb * mix(1.0, grad, inCore);

  // 光晕外边缘抗锯齿
  float aa = clamp((dist - (v_radius - border)) / max(border, 0.0001), 0.0, 1.0);
  gl_FragColor = mix(vec4(rgb, alpha * v_color.a), transparent, aa);
  #endif
}
`;

const UNIFORMS = ['u_sizeRatio', 'u_correctionRatio', 'u_matrix', 'u_glowRatio', 'u_glowStrength', 'u_glowFalloff'] as const;

export default class NodeGlowProgram<
  N extends Attributes = Attributes,
  E extends Attributes = Attributes,
  G extends Attributes = Attributes,
> extends NodeProgram<(typeof UNIFORMS)[number], N, E, G> {
  static readonly ANGLE_1 = 0;
  static readonly ANGLE_2 = (2 * Math.PI) / 3;
  static readonly ANGLE_3 = (4 * Math.PI) / 3;

  getDefinition() {
    return {
      VERTICES: 3,
      VERTEX_SHADER_SOURCE,
      FRAGMENT_SHADER_SOURCE,
      METHOD: WebGLRenderingContext.TRIANGLES,
      UNIFORMS,
      ATTRIBUTES: [
        { name: 'a_position', size: 2, type: WebGLRenderingContext.FLOAT },
        { name: 'a_size', size: 1, type: WebGLRenderingContext.FLOAT },
        { name: 'a_color', size: 4, type: WebGLRenderingContext.UNSIGNED_BYTE, normalized: true },
        { name: 'a_id', size: 4, type: WebGLRenderingContext.UNSIGNED_BYTE, normalized: true },
      ],
      CONSTANT_ATTRIBUTES: [{ name: 'a_angle', size: 1, type: WebGLRenderingContext.FLOAT }],
      CONSTANT_DATA: [
        [NodeGlowProgram.ANGLE_1],
        [NodeGlowProgram.ANGLE_2],
        [NodeGlowProgram.ANGLE_3],
      ],
    };
  }

  processVisibleItem(nodeIndex: number, startIndex: number, data: NodeDisplayData) {
    const array = this.array;
    const color = floatColor(data.color);
    array[startIndex++] = data.x;
    array[startIndex++] = data.y;
    array[startIndex++] = data.size;
    array[startIndex++] = color;
    array[startIndex++] = nodeIndex;
  }

  setUniforms(params: RenderParams, { gl, uniformLocations }: ProgramInfo) {
    const {
      u_sizeRatio,
      u_correctionRatio,
      u_matrix,
      u_glowRatio,
      u_glowStrength,
      u_glowFalloff,
    } = uniformLocations;
    gl.uniform1f(u_correctionRatio, params.correctionRatio);
    gl.uniform1f(u_sizeRatio, params.sizeRatio);
    gl.uniformMatrix3fv(u_matrix, false, params.matrix);
    // 光晕参数（可按视觉需求微调）：
    gl.uniform1f(u_glowRatio, 1.5); // 光晕外扩倍数（总直径 = 核心 × 2.2）
    gl.uniform1f(u_glowStrength, 0.20); // 光晕最大透明度
    gl.uniform1f(u_glowFalloff, 1.6); // 光晕衰减指数，越大光晕越短促
  }
}
