# 结果汇总

## 当前有效配置
- Default model: `google-vertex/gemini-3-flash-preview`
- Fallbacks: `google-vertex/gemini-3.1-pro-preview`
- Service env:
  - `GOOGLE_CLOUD_PROJECT=project-72ff2424-2b06-4cea-84f`
  - `GCLOUD_PROJECT=project-72ff2424-2b06-4cea-84f`
  - `GOOGLE_CLOUD_LOCATION=global`

## 性能观察（最近一轮）
- Vertex 直连（global）
  - flash: 约 3s
  - 3.1-pro: 约 5s
- OpenClaw 端到端（infer）
  - flash: 数十秒级
  - 3.1-pro: 数十秒级

结论：慢点主要在 OpenClaw 运行链路开销，非 Vertex API 基础连通性。
