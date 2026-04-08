# 复现命令（核心）

## 1) OpenClaw 状态
```bash
openclaw models status
openclaw status --deep
```

## 2) Vertex 直连 API（global）
```bash
ACCESS_TOKEN=$(gcloud auth application-default print-access-token)
curl -X POST \
  "https://aiplatform.googleapis.com/v1/projects/project-72ff2424-2b06-4cea-84f/locations/global/publishers/google/models/gemini-3-flash-preview:generateContent" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"contents":[{"role":"user","parts":[{"text":"Reply with exactly: vertex-api-ok"}]}]}'
```

## 3) OpenClaw 推理测试
```bash
export GOOGLE_CLOUD_PROJECT=project-72ff2424-2b06-4cea-84f
export GCLOUD_PROJECT=project-72ff2424-2b06-4cea-84f
export GOOGLE_CLOUD_LOCATION=global

openclaw infer model run \
  --prompt "Reply with exactly: default-openclaw-ok" \
  --json
```
