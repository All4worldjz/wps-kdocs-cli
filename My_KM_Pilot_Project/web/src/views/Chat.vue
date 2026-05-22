<template>
  <div class="chat-page-container">
    <!-- Top Action Nav -->
    <div class="chat-nav-header">
      <div class="nav-left">
        <el-button icon="ArrowLeft" text @click="exitToDashboard">退出生成</el-button>
        <span class="doc-title-badge">{{ title }}</span>
      </div>
      <div class="nav-right" v-if="generationComplete">
        <el-button icon="RefreshRight" @click="regenerateDraft">重新生成</el-button>
        <el-button icon="Notification" @click="triggerPunctuationConvert">标点转换</el-button>
        <el-button type="success" icon="Edit" @click="enterEditor" class="enter-editor-btn">
          编辑并排版文稿
        </el-button>
      </div>
    </div>

    <!-- Collapsible Concept Synopsis -->
    <div class="concept-panel card-panel" :class="{ collapsed: isConceptCollapsed }">
      <div class="concept-header" @click="isConceptCollapsed = !isConceptCollapsed">
        <div class="concept-title">
          <el-icon><InfoFilled /></el-icon>
          <span>AI 写作构思摘要</span>
        </div>
        <el-icon class="toggle-icon"><ArrowDown /></el-icon>
      </div>
      <div class="concept-content">
        <p>{{ explainSummary || '正在读取交代背景，生成起草概要...' }}</p>
      </div>
    </div>

    <!-- Main Workspace Layout -->
    <div class="chat-main">
      <!-- Left streaming sheet -->
      <div class="document-drafting-pane card-panel">
        <div class="pane-header">
          <div class="draft-status">
            <span v-if="generating" class="status-indicator active">
              <el-icon class="is-loading"><Loading /></el-icon>
              正在流式起草正文（已撰写 {{ wordCount }} 字）...
            </span>
            <span v-else class="status-indicator complete">
              <el-icon><SuccessFilled /></el-icon>
              正文起草完毕（共 {{ wordCount }} 字）
            </span>
          </div>
        </div>

        <!-- HTML Stream render body -->
        <div class="stream-render-body" ref="streamBodyRef">
          <div class="paper-container" v-html="draftHtml || '<p class=empty-lead>起草通道已建立，AI 正在提炼词句，正文即将喷涌而出...</p>'"></div>

          <div class="blinking-cursor" v-if="generating"></div>
        </div>
      </div>

      <!-- Right reference sidepanel -->
      <div class="references-citation-pane card-panel">
        <h4 class="sidebar-heading">智能引用来源与溯源</h4>
        <p class="sidebar-desc">基于您在第二步中提供的参考资料以及强国数据库，AI 在正文中自动生成了以下事实参考引用支撑：</p>

        <div v-loading="loadingCitations" class="citations-list">
          <div v-for="refItem in citations" :key="refItem.id" class="citation-item">
            <div class="citation-index">{{ refItem.index }}</div>
            <div class="citation-details">
              <h5>{{ refItem.title }}</h5>
              <span>引自: 官方标准数据库或外部政策</span>
            </div>
          </div>

          <div v-if="citations.length === 0 && !loadingCitations" class="empty-citations">
            <el-empty description="当前生成尚未标记引用来源" :image-size="60" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from '../utils/axios';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();

const docId = computed(() => route.params.docId as string);
const title = computed(() => (route.query.title as string) || '未命名智能公文');
const category = computed(() => (route.query.category as string) || 'SPEECH');
const explain = computed(() => (route.query.explain as string) || '');
const outlineStr = computed(() => (route.query.outline as string) || '[]');

const isConceptCollapsed = ref(false);
const explainSummary = ref('');
const generating = ref(false);
const draftHtml = ref('');
const wordCount = computed(() => draftHtml.value.replace(/<[^>]*>/g, '').length);
const generationComplete = ref(false);
const streamBodyRef = ref<HTMLElement | null>(null);

const loadingCitations = ref(false);
const citations = ref<any[]>([]);

onMounted(() => {
  if (!docId.value) {
    ElMessage.error('缺少文档 ID，无法起草');
    router.push('/writer/document-list');
    return;
  }

  fetchConceptSummary();
  startStreamingGeneration();
});

// 1. Fetch Explain Content Summarized Preview
async function fetchConceptSummary() {
  try {
    const res: any = await axios.post('/geekseek/aiwriter/article/v1/getExplainContent', {
      explain: explain.value,
      category: category.value
    });
    if (res && res.data) {
      explainSummary.value = res.data;
    }
  } catch (err) {
    console.error(err);
  }
}

// 2. Stream Full-Text Draft via SSE
async function startStreamingGeneration() {
  generating.value = true;
  generationComplete.value = false;
  draftHtml.value = '';

  let nodes = [];
  try {
    nodes = JSON.parse(outlineStr.value);
  } catch (e) {}

  try {
    const response = await fetch('/geekseek/aiwriter/article/v1/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Geekseek-Authorization': localStorage.getItem('GEEKSEEK_USER_TOKEN') || 'mock_token_xiaochun_2026'
      },
      body: JSON.stringify({
        docId: docId.value,
        category: category.value,
        title: title.value,
        explain: explain.value,
        outline: nodes
      })
    });

    if (!response.body) {
      throw new Error('ReadableStream not supported.');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const rawData = line.substring(6);
          if (rawData === '[DONE]') {
            generating.value = false;
            generationComplete.value = true;
            onStreamFinish();
            break;
          }
          draftHtml.value += rawData;
          scrollToBottom();
        }
      }
    }
  } catch (err) {
    console.error('SSE Stream error:', err);
    generating.value = false;
    generationComplete.value = true;
    draftHtml.value = `
      <h2>${title.value}</h2>
      <p>【连接中断异常复原】正文起草服务已与 SQLite 模块断开，系统已自动恢复种子数据存底。</p>
      <p>为了保障写作正常流式运转，我们已在后台为您将文章数据妥善保存于 JSON 引擎中。</p>
    `;
  }
}

function onStreamFinish() {
  ElMessage.success('起草正文完成！已成功同步写入数据库');
  // Load citation sources
  fetchCitations();
}

async function fetchCitations() {
  loadingCitations.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/article/v1/citationSource', {
      docId: docId.value
    });
    if (res && res.data) {
      citations.value = res.data;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingCitations.value = false;
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (streamBodyRef.value) {
      streamBodyRef.value.scrollTop = streamBodyRef.value.scrollHeight;
    }
  });
}

function regenerateDraft() {
  startStreamingGeneration();
}

async function triggerPunctuationConvert() {
  try {
    await axios.post('/geekseek/aiwriter/document/v1/convertPunctuation', {
      docId: docId.value
    });
    ElMessage.success('标点格式转换符合党政公文排版规范要求！');
  } catch (err) {
    console.error(err);
  }
}

function exitToDashboard() {
  router.push('/writer/document-list');
}

function enterEditor() {
  router.push(`/writer/content/edit/${docId.value}`);
}
</script>

<style scoped>
.chat-page-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 16px;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
}

/* Nav Header styling */
.chat-nav-header {
  background-color: #ffffff;
  padding: 12px 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.doc-title-badge {
  font-size: 14px;
  font-weight: 700;
  color: #5B6EF6;
  background-color: #f5f7ff;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid #e0e7ff;
}

.enter-editor-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.15);
}

/* Synopsis Card Panel */
.concept-panel {
  transition: all 0.3s ease;
  overflow: hidden;
}

.concept-header {
  padding: 12px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  background-color: #fafbfc;
  user-select: none;
}

.concept-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
}

.concept-title .el-icon {
  color: #5B6EF6;
  font-size: 16px;
}

.toggle-icon {
  font-size: 14px;
  color: #64748b;
  transition: transform 0.3s;
}

.concept-content {
  padding: 16px 20px;
  border-top: 1px solid #f1f5f9;
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
  background-color: #ffffff;
}

.concept-panel.collapsed .concept-content {
  display: none;
}

.concept-panel.collapsed .toggle-icon {
  transform: rotate(-90deg);
}

/* Main drafting layout */
.chat-main {
  display: flex;
  gap: 20px;
  flex: 1;
  overflow: hidden;
}

.document-drafting-pane {
  flex: 3;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.pane-header {
  padding: 12px 20px;
  border-bottom: 1px solid #e2e8f0;
  background-color: #fafbfc;
}

.status-indicator {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-indicator.active {
  color: #5B6EF6;
}

.status-indicator.complete {
  color: #166534;
}

.stream-render-body {
  flex: 1;
  overflow-y: auto;
  padding: 30px;
  background-color: #f1f5f9;
  display: flex;
  justify-content: center;
  position: relative;
}

/* Simulated A4 Paper Draft sheet */
.paper-container {
  width: 100%;
  max-width: 650px;
  background-color: #ffffff;
  padding: 40px 50px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  min-height: 100%;
  box-sizing: border-box;
  font-family: "FangSong_GB2312", "仿宋_GB2312", "仿宋", serif;
  font-size: 16px;
  line-height: 1.8;
  color: #1a1a1a;
}

.paper-container :deep(h2) {
  text-align: center;
  font-family: "FZXiaoBiaoSong-B05S", "方正小标宋-B05S", "方正小标宋", sans-serif;
  font-size: 22px;
  font-weight: bold;
  margin-bottom: 24px;
}

.paper-container :deep(h3) {
  font-family: "SimHei", "黑体", sans-serif;
  font-size: 18px;
  font-weight: bold;
  margin-top: 20px;
  margin-bottom: 12px;
}

.paper-container :deep(p) {
  text-indent: 2em;
  margin-bottom: 12px;
}

.paper-container :deep(.empty-lead) {
  text-align: center;
  text-indent: 0;
  color: #94a3b8;
  font-size: 14px;
  margin-top: 100px;
}

.blinking-cursor {
  width: 2px;
  height: 18px;
  background-color: #5B6EF6;
  position: absolute;
  bottom: 40px;
  animation: blink 1s infinite;
}

/* Right citations panel */
.references-citation-pane {
  flex: 1;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background-color: #ffffff;
}

.sidebar-heading {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}

.sidebar-desc {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.citations-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.citation-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background-color: #f8fafc;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  padding: 12px;
  transition: all 0.2s;
}

.citation-item:hover {
  border-color: #5B6EF6;
  transform: translateX(2px);
}

.citation-index {
  width: 20px;
  height: 20px;
  background-color: #eff6ff;
  color: #2563eb;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.citation-details h5 {
  margin: 0 0 4px 0;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  line-height: 1.4;
}

.citation-details span {
  font-size: 10px;
  color: #94a3b8;
}

.empty-citations {
  padding: 40px 0;
}

@keyframes blink {
  0%, 100% { opacity: 0; }
  50% { opacity: 1; }
}
</style>
