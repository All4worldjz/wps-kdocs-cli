# OpenClaw Vertex 配置过程归档（2026-04-09）

## 目标
- 通过 `xlmyyjz@34.124.143.168` 免密 SSH 管理远端 OpenClaw。
- 激活 Vertex AI 认证并将默认 LLM 设置为 `google-vertex/gemini-3-flash-preview`。
- 配置 fallback 为 `google-vertex/gemini-3.1-pro-preview`。
- 完成连通性与推理验证。

## 关键执行记录（摘要）
1. SSH 认证排查：确认 `~/.ssh/google_compute_engine` 可免密登录。
2. OpenClaw 扫描：
   - 状态目录：`/workshop/openclaw`（`~/.openclaw` 软链）
   - 服务：`openclaw-gateway.service`（systemd user）
3. 安全加固：
   - `chmod 700 /workshop/openclaw`
   - `chmod 600 /workshop/openclaw/agents/main/agent/auth-profiles.json`
4. Gateway 可信代理项：设置 `gateway.trustedProxies=["127.0.0.1","::1"]`。
5. Vertex 认证：
   - 完成 `gcloud auth application-default login`，生成 ADC。
   - 增加 systemd override 环境变量：
     - `GOOGLE_CLOUD_PROJECT=project-72ff2424-2b06-4cea-84f`
     - `GCLOUD_PROJECT=project-72ff2424-2b06-4cea-84f`
     - `GOOGLE_CLOUD_LOCATION=global`
6. 模型配置：
   - primary：`google-vertex/gemini-3-flash-preview`
   - fallback：`google-vertex/gemini-3.1-pro-preview`
7. 参数修正：为 flash/pro 模型设置低延迟参数：
   - `params.thinking.enabled=false`
   - `params.maxTokens=256`

## 验证结果（摘要）
- Vertex 直连 API（global）可用，返回成功文本。
- OpenClaw `infer model run` 在 `google-vertex/*` 模型下返回成功。
- OpenClaw 深度状态显示默认会话模型已切换为 Gemini Flash。

## 说明
- 本目录内 JSON 文件均为脱敏版本，不包含明文密钥。
