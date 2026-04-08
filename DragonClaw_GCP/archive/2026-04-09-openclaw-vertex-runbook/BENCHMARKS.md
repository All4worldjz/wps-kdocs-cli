# 基准记录（2026-04-09）

## Vertex 直连 API（global）
- `gemini-3-flash-preview`: 3.136997s, 2.977371s
- `gemini-3.1-pro-preview`: 5.278051s, 4.791360s

## OpenClaw 端到端（infer）
- `google-vertex/gemini-3-flash-preview`: 52s, 57s
- `google-vertex/gemini-3.1-pro-preview`: 41s, 48s

## 结论
- Vertex API 本身响应在秒级。
- OpenClaw 端到端耗时显著更高，主要瓶颈不在基础网络连通性。
