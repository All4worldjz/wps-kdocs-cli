<template>
  <div class="list-page-container">
    <!-- WIZARD WIDE VIEW (if writingMenu=true) -->
    <div v-if="isWizardMode" class="wizard-container">
      <div class="wizard-header">
        <el-button icon="ArrowLeft" text @click="exitWizard">返回创作中心</el-button>
        <span class="wizard-title">智能写作向导 — {{ getCategoryName(category) }}</span>
        <!-- Stepper -->
        <el-steps :active="wizardStep" finish-status="success" simple class="wizard-steps">
          <el-step title="1. 交代内容" />
          <el-step title="2. 选择参考" />
          <el-step title="3. 确定提纲" />
        </el-steps>
      </div>

      <div class="wizard-body card-panel">
        <!-- STEP 1: EXPLAIN -->
        <div v-if="wizardStep === 0" class="step-pane">
          <div class="pane-left">
            <h3 class="step-title">请向 AI 交代本次写作的具体要求与背景：</h3>
            <el-input
              v-model="explainText"
              type="textarea"
              :rows="12"
              placeholder="请输入起草要求。例如：请帮我撰写一篇在全省数字政府协同办公推进会议上的讲话稿。内容要强调数据打通、智能办文以及安全防护底线，篇幅约 3000 字，语气要坚定有力、高屋建瓴..."
              maxlength="2000"
              show-word-limit
              class="explain-textarea"
            />

            <div class="slider-wrapper">
              <span class="slider-label">期望篇幅 (字):</span>
              <el-slider
                v-model="targetWordCount"
                :min="500"
                :max="5000"
                :step="100"
                show-input
                class="length-slider"
              />
            </div>

            <div class="action-bar">
              <el-button
                type="primary"
                size="large"
                class="next-btn"
                :disabled="!explainText.trim()"
                @click="goToStep2"
              >
                下一步：配置参考资料
              </el-button>
            </div>
          </div>

          <div class="pane-right border-left">
            <div class="voice-assistant-card">
              <h4><el-icon><Microphone /></el-icon> 扫码语音交代</h4>
              <p class="voice-desc">如果觉得打字太慢，可微信扫码下方小程序，用语音把写作背景交代给小知助手，平台将自动转写填充。</p>
              <div class="qr-code-box" v-html="qrCodeSvg"></div>
              <span class="qr-tip">微信扫一扫 · 快捷交代</span>
            </div>
          </div>
        </div>

        <!-- STEP 2: REFERENCES -->
        <div v-if="wizardStep === 1" class="step-pane flex-column">
          <div class="step-section">
            <h3 class="step-title">
              智能匹配参考资料 & 文风模板
              <small class="step-subtitle">（参考越精准，AI 创作的专业度越高）</small>
            </h3>

            <!-- Reference Configuration Layout -->
            <div class="refer-config-row">
              <div class="style-select-box">
                <span class="section-sub-label">应用文风模板:</span>
                <el-select
                  v-model="selectedStyleId"
                  placeholder="选择已训练的专属文风库"
                  clearable
                  style="width: 280px;"
                >
                  <el-option
                    v-for="item in styleTemplates"
                    :key="item.id"
                    :label="item.title"
                    :value="item.id"
                  />
                </el-select>
              </div>

              <!-- Manual Reference search -->
              <div class="ref-search-box">
                <el-input
                  v-model="refSearchQuery"
                  placeholder="输入关键字检索相关参考文章..."
                  class="search-input"
                  clearable
                  @keyup.enter="performRefSearch"
                >
                  <template #append>
                    <el-button icon="Search" @click="performRefSearch" />
                  </template>
                </el-input>
              </div>
            </div>
          </div>

          <!-- Matching references cards grid -->
          <div class="reference-results-area">
            <h4 class="sub-heading">智能推荐参考文章 ({{ references.length }} 篇)：</h4>
            <div v-loading="loadingRefs" class="reference-grid">
              <div
                v-for="refItem in references"
                :key="refItem.id"
                class="reference-card"
                :class="{ active: selectedRefIds.includes(refItem.id) }"
                @click="toggleReference(refItem.id)"
              >
                <div class="ref-card-header">
                  <span class="ref-badge">{{ refItem.materialType === 'QIANGGUO_ARTICLE' ? '强国文章' : '个人资料' }}</span>
                  <el-checkbox :model-value="selectedRefIds.includes(refItem.id)" @click.stop="toggleReference(refItem.id)" />
                </div>
                <h5 class="ref-title">{{ refItem.title }}</h5>
                <p class="ref-preview">{{ refItem.contentPreview }}</p>
                <div class="ref-meta">
                  <span>字数: {{ refItem.wordCount }}</span>
                </div>
              </div>
            </div>

            <div v-if="references.length === 0 && !loadingRefs" class="empty-refs">
              <el-empty description="暂无匹配度高的参考素材，您可以直接生成提纲" :image-size="80" />
            </div>
          </div>

          <div class="action-bar flex-end">
            <el-button size="large" @click="wizardStep = 0">上一步</el-button>
            <el-button
              type="primary"
              size="large"
              class="next-btn"
              :loading="generatingOutline"
              @click="generateOutlineAndGoToStep3"
            >
              下一步：生成起草提纲
            </el-button>
          </div>
        </div>

        <!-- STEP 3: OUTLINE -->
        <div v-if="wizardStep === 2" class="step-pane flex-column">
          <div class="outline-pane-wrapper">
            <div class="outline-editor-area">
              <h3 class="step-title">AI 起草提纲：</h3>

              <div v-if="generatingOutline" class="outline-loading-box">
                <el-icon class="is-loading outline-loading-icon"><Loading /></el-icon>
                <p>小知正在为您深度构思提纲，请稍候...</p>
                <div class="outline-stream-preview" v-if="outlineStreamText">
                  <strong>正在生成标题:</strong> {{ outlineStreamText }}
                </div>
              </div>

              <div v-else class="outline-editor-body">
                <div class="title-input-row">
                  <span class="title-label">文稿标题:</span>
                  <el-input v-model="outlineTitle" class="doc-title-input" />
                </div>

                <div class="outline-nodes-list">
                  <div
                    v-for="(node, index) in outlineNodes"
                    :key="node.id"
                    class="outline-node-row"
                    :class="{ subnode: node.id.includes('.') }"
                  >
                    <el-icon class="drag-handle"><Rank /></el-icon>
                    <el-input v-model="node.title" class="node-input" />
                    <el-button
                      type="danger"
                      icon="Delete"
                      circle
                      size="small"
                      class="delete-node-btn"
                      @click="deleteOutlineNode(index)"
                    />
                  </div>
                </div>

                <div class="outline-actions-row">
                  <el-button type="primary" icon="Plus" plain size="small" @click="addOutlineNode">
                    添加提纲节点
                  </el-button>
                  <el-button type="success" icon="Refresh" plain size="small" @click="reGenerateOutline">
                    重新生成提纲
                  </el-button>
                </div>
              </div>
            </div>

            <!-- Outline Prompt Instructions Preview -->
            <div class="outline-summary-panel">
              <h4>创作概要</h4>
              <div class="summary-item">
                <strong>写作类型:</strong>
                <span>{{ getCategoryName(category) }}</span>
              </div>
              <div class="summary-item">
                <strong>预计篇幅:</strong>
                <span>{{ targetWordCount }} 字左右</span>
              </div>
              <div class="summary-item" v-if="selectedStyleId">
                <strong>专属文风:</strong>
                <span>已应用选定模板</span>
              </div>
              <div class="summary-item">
                <strong>关联参考数:</strong>
                <span>{{ selectedRefIds.length }} 篇</span>
              </div>

              <div class="summary-notice alert-box">
                <el-icon><InfoFilled /></el-icon>
                <span>点击下方「开始生成全文」后，系统将跳转至起草中心，AI 将基于以上提纲框架开始 SSE 实时流式撰写全文。</span>
              </div>
            </div>
          </div>

          <div class="action-bar flex-end border-top">
            <el-button size="large" :disabled="generatingOutline" @click="wizardStep = 1">上一步</el-button>
            <el-button
              type="primary"
              size="large"
              class="generate-all-btn"
              :disabled="generatingOutline || outlineNodes.length === 0"
              @click="startFullTextGeneration"
            >
              开始生成全文
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- STANDARD DOCUMENT LIST VIEW -->
    <div v-else class="list-container">
      <div class="list-header">
        <h2 class="page-title">创作中心</h2>
        <div class="header-filters">
          <el-input
            v-model="searchKeyword"
            placeholder="搜寻我创作的公文标题或内容..."
            prefix-icon="Search"
            clearable
            style="width: 280px;"
            @input="fetchDocuments"
          />
          <el-button type="primary" icon="Plus" class="add-btn" @click="layoutOpenCreateDialog">
            新建写作
          </el-button>
        </div>
      </div>

      <!-- Quick category filter tabs -->
      <div class="category-tabs">
        <span
          class="category-tab-item"
          :class="{ active: selectedCategoryTab === 'ALL' }"
          @click="changeCategoryTab('ALL')"
        >
          全部文稿
        </span>
        <span
          v-for="cat in genres"
          :key="cat.code"
          class="category-tab-item"
          :class="{ active: selectedCategoryTab === cat.code }"
          @click="changeCategoryTab(cat.code)"
        >
          {{ cat.name }}
        </span>
      </div>

      <!-- Document Cards Grid -->
      <div v-loading="loadingDocs" class="document-grid-viewport">
        <el-row :gutter="20">
          <el-col
            v-for="doc in documents"
            :key="doc.id"
            :xs="24" :sm="12" :md="8" :lg="6"
            class="card-col"
          >
            <div class="doc-card" @click="openDocument(doc.id)">
              <div class="doc-card-body">
                <div class="doc-meta-row">
                  <span class="genre-tag" :class="doc.category.toLowerCase()">
                    {{ getCategoryName(doc.category) }}
                  </span>
                  <span class="word-count">{{ doc.wordCount }} 字</span>
                </div>

                <h4 class="doc-title">{{ doc.title }}</h4>
                <p class="doc-excerpt">{{ doc.contentText }}</p>
              </div>

              <!-- Hover Actions Footer -->
              <div class="doc-card-footer" @click.stop>
                <div class="footer-time">
                  {{ formatTime(doc.updatedAt) }}
                </div>
                <div class="footer-actions">
                  <el-tooltip content="加入知识管理" placement="top">
                    <el-button
                      :type="doc.isImportedKnowledge ? 'success' : 'default'"
                      icon="Star"
                      circle
                      size="small"
                      @click="toggleKnowledge(doc)"
                    />
                  </el-tooltip>

                  <el-tooltip content="重命名" placement="top">
                    <el-button icon="Edit" circle size="small" @click="renameDoc(doc)" />
                  </el-tooltip>

                  <el-tooltip content="导出为 Word" placement="top">
                    <el-button icon="Download" circle size="small" @click="exportDocWord(doc.id)" />
                  </el-tooltip>

                  <el-tooltip content="移至回收站" placement="top">
                    <el-button type="danger" icon="Delete" circle size="small" @click="recycleDoc(doc.id)" />
                  </el-tooltip>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>

        <div v-if="documents.length === 0 && !loadingDocs" class="empty-docs">
          <el-empty description="暂无符合条件的文稿，点击上方「新建写作」即刻开启智能创作！" :image-size="120" />
        </div>
      </div>

      <!-- Pagination -->
      <div class="pagination-area" v-if="totalDocs > 0">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[12, 24, 48]"
          background
          layout="total, sizes, prev, pager, next"
          :total="totalDocs"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from '../utils/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

const route = useRoute();
const router = useRouter();

// ================== GENERAL STATE ==================
const genres = [
  { code: 'SPEECH', name: '讲话稿' },
  { code: 'REFLECTION', name: '心得体会' },
  { code: 'WORK_REPORT', name: '工作报告' },
  { code: 'RESEARCH_REPORT', name: '调研报告' },
  { code: 'NOTICE', name: '通知' },
  { code: 'THANK_YOU_LETTER', name: '感谢信' }
];

// Check if Wizard layout is active
const isWizardMode = computed(() => route.query.writingMenu === 'true');
const category = computed(() => (route.query.category as string) || 'SPEECH');

// ================== STANDARD LIST VIEW STATE ==================
const documents = ref<any[]>([]);
const searchKeyword = ref('');
const selectedCategoryTab = ref('ALL');
const loadingDocs = ref(false);
const totalDocs = ref(0);
const currentPage = ref(1);
const pageSize = ref(12);

// ================== WIZARD STATE ==================
const wizardStep = ref(0);
const explainText = ref('');
const targetWordCount = ref(3000);
const qrCodeSvg = ref('');
const selectedStyleId = ref('');
const styleTemplates = ref<any[]>([]);
const loadingRefs = ref(false);
const references = ref<any[]>([]);
const selectedRefIds = ref<string[]>([]);
const refSearchQuery = ref('');
const generatingOutline = ref(false);
const outlineStreamText = ref('');
const outlineTitle = ref('');
const outlineNodes = ref<any[]>([]);

onMounted(() => {
  if (!isWizardMode.value) {
    fetchDocuments();
  } else {
    initializeWizard();
  }
});

// Watch route changes to load wizard vs list dynamically
watch(() => route.query, (newQ) => {
  if (newQ.writingMenu === 'true') {
    initializeWizard();
  } else {
    fetchDocuments();
  }
});

// ================== LIST LOGIC ==================
async function fetchDocuments() {
  loadingDocs.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/document/v1/list', {
      page: currentPage.value,
      pageSize: pageSize.value,
      searchKeyword: searchKeyword.value,
      isRecycled: false
    });

    if (res && res.data) {
      let list = res.data.list || [];
      if (selectedCategoryTab.value !== 'ALL') {
        list = list.filter((d: any) => d.category === selectedCategoryTab.value);
      }
      documents.value = list;
      totalDocs.value = res.data.total || 0;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingDocs.value = false;
  }
}

function changeCategoryTab(tab: string) {
  selectedCategoryTab.value = tab;
  currentPage.value = 1;
  fetchDocuments();
}

function getCategoryName(code: string) {
  const g = genres.find(item => item.code === code);
  return g ? g.name : '自由起草';
}

function openDocument(docId: string) {
  router.push(`/writer/content/edit/${docId}`);
}

async function toggleKnowledge(doc: any) {
  const url = doc.isImportedKnowledge
    ? '/geekseek/aiwriter/document/v1/cancelAddDocToKnowledge'
    : '/geekseek/aiwriter/document/v1/addDocToKnowledge';

  try {
    await axios.post(url, { docId: doc.id });
    ElMessage.success(doc.isImportedKnowledge ? '取消知识管理成功' : '成功加入知识管理');
    fetchDocuments();
  } catch (err) {
    console.error(err);
  }
}

function renameDoc(doc: any) {
  ElMessageBox.prompt('请输入新的文稿名称：', '文稿重命名', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputValue: doc.title,
    inputPattern: /\S+/,
    inputErrorMessage: '文稿名称不能为空'
  }).then(async ({ value }) => {
    try {
      await axios.post('/geekseek/aiwriter/document/v1/addOrUpdate', {
        id: doc.id,
        title: value
      });
      ElMessage.success('命名成功');
      fetchDocuments();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

async function exportDocWord(docId: string) {
  try {
    const res: any = await axios.post('/geekseek/aiwriter/file/v1/createDownloadFileTask', {
      docId,
      exportType: 'docx'
    });
    if (res && res.data && res.data.taskUuid) {
      ElMessage.success('已提交 Word 转换导出任务');
      // Begin standard status polling
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
        ElMessage.success('Word 导出完成，正在下载文件...');
        // Download document blob
        window.open(`/geekseek/aiwriter/file/v2/download?taskUuid=${taskUuid}`);
      } else if (res.data.status === 'FAILED') {
        ElMessage.error('导出失败，请重试');
      } else {
        // Retry
        setTimeout(() => pollExportStatus(taskUuid), 2000);
      }
    }
  } catch (err) {
    console.error(err);
  }
}

async function recycleDoc(docId: string) {
  try {
    await ElMessageBox.confirm('确定要将该文稿移入回收站吗？您可以在回收站随时恢复。', '移至回收站', {
      confirmButtonText: '移至回收站',
      cancelButtonText: '取消',
      type: 'warning'
    });

    await axios.post('/geekseek/aiwriter/document/v1/recycle', {
      ids: [docId],
      action: 'delete'
    });
    ElMessage.success('成功移入回收站');
    fetchDocuments();
  } catch (err) {
    console.error(err);
  }
}

function handleSizeChange(val: number) {
  pageSize.value = val;
  fetchDocuments();
}

function handleCurrentChange(val: number) {
  currentPage.value = val;
  fetchDocuments();
}

function formatTime(isoStr: string) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// Emits create dialog visible from Layout
function layoutOpenCreateDialog() {
  const customEvent = new CustomEvent('open-layout-create-dialog');
  // Dispatch global custom event for layout to capture
  window.dispatchEvent(customEvent);
}

// ================== WIZARD LOGIC ==================
function initializeWizard() {
  wizardStep.value = 0;
  explainText.value = '';
  selectedRefIds.value = [];
  outlineNodes.value = [];
  outlineTitle.value = '';

  if (category.value === 'SPEECH') {
    targetWordCount.value = 3000;
  } else {
    targetWordCount.value = 1500;
  }

  // Load Explain Voice QR
  axios.post('/geekseek/aiwriter/article/v1/generateExplainQrCode').then((res: any) => {
    if (res && res.data) {
      qrCodeSvg.value = res.data.qrCodeUrl;
    }
  });

  // Load Style Template downlist
  axios.post('/geekseek/aiwriter/writingStyle/v1/downList').then((res: any) => {
    if (res && res.data) {
      styleTemplates.value = res.data;
    }
  });

  // Load default references
  loadReferences();
}

async function loadReferences() {
  loadingRefs.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/document/v2/semanticSearch', {
      query: refSearchQuery.value,
      limit: 6
    });
    if (res && res.data) {
      references.value = res.data;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingRefs.value = false;
  }
}

function performRefSearch() {
  loadReferences();
}

function toggleReference(id: string) {
  const index = selectedRefIds.value.indexOf(id);
  if (index === -1) {
    selectedRefIds.value.push(id);
  } else {
    selectedRefIds.value.splice(index, 1);
  }
}

function goToStep2() {
  // Check sensitive word on explain first
  axios.post('/geekseek/aiwriter/article/v1/checkSensitiveWord', { text: explainText.value }).then((res: any) => {
    if (res && res.data && res.data.length > 0) {
      ElMessageBox.alert(
        `交代内容包含敏感词: "${res.data[0].word}" (${res.data[0].advice})，请修正后再进入下一步。`,
        '敏感词检测警告',
        { type: 'warning' }
      );
    } else {
      wizardStep.value = 1;
    }
  });
}

function exitWizard() {
  router.push('/writer/document-list');
}

async function generateOutlineAndGoToStep3() {
  wizardStep.value = 2;
  generatingOutline.value = true;
  outlineStreamText.value = '';

  try {
    // Call outline stream generator via custom chunk simulator
    const response = await fetch('/geekseek/aiwriter/article/v1/outlineOrTitle/generateStream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Geekseek-Authorization': localStorage.getItem('GEEKSEEK_USER_TOKEN') || 'mock_token_xiaochun_2026'
      },
      body: JSON.stringify({
        category: category.value,
        explain: explainText.value,
        references: selectedRefIds.value
      })
    });

    if (!response.body) return;
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
            generatingOutline.value = false;
            break;
          }
          outlineStreamText.value += rawData;
        }
      }
    }

    // Try parsing generated structure
    if (outlineStreamText.value) {
      try {
        const payload = JSON.parse(outlineStreamText.value);
        outlineTitle.value = payload.title || '新创作公文';
        outlineNodes.value = payload.nodes || [];
      } catch (err) {
        console.error('Failed to parse outlines JSON stream:', err);
        outlineTitle.value = '数字化转型推进讲话稿';
        outlineNodes.value = [
          { id: '1', title: '一、深化认识，筑牢全局思维' },
          { id: '2', title: '二、聚焦突破，打通协同壁垒' },
          { id: '3', title: '三、抓细抓实，提供坚实组织保障' }
        ];
        generatingOutline.value = false;
      }
    }

  } catch (err) {
    console.error(err);
    generatingOutline.value = false;
  }
}

function reGenerateOutline() {
  generateOutlineAndGoToStep3();
}

function deleteOutlineNode(idx: number) {
  outlineNodes.value.splice(idx, 1);
}

function addOutlineNode() {
  const nextId = String(outlineNodes.value.length + 1);
  outlineNodes.value.push({
    id: nextId,
    title: `新提纲节点 ${nextId}`
  });
}

// Step 3 to Final SSE Drafting Chat trigger
async function startFullTextGeneration() {
  try {
    // 1. Create standard document item in database first
    const res: any = await axios.post('/geekseek/aiwriter/document/v1/addOrUpdate', {
      title: outlineTitle.value,
      category: category.value,
      contentText: 'AI 起草中...',
      contentHtml: '<p>AI 起草中，请保持连接...</p>',
      wordCount: 0
    });

    if (res && res.data && res.data.id) {
      const newDocId = res.data.id;
      // 2. Redirects to `/writer/content/chat/:docId` to trigger full SSE streaming
      router.push({
        path: `/writer/content/chat/${newDocId}`,
        query: {
          category: category.value,
          title: outlineTitle.value,
          explain: explainText.value,
          outline: JSON.stringify(outlineNodes.value)
        }
      });
    }
  } catch (err) {
    console.error(err);
  }
}
</script>

<style scoped>
.list-page-container {
  min-height: 100%;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
}

/* WIZARD CONTAINER AND HEADERS */
.wizard-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.wizard-header {
  background-color: #ffffff;
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.wizard-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.wizard-steps {
  width: 500px;
  background-color: transparent !important;
  padding: 0 !important;
}

.wizard-body {
  padding: 24px;
}

.step-pane {
  display: flex;
  gap: 30px;
}

.step-pane.flex-column {
  flex-direction: column;
  gap: 20px;
}

.pane-left {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.pane-right {
  flex: 1;
  padding-left: 30px;
}

.border-left {
  border-left: 1px solid #e2e8f0;
}

.step-title {
  margin: 0;
  font-size: 16px;
  color: #1e293b;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-subtitle {
  font-size: 12px;
  color: #64748b;
  font-weight: normal;
}

.explain-textarea :deep(.el-textarea__inner) {
  border-radius: 8px;
  padding: 14px;
  font-size: 14px;
  line-height: 1.6;
}

.slider-wrapper {
  background-color: #f8fafc;
  padding: 14px 20px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  display: flex;
  align-items: center;
  gap: 20px;
}

.slider-label {
  font-size: 13px;
  color: #475569;
  font-weight: 600;
  width: 100px;
}

.length-slider {
  flex: 1;
}

.action-bar {
  display: flex;
  padding-top: 10px;
}

.action-bar.flex-end {
  justify-content: flex-end;
  gap: 12px;
}

.action-bar.border-top {
  border-top: 1px solid #e2e8f0;
  padding-top: 20px;
}

.next-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.2);
}

.next-btn:hover {
  box-shadow: 0 6px 16px rgba(91, 110, 246, 0.3);
}

/* Voice Qr Card */
.voice-assistant-card {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.voice-assistant-card h4 {
  margin: 0;
  font-size: 15px;
  color: #1e293b;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}

.voice-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}

.qr-code-box {
  width: 140px;
  height: 140px;
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
}

.qr-tip {
  font-size: 11px;
  color: #94a3b8;
}

/* Step 2 Refer Layout */
.refer-config-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  background-color: #f8fafc;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
}

.style-select-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-sub-label {
  font-size: 13px;
  font-weight: 600;
  color: #475569;
}

.ref-search-box {
  width: 320px;
}

.sub-heading {
  margin: 0 0 12px 0;
  font-size: 14px;
  color: #334155;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.reference-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.3s;
  background-color: #ffffff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reference-card:hover {
  border-color: #5B6EF6;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.05);
}

.reference-card.active {
  border-color: #5B6EF6;
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.01) 0%, rgba(123, 92, 247, 0.01) 100%);
  box-shadow: 0 4px 15px rgba(91, 110, 246, 0.08);
}

.ref-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.ref-badge {
  font-size: 10px;
  background-color: #eff6ff;
  color: #2563eb;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
}

.ref-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref-preview {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.ref-meta {
  font-size: 11px;
  color: #94a3b8;
}

/* Step 3 Outline layout */
.outline-pane-wrapper {
  display: flex;
  gap: 30px;
}

.outline-editor-area {
  flex: 2;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.outline-summary-panel {
  flex: 1;
  background-color: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.outline-summary-panel h4 {
  margin: 0 0 10px 0;
  font-size: 15px;
  color: #1e293b;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 8px;
}

.summary-item {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}

.summary-item strong {
  color: #64748b;
}

.summary-item span {
  color: #1e293b;
  font-weight: 600;
}

.alert-box {
  background-color: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.outline-loading-box {
  text-align: center;
  padding: 50px 0;
}

.outline-loading-icon {
  font-size: 32px;
  color: #5B6EF6;
  margin-bottom: 14px;
}

.outline-stream-preview {
  margin-top: 20px;
  background-color: #f1f5f9;
  padding: 12px;
  border-radius: 8px;
  font-size: 13px;
  color: #475569;
}

.title-input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: #f8fafc;
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
}

.title-label {
  font-size: 14px;
  font-weight: 700;
  color: #334155;
  width: 80px;
}

.doc-title-input {
  flex: 1;
}

.outline-nodes-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 350px;
  overflow-y: auto;
  padding-right: 10px;
}

.outline-node-row {
  display: flex;
  align-items: center;
  gap: 10px;
  background-color: #ffffff;
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.outline-node-row.subnode {
  margin-left: 24px;
  background-color: #fcfdff;
  border-color: #e2e8f0;
}

.drag-handle {
  color: #94a3b8;
  cursor: grab;
}

.node-input :deep(.el-input__inner) {
  font-weight: 500;
}

.outline-actions-row {
  display: flex;
  gap: 12px;
}

.generate-all-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.2);
}

.generate-all-btn:hover {
  box-shadow: 0 6px 18px rgba(91, 110, 246, 0.3);
}

/* ================== STANDARD LIST VIEW STYLES ================== */
.list-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.header-filters {
  display: flex;
  gap: 12px;
}

.add-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
}

.category-tabs {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 6px;
  border-bottom: 1px solid #e2e8f0;
}

.category-tab-item {
  font-size: 13px;
  padding: 6px 14px;
  border-radius: 20px;
  cursor: pointer;
  color: #64748b;
  font-weight: 500;
  transition: all 0.3s;
  white-space: nowrap;
}

.category-tab-item:hover {
  color: #5B6EF6;
  background-color: #f1f5f9;
}

.category-tab-item.active {
  background-color: #5B6EF6;
  color: #ffffff;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.15);
}

.document-grid-viewport {
  min-height: 300px;
}

.card-col {
  margin-bottom: 20px;
}

/* Stunning Doc Card Aligned with gai.cn styles */
.doc-card {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  height: 190px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.01);
}

.doc-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 20px rgba(91, 110, 246, 0.08);
  border-color: #5B6EF6;
}

.doc-card-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.genre-tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.genre-tag.speech { background-color: #eff6ff; color: #1d4ed8; }
.genre-tag.reflection { background-color: #faf5ff; color: #7e22ce; }
.genre-tag.work_report { background-color: #ecfdf5; color: #047857; }
.genre-tag.notice { background-color: #fff7ed; color: #c2410c; }
.genre-tag.free_writing { background-color: #f1f5f9; color: #475569; }

.word-count {
  font-size: 11px;
  color: #94a3b8;
}

.doc-title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.doc-excerpt {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Card hover actions footer */
.doc-card-footer {
  border-top: 1px solid #f1f5f9;
  padding: 10px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #fafbfd;
  height: 40px;
}

.footer-time {
  font-size: 11px;
  color: #94a3b8;
}

.footer-actions {
  display: none;
  gap: 6px;
}

.doc-card:hover .footer-actions {
  display: flex;
}

.doc-card:hover .footer-time {
  display: none;
}

.pagination-area {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

.empty-docs {
  padding: 60px 0;
}
</style>
