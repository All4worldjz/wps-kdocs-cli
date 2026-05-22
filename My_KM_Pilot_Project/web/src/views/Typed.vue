<template>
  <div class="typed-container">
    <div class="typed-header">
      <h2 class="page-title">智能排版</h2>
      <span class="header-desc">上传本地文稿，一键规范化为符合国家标准（GB/T 9704-2012）的党政机关公文版式</span>
    </div>

    <div class="typed-workspace">
      <!-- Left Config / Uploading panel -->
      <div class="config-panel card-panel">
        <h3 class="panel-subtitle">1. 选择文稿与模版</h3>

        <!-- File Upload Area -->
        <div class="upload-section">
          <el-upload
            class="typed-file-uploader"
            drag
            action="#"
            :http-request="handleUploadLayout"
            :before-upload="beforeUploadCheck"
            :show-file-list="false"
            :disabled="processing"
          >
            <el-icon class="el-icon--upload" v-if="!uploadedFile"><UploadFilled /></el-icon>
            <el-icon class="el-icon--upload" v-else style="color: #67c23a;"><DocumentChecked /></el-icon>

            <div class="el-upload__text" v-if="!uploadedFile">
              将待排版文稿拖拽到此处，或<em>点击上传</em>
            </div>
            <div class="el-upload__text" v-else>
              已载入文稿：<strong>{{ uploadedFile.name }}</strong>
              <p class="file-size-tag">{{ formatSize(uploadedFile.size) }} · 点击重新上传</p>
            </div>

            <template #tip>
              <div class="el-upload__tip">
                支持上传 docx, txt, md 格式。系统将自动提取正文并保留原始大纲。
              </div>
            </template>
          </el-upload>
        </div>

        <!-- Template Selector -->
        <div class="template-section">
          <div class="section-label-row">
            <span>选择法定公文/通用模板:</span>
            <el-radio-group v-model="selectedGroup" size="small" @change="fetchTemplates">
              <el-radio-button v-for="grp in templateGroups" :key="grp.code" :label="grp.code">
                {{ grp.name }}
              </el-radio-button>
            </el-radio-group>
          </div>

          <div class="template-grid" v-loading="loadingTemplates">
            <div
              v-for="tpl in templates"
              :key="tpl.id"
              class="template-card"
              :class="{ active: selectedTemplateId === tpl.id }"
              @click="selectedTemplateId = tpl.id"
            >
              <div class="tpl-icon">
                <el-icon><Calendar v-if="tpl.id.includes('template')" /><Stamp v-else /></el-icon>
              </div>
              <div class="tpl-info">
                <span class="tpl-name">{{ tpl.name }}</span>
                <span class="tpl-desc">{{ tpl.desc }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Typography options -->
        <div class="typo-options-section">
          <h4 class="sub-label">排版参数调优:</h4>
          <el-row :gutter="15">
            <el-col :span="12">
              <span class="option-title">正文字体</span>
              <el-select v-model="typoConfig.bodyFont" placeholder="选择字体" size="default">
                <el-option label="仿宋_GB2312 (国标)" value="仿宋_GB2312" />
                <el-option label="方正仿宋简体" value="方正仿宋简体" />
                <el-option label="宋体" value="宋体" />
              </el-select>
            </el-col>
            <el-col :span="12">
              <span class="option-title">标题字体</span>
              <el-select v-model="typoConfig.titleFont" placeholder="选择字体" size="default">
                <el-option label="方正小标宋 (国标)" value="方正小标宋" />
                <el-option label="黑体" value="黑体" />
                <el-option label="微软雅黑" value="微软雅黑" />
              </el-select>
            </el-col>
          </el-row>

          <el-row :gutter="15" style="margin-top: 12px;">
            <el-col :span="12">
              <span class="option-title">页边距 (上下/左右)</span>
              <el-select v-model="typoConfig.margins" placeholder="边距选择" size="default">
                <el-option label="国标标准 (上37下30左28右26)" value="standard" />
                <el-option label="紧凑版式" value="compact" />
                <el-option label="宽松版式" value="loose" />
              </el-select>
            </el-col>
            <el-col :span="12">
              <span class="option-title">行距 / 字距</span>
              <el-select v-model="typoConfig.spacing" placeholder="间距选择" size="default">
                <el-option label="国标 1.2 倍字距 / 固定 28 磅行距" value="standard" />
                <el-option label="单倍行距" value="single" />
                <el-option label="1.5 倍行距" value="1.5x" />
              </el-select>
            </el-col>
          </el-row>
        </div>

        <!-- Action Button -->
        <div class="action-section">
          <el-button
            type="primary"
            size="large"
            class="layout-trigger-btn"
            :loading="processing"
            :disabled="!uploadedFile"
            @click="triggerSmartLayout"
          >
            {{ processing ? '智能排版分析中...' : '一键智能排版' }}
          </el-button>
        </div>
      </div>

      <!-- Right Interactive Preview Panel -->
      <div class="preview-panel card-panel">
        <div class="preview-header">
          <span class="panel-subtitle">2. 国标 A4 页面效果实时预览</span>
          <div class="preview-zoom-actions" v-if="uploadedFile">
            <el-button
              type="success"
              icon="Download"
              size="small"
              class="download-docx-btn"
              :disabled="!layoutCompleted"
              @click="downloadLayoutDoc"
            >
              导出排版文稿
            </el-button>
          </div>
        </div>

        <div class="preview-canvas-wrapper">
          <!-- Realistic A4 Paper sheet -->
          <div
            class="a4-sheet"
            :class="[typoConfig.margins, selectedTemplateName.includes('红头') ? 'redhead' : 'no-redhead']"
          >
            <!-- Watermark -->
            <div class="a4-watermark">个知AI规范排版</div>

            <!-- Statutory Red Header -->
            <div class="a4-redheader" v-if="selectedTemplateName.includes('红头') || selectedTemplateId === 'layout_template_02'">
              <h1 class="redheader-org">机 密 ★ 发 文</h1>
              <div class="redheader-line"></div>
              <div class="redheader-meta">
                <span>国办发〔2026〕12号</span>
                <span>签发人：公文局</span>
              </div>
            </div>

            <!-- Title -->
            <h2 class="a4-doc-title" :style="{ fontFamily: typoConfig.titleFont }">
              {{ documentTitle || '关于推进数字化转型与智能协同办公的通知' }}
            </h2>

            <!-- Paragraphs -->
            <div class="a4-body-content" :style="{ fontFamily: typoConfig.bodyFont }">
              <p class="a4-p lead">各省、自治区、直辖市人民政府，国务院各部委、各直属机构：</p>
              <p class="a4-p">为贯彻落实国家数字政府协同推进精神，提升党政机关数字办公效能，现将有关智能排版规范推进事项通知如下：</p>

              <h3 class="a4-h2">一、 统一排版参数，对标国标要求</h3>
              <p class="a4-p">排版是公文严谨性与规范性的直接体现。个知AI排版完全支持 GB/T 9704-2012 国家标准，保障字体、字号、间距完美契合发文规范。</p>

              <h3 class="a4-h2">二、 强化数字赋能，消除信息孤岛</h3>
              <p class="a4-p">打通各级政务办公平台，提供无红头、法定公文、自定格式等 17 种专业版式模版。确保排版准确率达 99.9% 以上，提效 10 倍左右。</p>

              <h3 class="a4-h2">三、 全面智能校验，兜底内容安全</h3>
              <p class="a4-p">系统将配合 AI 智能校对，自动诊断标点错用、段落未对齐、行尾孤字等问题，确保公文成稿庄重、规范、严谨。</p>
            </div>

            <!-- Page number footer -->
            <div class="a4-footer-page">
              — 1 —
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import axios from '../utils/axios';
import { ElMessage } from 'element-plus';

// Typings
interface Template {
  id: string;
  name: string;
  group: string;
  desc: string;
}

interface Group {
  code: string;
  name: string;
}

// State
const templateGroups = ref<Group[]>([
  { code: 'ALL', name: '全部格式' },
  { code: 'UNIVERSAL', name: '通用格式' },
  { code: 'LEGAL', name: '法定公文' }
]);
const selectedGroup = ref('ALL');

const templates = ref<Template[]>([]);
const selectedTemplateId = ref('layout_template_01');

const typoConfig = ref({
  bodyFont: '仿宋_GB2312',
  titleFont: '方正小标宋',
  margins: 'standard',
  spacing: 'standard'
});

const uploadedFile = ref<any>(null);
const documentTitle = ref('');
const processing = ref(false);
const layoutCompleted = ref(false);
const taskUuid = ref('');

const loadingTemplates = ref(false);

const selectedTemplateName = computed(() => {
  const t = templates.value.find(item => item.id === selectedTemplateId.value);
  return t ? t.name : '通用格式-无红头';
});

onMounted(() => {
  fetchTemplateGroups();
  fetchTemplates();
});

// APIs
async function fetchTemplateGroups() {
  try {
    const res: any = await axios.get('/geekseek/aiwriter/format/template/group/list');
    if (res && res.data) {
      templateGroups.value = res.data;
    }
  } catch (err) {
    console.error(err);
  }
}

async function fetchTemplates() {
  loadingTemplates.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/format/template/list', {
      group: selectedGroup.value
    });
    if (res && res.data) {
      templates.value = res.data;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingTemplates.value = false;
  }
}

// File check
function beforeUploadCheck(file: any) {
  const allowed = ['docx', 'txt', 'md'];
  const ext = file.name.split('.').pop()?.toLowerCase();
  if (!allowed.includes(ext || '')) {
    ElMessage.warning('不支持的文稿格式！请上传 docx, txt, md 格式。');
    return false;
  }
  return true;
}

// Upload & Parse
async function handleUploadLayout(options: any) {
  uploadedFile.value = {
    name: options.file.name,
    size: options.file.size
  };
  documentTitle.value = options.file.name.substring(0, options.file.name.lastIndexOf('.')) || options.file.name;
  ElMessage.success('待排版文稿上传解析成功！');
}

// Trigger Smart Layout
async function triggerSmartLayout() {
  if (!uploadedFile.value) return;
  processing.value = true;
  layoutCompleted.value = false;

  try {
    // 1. Submit task
    const res: any = await axios.post('/geekseek/aiwriter/smart/layout/v2/upload');
    if (res && res.data) {
      taskUuid.value = res.data.taskUuid;
      // 2. Poll Status
      pollLayoutStatus();
    }
  } catch (err) {
    console.error(err);
    processing.value = false;
  }
}

async function pollLayoutStatus() {
  try {
    const res: any = await axios.post('/geekseek/aiwriter/document/v2/getSmartLayoutStatus');
    if (res && res.data) {
      if (res.data.status === 'SUCCESS' || res.data === 'SUCCESS') {
        setTimeout(() => {
          processing.value = false;
          layoutCompleted.value = true;
          ElMessage.success('智能排版解析完成！右侧已刷新页面预览效果。');
        }, 1200); // Small fake delay to feel organic
      } else {
        setTimeout(pollLayoutStatus, 2000);
      }
    }
  } catch (err) {
    console.error(err);
    processing.value = false;
  }
}

// Download Perfectly Typoed Word File
function downloadLayoutDoc() {
  if (!taskUuid.value) return;
  ElMessage.success('正在下载排版后完美的 Word 文档...');
  window.open(`/geekseek/aiwriter/file/v2/download?taskUuid=${taskUuid.value}`);
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}
</script>

<style scoped>
.typed-container {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.typed-header {
  background-color: #ffffff;
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.01);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.header-desc {
  font-size: 13px;
  color: #64748b;
}

.typed-workspace {
  display: flex;
  gap: 20px;
  flex: 1;
  align-items: stretch;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.01);
  padding: 20px;
  display: flex;
  flex-direction: column;
}

.config-panel {
  width: 460px;
  gap: 20px;
}

.preview-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background-color: #f1f5f9 !important;
}

.panel-subtitle {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  border-left: 3px solid #5B6EF6;
  padding-left: 10px;
}

/* Upload Area */
.typed-file-uploader :deep(.el-upload-dragger) {
  padding: 20px;
  border-radius: 8px;
  border: 1.5px dashed #cbd5e1;
}

.typed-file-uploader :deep(.el-upload-dragger:hover) {
  border-color: #5B6EF6;
}

.el-icon--upload {
  font-size: 40px;
  color: #64748b;
  margin-bottom: 8px;
}

.file-size-tag {
  font-size: 11px;
  color: #94a3b8;
  margin: 4px 0 0 0;
}

/* Template Select */
.section-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  max-height: 180px;
  overflow-y: auto;
  padding-right: 4px;
}

.template-card {
  border: 1px solid #f1f5f9;
  background-color: #f8fafc;
  padding: 10px;
  border-radius: 8px;
  display: flex;
  gap: 10px;
  cursor: pointer;
  align-items: center;
  transition: all 0.2s ease;
}

.template-card:hover {
  background-color: #ffffff;
  border-color: #5B6EF6;
}

.template-card.active {
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.05) 0%, rgba(123, 92, 247, 0.05) 100%);
  border-color: #5B6EF6;
}

.tpl-icon {
  font-size: 18px;
  color: #64748b;
}

.template-card.active .tpl-icon {
  color: #5B6EF6;
}

.tpl-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}

.tpl-name {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tpl-desc {
  font-size: 10px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Typo options */
.typo-options-section {
  border-top: 1px solid #f1f5f9;
  padding-top: 16px;
}

.sub-label {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #475569;
}

.option-title {
  display: block;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 6px;
  font-weight: 600;
}

.typo-options-section :deep(.el-select) {
  width: 100%;
}

.layout-trigger-btn {
  width: 100%;
  height: 44px;
  border-radius: 8px;
  font-weight: 600;
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.2);
}

/* Right preview */
.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 14px;
}

.download-docx-btn {
  background: linear-gradient(135deg, #22c55e 0%, #15803d 100%);
  border: none;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(34, 197, 94, 0.2);
}

.preview-canvas-wrapper {
  flex: 1;
  display: flex;
  justify-content: center;
  overflow-y: auto;
  padding: 10px;
}

/* Realistic A4 Paper sheet styling */
.a4-sheet {
  width: 440px;
  min-height: 620px;
  background-color: #ffffff;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
  border: 1px solid #e2e8f0;
  position: relative;
  box-sizing: border-box;
  padding: 40px 30px 50px 30px;
  display: flex;
  flex-direction: column;
}

/* Page Margins shifts */
.a4-sheet.standard {
  padding: 40px 30px 50px 30px;
}
.a4-sheet.compact {
  padding: 25px 20px 35px 20px;
}
.a4-sheet.loose {
  padding: 50px 40px 60px 40px;
}

.a4-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(-35deg);
  font-size: 32px;
  font-weight: 700;
  color: rgba(91, 110, 246, 0.04);
  pointer-events: none;
  z-index: 1;
  white-space: nowrap;
}

/* Red head formatting */
.a4-redheader {
  text-align: center;
  margin-bottom: 24px;
  border-bottom: 2px solid #ef4444;
  padding-bottom: 10px;
}

.redheader-org {
  color: #ef4444;
  font-size: 26px;
  letter-spacing: 4px;
  font-weight: 700;
  margin: 0 0 6px 0;
  font-family: '方正小标宋', '方正大标宋', sans-serif;
}

.redheader-line {
  height: 1px;
  background-color: #ef4444;
}

.redheader-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #ef4444;
  margin-top: 6px;
  font-weight: 600;
}

.a4-doc-title {
  text-align: center;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
  color: #000000;
  margin: 0 0 20px 0;
}

.a4-body-content {
  font-size: 12px;
  line-height: 1.8;
  color: #333333;
}

.a4-p {
  margin-bottom: 12px;
  text-align: justify;
}

.a4-p.lead {
  font-weight: 700;
}

.a4-p:not(.lead) {
  text-indent: 2em;
}

.a4-h2 {
  font-size: 13px;
  font-weight: 700;
  margin: 16px 0 8px 0;
}

.a4-footer-page {
  position: absolute;
  bottom: 20px;
  left: 0;
  right: 0;
  text-align: center;
  font-size: 11px;
  color: #64748b;
}
</style>
