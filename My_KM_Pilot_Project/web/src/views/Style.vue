<template>
  <div class="style-container">
    <div class="style-header-row">
      <h2 class="page-title">文风模板</h2>
      <div class="header-actions">
        <el-input
          v-model="searchKeyword"
          placeholder="搜寻我训练的专属文风库..."
          prefix-icon="Search"
          clearable
          style="width: 280px; margin-right: 12px;"
          @input="fetchStyles"
        />
        <el-button
          type="primary"
          icon="Plus"
          class="create-style-btn"
          @click="openCreateStyleModal"
        >
          训练新文风
        </el-button>
      </div>
    </div>

    <!-- Styles Grid -->
    <div class="styles-viewport" v-loading="loadingStyles">
      <el-row :gutter="20" v-if="styles.length > 0">
        <el-col
          v-for="style in styles"
          :key="style.id"
          :xs="24" :sm="12" :md="8" :lg="6"
          class="card-col"
        >
          <div class="style-card" @click="viewStyleDetails(style)">
            <div class="card-body">
              <div class="card-status-row">
                <el-tag :type="style.status === 'READY' ? 'success' : 'warning'" size="small">
                  {{ style.status === 'READY' ? '就绪' : '训练中' }}
                </el-tag>
                <span class="materials-count">{{ style.materialCount }} 篇参考资料</span>
              </div>

              <h3 class="style-title">{{ style.title }}</h3>

              <!-- Progress Indicator if training -->
              <div class="training-progress-box" v-if="style.status === 'TRAINING'">
                <span class="progress-txt">大模型深度解析与文风抽象中... {{ style.progress }}%</span>
                <el-progress :percentage="style.progress" :stroke-width="6" color="#7B5CF7" />
              </div>

              <!-- Static Word Cloud Canvas miniature when ready -->
              <div class="wordcloud-mini-preview" v-else>
                <el-icon class="cloud-preview-icon"><MagicStick /></el-icon>
                <span class="preview-txt">点击查看专属文体词云 & 文风分析</span>
              </div>
            </div>

            <!-- Actions footer -->
            <div class="card-footer" @click.stop>
              <span class="created-at">{{ formatTime(style.createdAt) }}</span>
              <div class="footer-actions">
                <el-tooltip content="编辑文风" placement="top" v-if="style.status === 'READY'">
                  <el-button icon="Edit" circle size="small" @click="openEditStyleModal(style)" />
                </el-tooltip>
                <el-tooltip content="删除文风" placement="top">
                  <el-button type="danger" icon="Delete" circle size="small" @click="deleteStyleConfirm(style.id)" />
                </el-tooltip>
              </div>
            </div>
          </div>
        </el-col>
      </el-row>

      <div v-else class="empty-placeholder">
        <el-empty description="当前暂无训练的专属文体。点击「训练新文风」上传您的专属范文以训练文风！" :image-size="120" />
      </div>
    </div>

    <!-- Style Builder Modal (Create/Edit Wizard) -->
    <el-dialog
      v-model="builderVisible"
      :title="editingStyleId ? '编辑专属文风' : '训练专属 AI 文风库'"
      width="780px"
      align-center
      destroy-on-close
    >
      <div class="builder-wizard-container">
        <!-- Steps indicator -->
        <el-steps :active="builderStep" finish-status="success" simple class="builder-steps">
          <el-step title="1. 设定命名" />
          <el-step title="2. 选择范文" />
          <el-step title="3. 训练排队" />
        </el-steps>

        <div class="builder-pane">
          <!-- STEP 1: Name and Title -->
          <div v-if="builderStep === 0" class="step-pane">
            <h4 class="step-pane-title">为您的文风模板命名：</h4>
            <p class="pane-desc">建议按使用场景或作者名称命名，例如：【政策研究室领导讲话风格】、【数字化科室常规通知风】等。</p>
            <el-input
              v-model="builderTitle"
              placeholder="请输入专属文风库命名..."
              maxlength="30"
              show-word-limit
              class="style-name-input"
            />

            <div class="step-actions flex-end">
              <el-button type="primary" :disabled="!builderTitle.trim()" @click="goToStep2">下一步：配置范文</el-button>
            </div>
          </div>

          <!-- STEP 2: Select Materials -->
          <div v-if="builderStep === 1" class="step-pane">
            <h4 class="step-pane-title">选择要分析提炼的参考范文 (可选 1~10 篇)：</h4>
            <p class="pane-desc">AI 将从选定的历史范文中深度提炼其独有的修辞句式、行文大纲、段落过渡以及特有的字词频率规律。</p>

            <!-- Materials multi-selection list -->
            <div class="materials-picker-box" v-loading="loadingMats">
              <div
                v-for="mat in availableMaterials"
                :key="mat.id"
                class="mat-picker-item"
                :class="{ selected: selectedMatIds.includes(mat.id) }"
                @click="toggleSelectMaterial(mat.id)"
              >
                <el-checkbox :model-value="selectedMatIds.includes(mat.id)" @click.stop="toggleSelectMaterial(mat.id)" />
                <div class="mat-details">
                  <span class="mat-title">{{ mat.title }}</span>
                  <span class="mat-desc">{{ mat.wordCount }} 字 · {{ mat.source }}</span>
                </div>
              </div>
              <div v-if="availableMaterials.length === 0" class="empty-mats">
                <el-empty description="暂无素材，请先在素材文稿中上传范文" :image-size="60" />
              </div>
            </div>

            <div class="step-actions flex-between" style="margin-top: 18px;">
              <el-button @click="builderStep = 0">上一步</el-button>
              <el-button type="primary" :disabled="selectedMatIds.length === 0" @click="submitTraining">
                开始特征训练 (TDD 模式)
              </el-button>
            </div>
          </div>

          <!-- STEP 3: Training & Progress -->
          <div v-if="builderStep === 2" class="step-pane text-center">
            <div class="training-loader-box">
              <el-icon class="is-loading loader-icon"><Loading /></el-icon>
              <h3 class="training-status-title">专属文体分析建模中...</h3>
              <p class="training-desc">大模型正在对所选范文的词法大纲与逻辑树进行语义级归纳，预计需要 5~10 秒。</p>

              <div class="progress-bar-wrapper">
                <el-progress :percentage="trainingProgress" status="success" :stroke-width="10" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>

    <!-- Style Detailed Analytics Dialog (Word Cloud & Details) -->
    <el-dialog
      v-model="detailsVisible"
      :title="selectedStyleDetail?.title"
      width="680px"
      align-center
    >
      <div class="details-body" v-if="selectedStyleDetail">
        <el-row :gutter="20">
          <el-col :span="12">
            <h4 class="analytics-title"><el-icon><MagicStick /></el-icon> 专属文体词云分析</h4>
            <!-- HTML5 Word Cloud Canvas -->
            <div class="canvas-container">
              <canvas id="wordCloudCanvas" class="wordcloud-canvas"></canvas>
            </div>
          </el-col>

          <el-col :span="12" class="style-desc-col">
            <h4 class="analytics-title"><el-icon><Document /></el-icon> 文风特质提炼</h4>
            <div class="style-prompt-card">
              <p class="style-prompt-txt">{{ selectedStyleDetail.stylePrompt || '暂无提炼' }}</p>
            </div>

            <div class="style-summary-details">
              <div class="summary-row">
                <span>训练数据源:</span>
                <strong>{{ selectedStyleDetail.materialCount }} 篇标准文稿</strong>
              </div>
              <div class="summary-row">
                <span>训练完成时间:</span>
                <strong>{{ formatTime(selectedStyleDetail.createdAt) }}</strong>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="detailsVisible = false">关闭分析</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue';
import axios from '../utils/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

// State
const searchKeyword = ref('');
const styles = ref<any[]>([]);
const loadingStyles = ref(false);

// Builder wizard state
const builderVisible = ref(false);
const builderStep = ref(0);
const builderTitle = ref('');
const editingStyleId = ref<string | null>(null);

const availableMaterials = ref<any[]>([]);
const selectedMatIds = ref<string[]>([]);
const loadingMats = ref(false);

const trainingProgress = ref(0);
const trainedStyleId = ref('');

// Details state
const detailsVisible = ref(false);
const selectedStyleDetail = ref<any>(null);

onMounted(() => {
  fetchStyles();
});

// APIs
async function fetchStyles() {
  loadingStyles.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/writingStyle/v1/pageList', {
      page: 1,
      pageSize: 24,
      searchKeyword: searchKeyword.value
    });
    if (res && res.data) {
      styles.value = res.data.list || [];
      // Proactively poll status of any currently training items
      styles.value.forEach(style => {
        if (style.status === 'TRAINING') {
          pollTrainingStatus(style.id);
        }
      });
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingStyles.value = false;
  }
}

// Poll Training Progress
async function pollTrainingStatus(styleId: string) {
  try {
    const res: any = await axios.post('/geekseek/aiwriter/writingStyle/v1/query', { id: styleId });
    if (res && res.data) {
      const updatedStyle = res.data;

      // Update local array item
      const found = styles.value.find(s => s.id === styleId);
      if (found) {
        found.progress = updatedStyle.progress;
        found.status = updatedStyle.status;

        if (updatedStyle.status === 'READY') {
          ElMessage.success(`专属文风「${found.title}」建模完成！词云及特征已就绪。`);
          fetchStyles();
          return;
        }
      }

      // If still training and modal is active for this training process
      if (builderVisible.value && builderStep.value === 2 && trainedStyleId.value === styleId) {
        trainingProgress.value = updatedStyle.progress;
        if (updatedStyle.status === 'READY') {
          setTimeout(() => {
            builderVisible.value = false;
            fetchStyles();
          }, 800);
          return;
        }
      }

      // Keep polling
      if (updatedStyle.status === 'TRAINING') {
        setTimeout(() => pollTrainingStatus(styleId), 2000);
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// Modal open
function openCreateStyleModal() {
  builderTitle.value = '';
  selectedMatIds.value = [];
  editingStyleId.value = null;
  builderStep.value = 0;
  builderVisible.value = true;
}

function openEditStyleModal(style: any) {
  builderTitle.value = style.title;
  selectedMatIds.value = [...(style.materialIds || [])];
  editingStyleId.value = style.id;
  builderStep.value = 0;
  builderVisible.value = true;
}

async function goToStep2() {
  builderStep.value = 1;
  loadingMats.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/document/v2/list', {
      page: 1,
      pageSize: 40,
      channel: 'PERSONAL_MATERIAL'
    });
    if (res && res.data) {
      availableMaterials.value = res.data.list || [];
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingMats.value = false;
  }
}

function toggleSelectMaterial(id: string) {
  const index = selectedMatIds.value.indexOf(id);
  if (index === -1) {
    if (selectedMatIds.value.length >= 10) {
      ElMessage.warning('最多只能选取 10 篇范文进行文风提取！');
      return;
    }
    selectedMatIds.value.push(id);
  } else {
    selectedMatIds.value.splice(index, 1);
  }
}

// Submit style training
async function submitTraining() {
  try {
    if (editingStyleId.value) {
      // Edit
      const res: any = await axios.post('/geekseek/aiwriter/writingStyle/v1/update', {
        id: editingStyleId.value,
        title: builderTitle.value,
        materialIds: selectedMatIds.value
      });
      if (res && res.data) {
        ElMessage.success('文风修改提交成功，正在重新提取！');
        builderVisible.value = false;
        fetchStyles();
      }
    } else {
      // Create
      const res: any = await axios.post('/geekseek/aiwriter/writingStyle/v1/add', {
        title: builderTitle.value,
        materialIds: selectedMatIds.value
      });
      if (res && res.data && res.data.id) {
        trainedStyleId.value = res.data.id;
        trainingProgress.value = 0;
        builderStep.value = 2;
        // Start polling
        pollTrainingStatus(res.data.id);
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// Delete style
function deleteStyleConfirm(id: string) {
  ElMessageBox.confirm('确定要删除该文风模板吗？删除后在起草向导中将无法继续引用。', '删除文风模板', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await axios.post('/geekseek/aiwriter/writingStyle/v1/delete', { id });
      ElMessage.success('文风模板成功删除');
      fetchStyles();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// View details and render Canvas Word Cloud
async function viewStyleDetails(style: any) {
  if (style.status !== 'READY') return;

  loadingStyles.value = true;
  try {
    const res: any = await axios.get(`/geekseek/aiwriter/writingStyle/v1/detail?styleId=${style.id}`);
    if (res && res.data) {
      selectedStyleDetail.value = res.data;
      detailsVisible.value = true;

      // Draw Word Cloud nextTick
      nextTick(() => {
        setTimeout(() => {
          renderWordCloudCanvas(res.data.wordCloud || []);
        }, 100);
      });
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingStyles.value = false;
  }
}

// Custom interactive Canvas Word Cloud renderer
function renderWordCloudCanvas(words: any[]) {
  const canvas = document.getElementById('wordCloudCanvas') as HTMLCanvasElement;
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // Adapt to high DPI
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * 2;
  canvas.height = rect.height * 2;
  ctx.scale(2, 2);

  // Clear Canvas
  ctx.clearRect(0, 0, rect.width, rect.height);

  const colors = ['#5B6EF6', '#7B5CF7', '#4B6EE3', '#6366f1', '#a855f7', '#6366f1', '#4f46e5', '#8b5cf6'];

  // Mock layout algorithm for words
  words.forEach((item, index) => {
    const wordText = item.word || item.text || '文公';
    const weight = item.weight || item.value || 15;

    // Scale font size proportionally
    const fontSize = Math.max(12, Math.min(34, Math.round(weight / 2.5) + 12));
    ctx.font = `bold ${fontSize}px "Outfit", "PingFang SC", sans-serif`;
    ctx.fillStyle = colors[index % colors.length];

    // Determine random but distributed positions
    let x, y;
    if (index === 0) {
      x = rect.width / 2;
      y = rect.height / 2;
    } else {
      const angle = (index * 45 * Math.PI) / 180 + (Math.random() - 0.5) * 0.2;
      const radius = (index * 15) + 10;
      x = rect.width / 2 + Math.cos(angle) * radius;
      y = rect.height / 2 + Math.sin(angle) * radius;
    }

    // Keep words fully bounded inside canvas
    x = Math.max(50, Math.min(rect.width - 50, x));
    y = Math.max(30, Math.min(rect.height - 30, y));

    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    ctx.save();
    ctx.translate(x, y);
    // 15% probability of drawing vertically
    if (Math.random() < 0.15 && index !== 0) {
      ctx.rotate(Math.PI / 2);
    }
    ctx.fillText(wordText, 0, 0);
    ctx.restore();
  });
}

function formatTime(isoStr: string) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
</script>

<style scoped>
.style-container {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.style-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #ffffff;
  padding: 16px 24px;
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.02);
  border: 1px solid #e2e8f0;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.header-actions {
  display: flex;
  align-items: center;
}

.create-style-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.15);
}

.styles-viewport {
  flex: 1;
}

.style-card {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  height: 220px;
  cursor: pointer;
  transition: all 0.3s ease;
  overflow: hidden;
  margin-bottom: 20px;
}

.style-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(123, 92, 247, 0.08);
  border-color: #7B5CF7;
}

.card-body {
  padding: 18px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-status-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.materials-count {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
}

.style-title {
  margin: 0 0 16px 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.style-card:hover .style-title {
  color: #7B5CF7;
}

.training-progress-box {
  background-color: rgba(123, 92, 247, 0.03);
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid rgba(123, 92, 247, 0.1);
  margin-top: auto;
}

.progress-txt {
  display: block;
  font-size: 10px;
  color: #7B5CF7;
  font-weight: 600;
  margin-bottom: 6px;
}

.wordcloud-mini-preview {
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: #f8fafc;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #f1f5f9;
  color: #64748b;
}

.cloud-preview-icon {
  font-size: 18px;
  color: #7B5CF7;
}

.preview-txt {
  font-size: 11px;
  font-weight: 500;
}

.card-footer {
  padding: 10px 18px;
  background-color: #f8fafc;
  border-top: 1px solid #f1f5f9;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.created-at {
  font-size: 11px;
  color: #94a3b8;
}

.footer-actions {
  display: flex;
  gap: 6px;
}

.empty-placeholder {
  background-color: #ffffff;
  padding: 60px 0;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

/* Wizard Builder */
.builder-steps {
  margin-bottom: 24px;
}

.builder-pane {
  padding: 10px 0;
}

.step-pane-title {
  margin: 0 0 6px 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
}

.pane-desc {
  font-size: 12px;
  color: #64748b;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.style-name-input {
  width: 100%;
}

.materials-picker-box {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  max-height: 240px;
  overflow-y: auto;
}

.mat-picker-item {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #f1f5f9;
  cursor: pointer;
  transition: background-color 0.2s;
  gap: 12px;
}

.mat-picker-item:last-child {
  border-bottom: none;
}

.mat-picker-item:hover {
  background-color: #f8fafc;
}

.mat-picker-item.selected {
  background-color: rgba(123, 92, 247, 0.03);
}

.mat-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.mat-picker-item .mat-title {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.mat-picker-item .mat-desc {
  font-size: 10px;
  color: #94a3b8;
}

/* Training loader */
.training-loader-box {
  padding: 30px 0;
}

.loader-icon {
  font-size: 40px;
  color: #7B5CF7;
  margin-bottom: 14px;
}

.training-status-title {
  margin: 0 0 6px 0;
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
}

.training-desc {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 24px;
}

.progress-bar-wrapper {
  max-width: 440px;
  margin: 0 auto;
}

/* Details dialog layout */
.analytics-title {
  margin: 0 0 14px 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  display: flex;
  align-items: center;
  gap: 6px;
}

.canvas-container {
  width: 100%;
  height: 260px;
  background-color: #f8fafc;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.wordcloud-canvas {
  width: 100%;
  height: 100%;
}

.style-desc-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.style-prompt-card {
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.02) 0%, rgba(123, 92, 247, 0.02) 100%);
  border: 1px solid rgba(123, 92, 247, 0.1);
  padding: 16px;
  border-radius: 10px;
  min-height: 120px;
}

.style-prompt-txt {
  font-size: 12.5px;
  color: #475569;
  line-height: 1.7;
  margin: 0;
  text-align: justify;
}

.style-summary-details {
  border-top: 1px solid #f1f5f9;
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.summary-row span {
  color: #64748b;
}

.summary-row strong {
  color: #334155;
  font-weight: 600;
}
</style>
