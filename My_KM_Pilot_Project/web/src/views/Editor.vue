<template>
  <div class="editor-page-container">
    <!-- Top Action Nav -->
    <div class="editor-header">
      <div class="header-left">
        <el-button icon="ArrowLeft" text @click="exitToDashboard">创作中心</el-button>
        <div class="doc-title-wrapper">
          <el-input
            v-model="docTitle"
            placeholder="未命名公文"
            class="doc-title-input"
            @blur="autoSave"
          />
          <span class="save-status-indicator">
            <el-icon v-if="saving"><Loading /></el-icon>
            <el-icon v-else><CircleCheck /></el-icon>
            {{ saving ? '正在保存...' : '已保存于本地' }}
          </span>
        </div>
      </div>

      <div class="header-right">
        <el-dropdown trigger="click" @command="handleExportCommand">
          <el-button type="primary" icon="Download">
            导出下载 <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="word">导出为 Word 文档 (.docx)</el-dropdown-item>
              <el-dropdown-item command="pdf">导出为 PDF 文档 (.pdf)</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button type="success" icon="DocumentChecked" @click="manualSave">
          手动保存
        </el-button>
      </div>
    </div>

    <!-- Main Workspace -->
    <div class="workspace-body">
      <!-- Left side: TinyMCE Editor -->
      <div class="editor-container card-panel">
        <editor
          v-if="tinymceLoaded"
          v-model="editorContent"
          tinymce-script-src="https://cdnjs.cloudflare.com/ajax/libs/tinymce/6.8.3/tinymce.min.js"
          :init="editorInitConfig"
          class="tinymce-editor"
          @selection-change="handleTextSelection"
        />
        <div v-else class="editor-loading-box">
          <el-icon class="is-loading"><Loading /></el-icon>
          <p>正在拉取 TinyMCE 公文排版内核，请稍候...</p>
        </div>
      </div>

      <!-- Right side: AI Sidebar Panel -->
      <div class="ai-sidebar card-panel">
        <el-tabs v-model="activeSideTab" class="sidebar-tabs" stretch>
          <!-- 1. 内容优化 -->
          <el-tab-pane label="内容优化" name="optimize">
            <div class="tab-pane-content">
              <div class="pane-heading">
                <h4>内容优化辅助</h4>
                <p>在左侧编辑器中选中文字，激活以下 AI 优化引擎：</p>
              </div>

              <!-- Selection display -->
              <div class="selected-text-box" :class="{ 'has-selection': selectedText }">
                <span class="box-label">已选中字数: {{ selectedText.length }}</span>
                <p class="selection-preview">{{ selectedText || '当前未选中任何文字。请在左侧段落中划词。' }}</p>
              </div>

              <!-- Optimization action tabs -->
              <el-tabs v-model="activeOptimizeSubTab" type="card" class="optimize-sub-tabs">
                <el-tab-pane label="润色" name="POLISH" />
                <el-tab-pane label="扩写" name="EXPAND" />
                <el-tab-pane label="缩写" name="SHORTEN" />
                <el-tab-pane label="改写" name="REWRITE" />
              </el-tabs>

              <div class="optimize-action-area">
                <el-button
                  type="primary"
                  icon="MagicStick"
                  class="action-btn"
                  :disabled="!selectedText"
                  :loading="optimizingText"
                  @click="runOptimize"
                >
                  执行 AI {{ getOptimizeSubName(activeOptimizeSubTab) }}
                </el-button>
              </div>

              <!-- Optimization results -->
              <div v-if="optimizeResult" class="optimize-result-panel">
                <h5>AI 优化建议结果：</h5>
                <div class="result-text">{{ optimizeResult }}</div>
                <div class="result-actions">
                  <el-button type="success" size="small" icon="Check" @click="applyOptimizeResult">
                    采纳并替换
                  </el-button>
                  <el-button size="small" icon="DocumentAdd" @click="insertOptimizeResult">
                    尾部插入
                  </el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- 2. 格式排版 -->
          <el-tab-pane label="格式排版" name="layout">
            <div class="tab-pane-content scrollable">
              <div class="pane-heading">
                <h4>国家标准公文模版排版</h4>
                <p>选择以下模版卡片，可直接在左侧正文中实施标准的标题、字号、段落缩进及行距排版。</p>
              </div>

              <div class="layout-template-groups">
                <div
                  v-for="group in formatTemplates"
                  :key="group.id"
                  class="template-card"
                  @click="applyFormatTemplate(group)"
                >
                  <div class="card-left">
                    <el-icon class="template-icon"><Collection /></el-icon>
                  </div>
                  <div class="card-right">
                    <h5>{{ group.name }}</h5>
                    <p>{{ group.desc }}</p>
                  </div>
                </div>
              </div>
            </div>
          </el-tab-pane>

          <!-- 3. 智能校对 -->
          <el-tab-pane label="智能校对" name="proofread">
            <div class="tab-pane-content">
              <div class="pane-heading">
                <h4>智能错别字与敏感词校对</h4>
                <p>点击下方开始按钮，AI 将全面扫描您的文稿，检索涉密漏洞、错别字及党政专有名词失误。</p>
              </div>

              <div class="proofread-action-bar">
                <el-button
                  type="primary"
                  icon="Search"
                  class="action-btn"
                  :loading="proofreading"
                  @click="runProofreading"
                >
                  开始智能校对
                </el-button>
              </div>

              <!-- Corrections Suggestions list -->
              <div v-if="corrections.length > 0" class="corrections-container">
                <h5>检出问题列表 ({{ corrections.length }} 处)：</h5>
                <div class="corrections-list">
                  <div v-for="(item, idx) in corrections" :key="idx" class="correction-card">
                    <div class="card-top">
                      <span class="err-badge" :class="item.type.toLowerCase()">{{ getErrTypeName(item.type) }}</span>
                    </div>
                    <div class="card-mid">
                      <p><strong>原词:</strong> <span class="err-word">{{ item.word }}</span></p>
                      <p><strong>建议:</strong> <span class="correct-word">{{ item.correct }}</span></p>
                      <p class="err-desc">{{ item.desc }}</p>
                    </div>
                    <div class="card-bottom">
                      <el-button type="success" size="small" @click="acceptCorrection(item, idx)">采纳建议</el-button>
                      <el-button size="small" @click="ignoreCorrection(idx)">忽略</el-button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else-if="proofreadFinished" class="proofread-clean">
                <el-result icon="success" title="未检出任何问题" sub-title="您的文章十分规范，请放心使用！" />
              </div>
            </div>
          </el-tab-pane>

          <!-- 4. 小知AI -->
          <el-tab-pane label="小知AI" name="xiaozhi">
            <div class="tab-pane-content flex-column-layout">
              <div class="chat-messages-container" ref="chatContainerRef">
                <div
                  v-for="(msg, index) in chatMessages"
                  :key="index"
                  class="chat-bubble"
                  :class="msg.role"
                >
                  <div class="avatar-badge">
                    {{ msg.role === 'assistant' ? '小' : '我' }}
                  </div>
                  <div class="bubble-content">
                    <p>{{ msg.content }}</p>
                  </div>
                </div>
              </div>

              <!-- Chat input -->
              <div class="chat-input-row">
                <el-input
                  v-model="chatInputText"
                  placeholder="询问小知关于公文起草或修改的建议..."
                  @keyup.enter="sendChatMessage"
                >
                  <template #append>
                    <el-button icon="Promotion" @click="sendChatMessage" />
                  </template>
                </el-input>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import Editor from '@tinymce/tinymce-vue';
import axios from '../utils/axios';
import { ElMessage } from 'element-plus';

const route = useRoute();
const router = useRouter();

const docId = ref((route.params.docId as string) || '');
const docTitle = ref('我的新智能文稿');
const editorContent = ref('');
const saving = ref(false);
const tinymceLoaded = ref(true);

const activeSideTab = ref('optimize');

// ================== CONTENT OPTIMIZE STATE ==================
const selectedText = ref('');
const activeOptimizeSubTab = ref('POLISH');
const optimizingText = ref(false);
const optimizeResult = ref('');

// ================== SMART LAYOUT TEMPLATES ==================
const formatTemplates = ref<any[]>([
  { id: 'layout_template_01', name: '通用格式-无红头', desc: '标准的政企公文通用格式，不包含红头。正文三号仿宋_GB2312。' },
  { id: 'layout_template_02', name: '通用格式-有红头', desc: '标准的政企公文通用格式，自带红头。标题二号方正小标宋。' },
  { id: 'layout_template_03', name: '正式公文报告', desc: '标准国家报告规格，正文仿宋、落款居右、双面页边距规范。' },
  { id: 'layout_template_04', name: '正式公文通知', desc: '用于发布工作安排与节点要求。' }
]);

// ================== PROOFREAD STATE ==================
const proofreading = ref(false);
const proofreadFinished = ref(false);
const corrections = ref<any[]>([]);

// ================== XIAOZHI CHAT STATE ==================
const chatInputText = ref('');
const chatContainerRef = ref<HTMLElement | null>(null);
const chatMessages = ref<any[]>([
  { role: 'assistant', content: '您好！我是您的公文小助手「小春 / 水哥」。您可以向我提问关于公文格式、用词润色或内容补充的问题，我会竭诚为您解答！' }
]);

// ================== TINYMCE CONFIG ==================
const editorInitConfig = {
  height: '100%',
  language: 'zh_CN',
  menubar: false,
  branding: false,
  plugins: 'link lists image charmap preview searchreplace wordcount code',
  toolbar: 'undo redo | blocks | fontfamily fontsize | bold italic underline strikethrough forecolor backcolor | alignleft aligncenter alignright alignjustify | lineheight outdent indent | removeformat code',
  font_family_formats: '仿宋_GB2312=FangSong_GB2312, 仿宋; 楷体=KaiTi, 楷体_GB2312; 黑体=SimHei, 黑体; 方正小标宋=FZXiaoBiaoSong-B05S, JXBS; 宋体=SimSun; 微软雅黑=Microsoft YaHei',
  font_size_formats: '八号=5pt 七号=5.5pt 小六=6.5pt 六号=7.5pt 小五=9pt 五号=10.5pt 小四=12pt 四号=14pt 小三=15pt 三号=16pt 小二=18pt 二号=22pt 小一=24pt 一号=26pt 二号大=28pt 二号特=30pt',
  line_height_formats: '1 1.2 1.5 2 28pt 30pt 35pt 36pt',
  content_style: `
    @font-face {
      font-family: 'FangSong_GB2312';
      src: local('FangSong_GB2312'), local('仿宋_GB2312');
    }
    @font-face {
      font-family: 'FZXiaoBiaoSong-B05S';
      src: local('FZXiaoBiaoSong-B05S'), local('方正小标宋');
    }
    body {
      font-family: 'FangSong_GB2312', '仿宋_GB2312', serif;
      font-size: 16px;
      line-height: 1.8;
      padding: 40px 50px !important;
      max-width: 720px;
      margin: 0 auto;
      color: #111;
    }
    p {
      text-indent: 2em;
      margin-bottom: 12px;
    }
    h2 {
      text-align: center;
      font-family: 'FZXiaoBiaoSong-B05S', sans-serif;
      font-size: 22px;
      font-weight: bold;
      margin-bottom: 24px;
    }
    h3 {
      font-family: 'SimHei', sans-serif;
      font-size: 18px;
      font-weight: bold;
      margin-top: 20px;
      margin-bottom: 12px;
    }
  `,
  setup: (editor: any) => {
    editor.on('init', () => {
      // Set styles on load
    });
  }
};

onMounted(() => {
  if (docId.value) {
    loadDocumentDetails();
  }
  // Load templates list
  axios.post('/geekseek/aiwriter/format/template/list').then((res: any) => {
    if (res && res.data) {
      formatTemplates.value = res.data;
    }
  });
});

// Load document details
async function loadDocumentDetails() {
  try {
    const res: any = await axios.get(`/geekseek/aiwriter/document/v1/detail?docId=${docId.value}`);
    if (res && res.data) {
      docTitle.value = res.data.title;
      editorContent.value = res.data.contentHtml || '';
    }
  } catch (err) {
    console.error(err);
  }
}

// Auto Save trigger on title blur / editor input
async function autoSave() {
  if (!docId.value) return;
  saving.value = true;
  try {
    const textContentOnly = editorContent.value.replace(/<[^>]*>/g, '');
    await axios.post('/geekseek/aiwriter/document/v1/addOrUpdate', {
      id: docId.value,
      title: docTitle.value,
      contentHtml: editorContent.value,
      contentText: textContentOnly,
      wordCount: textContentOnly.length
    });
  } catch (err) {
    console.error('Auto save failed:', err);
  } finally {
    saving.value = false;
  }
}

async function manualSave() {
  await autoSave();
  ElMessage.success('文稿内容保存成功！');
}

function exitToDashboard() {
  router.push('/writer/document-list');
}

// Selection monitoring
function handleTextSelection() {
  const activeEditor = (window as any).tinymce?.activeEditor;
  if (activeEditor) {
    const text = activeEditor.selection.getContent({ format: 'text' });
    selectedText.value = text.trim();
  }
}

// Optimize sub-pane headers
function getOptimizeSubName(type: string) {
  if (type === 'POLISH') return '润色';
  if (type === 'EXPAND') return '扩写';
  if (type === 'SHORTEN') return '缩写';
  return '改写';
}

// Run AI optimization
async function runOptimize() {
  if (!selectedText.value) return;
  optimizingText.value = true;
  optimizeResult.value = '';
  try {
    const res: any = await axios.post('/geekseek/aiwriter/article/v1/optimize', {
      text: selectedText.value,
      type: activeOptimizeSubTab.value
    });
    if (res && res.data) {
      optimizeResult.value = res.data;
    }
  } catch (err) {
    console.error(err);
  } finally {
    optimizingText.value = false;
  }
}

function applyOptimizeResult() {
  const activeEditor = (window as any).tinymce?.activeEditor;
  if (activeEditor && optimizeResult.value) {
    activeEditor.selection.setContent(optimizeResult.value);
    editorContent.value = activeEditor.getContent();
    ElMessage.success('已采纳并替换选中文字');
    autoSave();
  }
}

function insertOptimizeResult() {
  const activeEditor = (window as any).tinymce?.activeEditor;
  if (activeEditor && optimizeResult.value) {
    activeEditor.execCommand('mceInsertContent', false, `<p>${optimizeResult.value}</p>`);
    editorContent.value = activeEditor.getContent();
    ElMessage.success('已将优化建议追加插入到光标位置');
    autoSave();
  }
}

// Apply layout templates
function applyFormatTemplate(template: any) {
  const activeEditor = (window as any).tinymce?.activeEditor;
  if (!activeEditor) return;

  // Let's format the editor DOM directly with standard structures
  const doc = activeEditor.getDoc();

  // Format Headings
  const headings = doc.querySelectorAll('h1, h2, h3');
  headings.forEach((h: HTMLElement) => {
    h.style.fontFamily = "'FZXiaoBiaoSong-B05S', sans-serif";
    h.style.textAlign = 'center';
    h.style.fontWeight = 'bold';
  });

  // Format Paragraphs
  const paragraphs = doc.querySelectorAll('p');
  paragraphs.forEach((p: HTMLElement) => {
    p.style.fontFamily = "'FangSong_GB2312', serif";
    p.style.fontSize = '16px';
    p.style.textIndent = '2em';
    p.style.lineHeight = '1.8';
  });

  editorContent.value = activeEditor.getContent();
  ElMessage.success(`成功应用「${template.name}」排版规范`);
  autoSave();
}

// Proofreading logic
async function runProofreading() {
  proofreading.value = true;
  proofreadFinished.value = false;
  corrections.value = [];

  setTimeout(() => {
    proofreading.value = false;
    proofreadFinished.value = true;

    // Seed 2 corrections
    corrections.value = [
      { word: '打同', correct: '打通', type: 'TYPO', desc: '字词错别字，建议修改为「打通」', targetRange: '打同数据壁垒' },
      { word: '机密泄漏', correct: '信息安全脱敏', type: 'SENSITIVE', desc: '政务安全敏感词，在公开发布文案中建议进行脱敏处理', targetRange: '防范机密泄漏' }
    ];
  }, 1500);
}

function getErrTypeName(type: string) {
  return type === 'TYPO' ? '错别字' : '涉密风险';
}

function acceptCorrection(item: any, idx: number) {
  const activeEditor = (window as any).tinymce?.activeEditor;
  if (activeEditor) {
    const html = activeEditor.getContent();
    const cleanHtml = html.replace(new RegExp(item.word, 'g'), item.correct);
    activeEditor.setContent(cleanHtml);
    editorContent.value = cleanHtml;

    ElMessage.success(`已自动采纳纠错：将「${item.word}」修正为「${item.correct}」`);
    corrections.value.splice(idx, 1);
    autoSave();
  }
}

function ignoreCorrection(idx: number) {
  corrections.value.splice(idx, 1);
}

// XiaoZhi Q&A Chat
function sendChatMessage() {
  if (!chatInputText.value.trim()) return;

  chatMessages.value.push({ role: 'user', content: chatInputText.value });
  const input = chatInputText.value;
  chatInputText.value = '';

  scrollToChatBottom();

  // Simulate assistant answer
  setTimeout(() => {
    let reply = '收到您的反馈。作为写作助手，我建议在党政公文中尽量多用动宾短语或对称排比。';
    if (input.includes('怎么') || input.includes('如何')) {
      reply = '撰写该部分时，建议从「强化认识」、「聚焦突破」、「兜底防护」三个维度分段陈述，结构层层递进，彰显执行力。';
    } else if (input.includes('格式')) {
      reply = '根据国家标准GB/T 9704-2012，公文正文推荐采用三号仿宋字，行距推荐固定值28pt，首行左缩进二字。';
    }
    chatMessages.value.push({ role: 'assistant', content: reply });
    scrollToChatBottom();
  }, 1000);
}

function scrollToChatBottom() {
  nextTick(() => {
    if (chatContainerRef.value) {
      chatContainerRef.value.scrollTop = chatContainerRef.value.scrollHeight;
    }
  });
}

// Download Tasks
async function handleExportCommand(command: string) {
  if (!docId.value) return;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/file/v1/createDownloadFileTask', {
      docId: docId.value,
      exportType: command
    });
    if (res && res.data && res.data.taskUuid) {
      ElMessage.success(`已提交 ${command.toUpperCase()} 排版转换任务，请耐心等候...`);
      pollExportStatus(res.data.taskUuid);
    }
  } catch (err) {
    console.error(err);
  }
}

async function pollExportStatus(taskUuid: string) {
  try {
    const res: any = await axios.post('/geekseek/aiwriter/file/v1/taskStatus', { taskUuid });
    if (res && res.data) {
      if (res.data.status === 'SUCCESS') {
        ElMessage.success('文稿生成完毕，正在拉起下载...');
        window.open(`/geekseek/aiwriter/file/v2/download?taskUuid=${taskUuid}`);
      } else if (res.data.status === 'FAILED') {
        ElMessage.error('转换失败');
      } else {
        setTimeout(() => pollExportStatus(taskUuid), 2000);
      }
    }
  } catch (err) {
    console.error(err);
  }
}
</script>

<style scoped>
.editor-page-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: #f5f7ff;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
}

/* Header style */
.editor-header {
  height: 60px;
  background-color: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.doc-title-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.doc-title-input {
  width: 260px;
}

.doc-title-input :deep(.el-input__inner) {
  font-weight: 700;
  font-size: 15px;
  color: #1e293b;
}

.save-status-indicator {
  font-size: 11px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-right {
  display: flex;
  gap: 12px;
}

/* Workspace Layout */
.workspace-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.editor-container {
  flex: 2;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  position: relative;
}

.editor-loading-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 16px;
  color: #64748b;
  font-size: 14px;
}

.editor-loading-box .el-icon {
  font-size: 36px;
  color: #5B6EF6;
}

/* AI Sidebar tabs */
.ai-sidebar {
  width: 380px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.sidebar-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}

.tab-pane-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
}

.tab-pane-content.scrollable {
  overflow-y: auto;
}

.tab-pane-content.flex-column-layout {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
  overflow: hidden;
}

.pane-heading h4 {
  margin: 0 0 6px 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
}

.pane-heading p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

/* Selected text划词 box */
.selected-text-box {
  background-color: #f8fafc;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.selected-text-box.has-selection {
  border-color: #5B6EF6;
  background-color: #f5f7ff;
}

.box-label {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 600;
}

.selection-preview {
  margin: 0;
  font-size: 12px;
  color: #475569;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.optimize-sub-tabs {
  margin-top: 10px;
}

.optimize-sub-tabs :deep(.el-tabs__item) {
  font-size: 12px;
  padding: 0 10px;
}

.optimize-action-area {
  display: flex;
}

.action-btn {
  width: 100%;
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
}

.action-btn:hover {
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.2);
}

/* Result panel styling */
.optimize-result-panel {
  background-color: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.optimize-result-panel h5 {
  margin: 0;
  font-size: 12px;
  color: #166534;
}

.result-text {
  font-size: 13px;
  color: #14532d;
  line-height: 1.6;
}

.result-actions {
  display: flex;
  gap: 8px;
}

/* Layout templates list */
.layout-template-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-card {
  border: 1px solid #e2e8f0;
  background-color: #ffffff;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  gap: 12px;
  cursor: pointer;
  transition: all 0.3s;
}

.template-card:hover {
  border-color: #5B6EF6;
  background-color: #f5f7ff;
  transform: translateX(2px);
}

.template-icon {
  font-size: 20px;
  color: #5B6EF6;
  background-color: rgba(91, 110, 246, 0.1);
  padding: 8px;
  border-radius: 6px;
}

.card-right h5 {
  margin: 0 0 4px 0;
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.card-right p {
  margin: 0;
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

/* Corrections styles */
.proofread-action-bar {
  display: flex;
}

.corrections-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  overflow: hidden;
}

.corrections-container h5 {
  margin: 0;
  font-size: 13px;
  color: #334155;
}

.corrections-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  flex: 1;
  padding-right: 6px;
}

.correction-card {
  border: 1px solid #fecaca;
  background-color: #fff5f5;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.err-badge {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.err-badge.typo {
  background-color: #fee2e2;
  color: #991b1b;
}

.err-badge.sensitive {
  background-color: #fef3c7;
  color: #92400e;
}

.card-mid p {
  margin: 2px 0;
  font-size: 12px;
}

.err-word {
  color: #ef4444;
  text-decoration: line-through;
  font-weight: 600;
}

.correct-word {
  color: #10b981;
  font-weight: 700;
  font-size: 13px;
}

.err-desc {
  font-size: 11px;
  color: #64748b;
  margin-top: 4px !important;
}

/* XiaoZhi chat bubble elements */
.chat-messages-container {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-right: 6px;
}

.chat-bubble {
  display: flex;
  gap: 10px;
  max-width: 85%;
}

.chat-bubble.assistant {
  align-self: flex-start;
}

.chat-bubble.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.avatar-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: #5B6EF6;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.chat-bubble.user .avatar-badge {
  background-color: #7b5cf7;
}

.bubble-content {
  background-color: #f1f5f9;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
}

.chat-bubble.user .bubble-content {
  background-color: #e0e7ff;
  color: #1e1b4b;
}

.chat-bubble p {
  margin: 0;
}

.chat-input-row {
  border-top: 1px solid #f1f5f9;
  padding-top: 12px;
}
</style>
