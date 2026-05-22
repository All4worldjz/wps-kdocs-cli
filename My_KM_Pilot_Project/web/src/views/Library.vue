<template>
  <div class="library-container">
    <div class="library-header-row">
      <h2 class="page-title">素材文稿</h2>
      <div class="header-actions">
        <!-- AI Semantic Search Toggle -->
        <div class="semantic-toggle-wrapper">
          <span class="toggle-label">AI 语义检索</span>
          <el-switch
            v-model="useSemanticSearch"
            active-color="#5B6EF6"
            inactive-color="#dcdfe6"
            @change="handleSearchModeChange"
          />
        </div>
        <el-input
          v-model="searchKeyword"
          :placeholder="useSemanticSearch ? '输入您的构思想法，AI 自动匹配语义相近素材...' : '搜寻素材标题...'"
          :prefix-icon="useSemanticSearch ? 'MagicStick' : 'Search'"
          clearable
          style="width: 320px; margin-right: 12px;"
          @input="debouncedSearch"
          @keyup.enter="performSearch"
        />
        <el-button
          type="primary"
          icon="Upload"
          class="upload-btn"
          @click="openUploadDialog"
        >
          上传素材
        </el-button>
      </div>
    </div>

    <div class="library-workspace">
      <!-- Sidebar Folders list -->
      <aside class="folders-sidebar card-panel">
        <div class="sidebar-header">
          <span class="section-title">
            <el-icon><Folder /></el-icon> 文件夹
          </span>
          <el-button
            type="primary"
            icon="Plus"
            circle
            size="small"
            plain
            @click="openCreateFolderDialog"
          />
        </div>

        <div class="folder-list-wrapper" v-loading="loadingFolders">
          <div
            class="folder-item-row"
            :class="{ active: activeFolderId === 'root' }"
            @click="selectFolder('root')"
          >
            <el-icon class="folder-icon"><HomeFilled /></el-icon>
            <span class="folder-name">全部素材</span>
          </div>

          <div
            v-for="folder in folders"
            :key="folder.id"
            class="folder-item-row"
            :class="{ active: activeFolderId === folder.id }"
            @click="selectFolder(folder.id)"
          >
            <el-icon class="folder-icon"><FolderOpened v-if="activeFolderId === folder.id" /><Folder v-else /></el-icon>
            <span class="folder-name">{{ folder.name }}</span>

            <!-- Actions -->
            <el-dropdown trigger="click" @click.stop class="folder-actions-dropdown">
              <el-icon class="folder-more-icon"><MoreFilled /></el-icon>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item style="color: #f56c6c;" @click="deleteFolderConfirm(folder)">
                    <el-icon><Delete /></el-icon> 删除文件夹
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </aside>

      <!-- Main Contents Area -->
      <main class="library-main-panel">
        <!-- Channel tabs -->
        <div class="channel-tabs">
          <span
            v-for="tab in channelTabs"
            :key="tab.code"
            class="channel-tab-item"
            :class="{ active: activeChannel === tab.code }"
            @click="selectChannel(tab.code)"
          >
            {{ tab.name }}
          </span>
        </div>

        <!-- Tags / Categories filter -->
        <div class="tags-filter-row">
          <span class="filter-label">素材分类:</span>
          <div class="tags-wrapper">
            <span
              class="tag-pill"
              :class="{ active: activeCategory === '全部' }"
              @click="selectCategory('全部')"
            >
              全部
            </span>
            <span
              v-for="tag in categories"
              :key="tag"
              class="tag-pill"
              :class="{ active: activeCategory === tag }"
              @click="selectCategory(tag)"
            >
              {{ tag }}
            </span>
          </div>
        </div>

        <!-- Materials List View -->
        <div class="materials-viewport" v-loading="loadingMaterials">
          <div v-if="materials.length > 0" class="materials-list-container">
            <el-row :gutter="20">
              <el-col
                v-for="mat in materials"
                :key="mat.id"
                :xs="24" :sm="12" :md="12" :lg="8"
                style="margin-bottom: 20px;"
              >
                <div class="material-card">
                  <div class="card-top">
                    <span class="source-badge">{{ mat.source }}</span>
                    <span class="word-badge">{{ mat.wordCount }} 字</span>
                  </div>

                  <h3 class="mat-title" @click="viewMaterialDetail(mat)">{{ mat.title }}</h3>
                  <p class="mat-excerpt" @click="viewMaterialDetail(mat)">{{ mat.contentPreview }}</p>

                  <div class="card-footer">
                    <span class="upload-time">{{ formatTime(mat.createdAt) }}</span>
                    <div class="footer-btn-actions">
                      <!-- Collection state -->
                      <el-tooltip :content="mat.isImportedKnowledge ? '已加入个人知识库' : '加入个人知识库'" placement="top">
                        <el-button
                          :type="mat.isImportedKnowledge ? 'success' : 'default'"
                          icon="Star"
                          circle
                          size="small"
                          @click="toggleCollect(mat)"
                        />
                      </el-tooltip>

                      <!-- Move Folder -->
                      <el-tooltip content="移动文件夹" placement="top">
                        <el-button
                          icon="Folder"
                          circle
                          size="small"
                          @click="openMoveFolderDialog(mat)"
                        />
                      </el-tooltip>

                      <!-- Delete -->
                      <el-tooltip content="永久删除素材" placement="top">
                        <el-button
                          type="danger"
                          icon="Delete"
                          circle
                          size="small"
                          @click="deleteMaterialConfirm(mat.id)"
                        />
                      </el-tooltip>
                    </div>
                  </div>
                </div>
              </el-col>
            </el-row>

            <!-- Pagination -->
            <div class="pagination-row" v-if="totalMaterials > 0">
              <el-pagination
                v-model:current-page="currentPage"
                v-model:page-size="pageSize"
                :page-sizes="[9, 18, 36]"
                background
                layout="total, sizes, prev, pager, next"
                :total="totalMaterials"
                @size-change="handleSizeChange"
                @current-change="handleCurrentChange"
              />
            </div>
          </div>

          <!-- Empty placeholder -->
          <div v-else class="empty-placeholder">
            <el-empty
              :description="useSemanticSearch ? '未匹配到相似的素材，建议切换到普通检索或丰富构思词。' : '当前目录下暂无相关素材文稿，赶快点击「上传素材」进行添加吧！'"
              :image-size="120"
            />
          </div>
        </div>
      </main>
    </div>

    <!-- Create Folder Dialog -->
    <el-dialog
      v-model="createFolderVisible"
      title="新建文件夹"
      width="420px"
      align-center
    >
      <el-form label-position="top">
        <el-form-item label="文件夹名称" required>
          <el-input
            v-model="newFolderName"
            placeholder="请输入文件夹名称，如：数字政务汇报"
            maxlength="20"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="createFolderVisible = false">取消</el-button>
          <el-button type="primary" :disabled="!newFolderName.trim()" @click="submitCreateFolder">确定</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Move Folder Dialog -->
    <el-dialog
      v-model="moveFolderVisible"
      title="移动素材到文件夹"
      width="440px"
      align-center
    >
      <div class="move-folder-body">
        <p class="dialog-desc">请选择要将素材 <strong>《{{ selectedMat?.title }}》</strong> 移动到的文件夹：</p>
        <div class="folder-options-list">
          <div
            class="folder-option-item"
            :class="{ active: moveTargetFolderId === 'root' }"
            @click="moveTargetFolderId = 'root'"
          >
            <el-icon><HomeFilled /></el-icon>
            <span>素材根目录</span>
          </div>
          <div
            v-for="folder in folders"
            :key="folder.id"
            class="folder-option-item"
            :class="{ active: moveTargetFolderId === folder.id }"
            @click="moveTargetFolderId = folder.id"
          >
            <el-icon><Folder /></el-icon>
            <span>{{ folder.name }}</span>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button @click="moveFolderVisible = false">取消</el-button>
          <el-button type="primary" @click="submitMoveFolder">确定移动</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Upload Material Dialog -->
    <el-dialog
      v-model="uploadDialogVisible"
      title="上传本地公文素材"
      width="520px"
      align-center
    >
      <div class="upload-dialog-body">
        <el-upload
          class="material-uploader"
          drag
          action="#"
          :http-request="handleCustomUpload"
          :before-upload="beforeUploadCheck"
          :show-file-list="false"
          :disabled="uploading"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            将公文拖拽到此处，或<em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              支持 doc, docx, txt, md 等常见格式，单个文件不超过 10 MB。
            </div>
          </template>
        </el-upload>

        <!-- Progress Indicator -->
        <div v-if="uploading" class="upload-progress-box">
          <span class="progress-title">文件深度智能解析中，提取公文段落结构...</span>
          <el-progress :percentage="uploadProgress" status="success" />
        </div>
      </div>
    </el-dialog>

    <!-- Material Detail Viewer Dialog -->
    <el-dialog
      v-model="detailDialogVisible"
      :title="detailMaterial?.title || '素材详情'"
      width="680px"
      align-center
    >
      <div class="detail-dialog-body" v-if="detailMaterial">
        <div class="meta-row">
          <el-tag type="info" size="small">{{ detailMaterial.source }}</el-tag>
          <el-tag type="success" size="small" style="margin-left: 8px;">{{ detailMaterial.category }}</el-tag>
          <span class="meta-word">{{ detailMaterial.wordCount }} 字</span>
          <span class="meta-time">{{ formatTime(detailMaterial.createdAt) }}</span>
        </div>

        <div class="material-content-preview">
          <p v-for="(p, index) in previewParagraphs" :key="index" class="preview-p">
            {{ p }}
          </p>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <el-button type="primary" @click="detailDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import axios from '../utils/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

const channelTabs = [
  { code: 'PERSONAL_MATERIAL', name: '个人素材' },
  { code: 'QIANGGUO_ARTICLE', name: '强国文章' },
  { code: 'STUDY_MATERIAL', name: '学习资料' }
];

// State
const activeChannel = ref('PERSONAL_MATERIAL');
const activeFolderId = ref('root');
const activeCategory = ref('全部');
const searchKeyword = ref('');
const useSemanticSearch = ref(false);

const folders = ref<any[]>([]);
const categories = ref<string[]>([]);
const materials = ref<any[]>([]);

const loadingFolders = ref(false);
const loadingMaterials = ref(false);

const totalMaterials = ref(0);
const currentPage = ref(1);
const pageSize = ref(9);

// Create folder dialog state
const createFolderVisible = ref(false);
const newFolderName = ref('');

// Move folder dialog state
const moveFolderVisible = ref(false);
const selectedMat = ref<any>(null);
const moveTargetFolderId = ref('root');

// Upload dialog state
const uploadDialogVisible = ref(false);
const uploading = ref(false);
const uploadProgress = ref(0);

// Detail dialog state
const detailDialogVisible = ref(false);
const detailMaterial = ref<any>(null);

const previewParagraphs = computed(() => {
  if (!detailMaterial.value || !detailMaterial.value.contentPreview) return [];
  return detailMaterial.value.contentPreview.split('\n').filter((p: string) => p.trim());
});

onMounted(() => {
  fetchFolders();
  fetchCategories();
  fetchMaterials();
});

// Search debounce helpers
let searchTimer: any = null;
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    currentPage.value = 1;
    fetchMaterials();
  }, 400);
}

function performSearch() {
  currentPage.value = 1;
  fetchMaterials();
}

function handleSearchModeChange() {
  searchKeyword.value = '';
  currentPage.value = 1;
  fetchMaterials();
}

// APIs
async function fetchFolders() {
  loadingFolders.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/folder/v1/list', { type: 'MATERIAL' });
    if (res && res.data) {
      folders.value = res.data;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingFolders.value = false;
  }
}

async function fetchCategories() {
  try {
    const res: any = await axios.get('/geekseek/aiwriter/document/v2/tag');
    if (res && res.data) {
      categories.value = res.data;
    }
  } catch (err) {
    console.error(err);
  }
}

async function fetchMaterials() {
  loadingMaterials.value = true;
  try {
    if (useSemanticSearch.value && searchKeyword.value.trim()) {
      // AI semantic search matches
      const res: any = await axios.post('/geekseek/aiwriter/document/v2/semanticSearch', {
        query: searchKeyword.value,
        limit: pageSize.value
      });
      if (res && res.data) {
        // Map simplified semantic items to full preview structure
        materials.value = res.data.map((item: any) => ({
          ...item,
          source: item.source || '智能推荐',
          createdAt: item.createdAt || new Date().toISOString(),
          isImportedKnowledge: false
        }));
        totalMaterials.value = res.data.length;
      }
    } else {
      // Normal list filtering
      const res: any = await axios.post('/geekseek/aiwriter/document/v2/list', {
        page: currentPage.value,
        pageSize: pageSize.value,
        channel: activeChannel.value,
        searchKeyword: searchKeyword.value,
        category: activeCategory.value,
        folderId: activeFolderId.value
      });
      if (res && res.data) {
        materials.value = res.data.list || [];
        totalMaterials.value = res.data.total || 0;
      }
    }
  } catch (err) {
    console.error(err);
  } finally {
    loadingMaterials.value = false;
  }
}

// Selection handlers
function selectChannel(code: string) {
  activeChannel.value = code;
  currentPage.value = 1;
  fetchMaterials();
}

function selectFolder(id: string) {
  activeFolderId.value = id;
  currentPage.value = 1;
  fetchMaterials();
}

function selectCategory(cat: string) {
  activeCategory.value = cat;
  currentPage.value = 1;
  fetchMaterials();
}

// Dialog Launchers
function openCreateFolderDialog() {
  newFolderName.value = '';
  createFolderVisible.value = true;
}

async function submitCreateFolder() {
  try {
    await axios.post('/geekseek/aiwriter/folder/v1/create', {
      name: newFolderName.value,
      type: 'MATERIAL'
    });
    ElMessage.success('新建文件夹成功');
    createFolderVisible.value = false;
    fetchFolders();
  } catch (err) {
    console.error(err);
  }
}

function deleteFolderConfirm(folder: any) {
  ElMessageBox.confirm(`确定要删除文件夹「${folder.name}」吗？其中的素材将退回到根目录。`, '删除文件夹', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await axios.post('/geekseek/aiwriter/folder/v1/delete', { folderId: folder.id });
      ElMessage.success('成功删除文件夹');
      if (activeFolderId.value === folder.id) {
        activeFolderId.value = 'root';
      }
      fetchFolders();
      fetchMaterials();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// Move Folder Handler
function openMoveFolderDialog(mat: any) {
  selectedMat.value = mat;
  moveTargetFolderId.value = mat.folderId || 'root';
  moveFolderVisible.value = true;
}

async function submitMoveFolder() {
  if (!selectedMat.value) return;
  try {
    await axios.post('/geekseek/aiwriter/folder/v1/move', {
      ids: [selectedMat.value.id],
      folderId: moveTargetFolderId.value
    });
    ElMessage.success('成功移动素材');
    moveFolderVisible.value = false;
    fetchMaterials();
  } catch (err) {
    console.error(err);
  }
}

// Toggle Knowledge Collector
async function toggleCollect(mat: any) {
  const willCollect = !mat.isImportedKnowledge;
  try {
    await axios.post('/geekseek/aiwriter/document/v2/collect', {
      docId: mat.id,
      collect: willCollect
    });
    ElMessage.success(willCollect ? '成功加入个人知识库' : '已从知识库中移除');
    fetchMaterials();
  } catch (err) {
    console.error(err);
  }
}

// Delete Material
function deleteMaterialConfirm(id: string) {
  ElMessageBox.confirm('确定要永久删除该素材文稿吗？此操作不可逆。', '删除素材', {
    confirmButtonText: '确定删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await axios.post('/geekseek/aiwriter/document/v2/delete', {
        ids: [id],
        channel: activeChannel.value
      });
      ElMessage.success('素材永久删除成功');
      fetchMaterials();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// Pagination Event Dispatchers
function handleSizeChange(val: number) {
  pageSize.value = val;
  fetchMaterials();
}

function handleCurrentChange(val: number) {
  currentPage.value = val;
  fetchMaterials();
}

// Upload handlers
function openUploadDialog() {
  uploadDialogVisible.value = false;
  uploadProgress.value = 0;
  uploading.value = false;
  uploadDialogVisible.value = true;
}

function beforeUploadCheck(file: any) {
  const allowed = ['doc', 'docx', 'txt', 'md'];
  const ext = file.name.split('.').pop()?.toLowerCase();
  if (!allowed.includes(ext || '')) {
    ElMessage.warning('不支持的文件格式！仅支持 doc, docx, txt, md 文件。');
    return false;
  }
  const isLt10M = file.size / 1024 / 1024 < 10;
  if (!isLt10M) {
    ElMessage.warning('上传文件大小不能超过 10 MB！');
    return false;
  }
  return true;
}

async function handleCustomUpload(options: any) {
  uploading.value = true;
  uploadProgress.value = 10;

  const timer = setInterval(() => {
    if (uploadProgress.value < 85) {
      uploadProgress.value += 15;
    }
  }, 300);

  try {
    // Send upload request
    await axios.post('/geekseek/aiwriter/file/v2/upload');
    clearInterval(timer);
    uploadProgress.value = 100;

    setTimeout(() => {
      ElMessage.success(`《${options.file.name}》上传并提取成功！已加入素材列表。`);
      uploading.value = false;
      uploadDialogVisible.value = false;
      fetchMaterials();
    }, 400);
  } catch (err) {
    clearInterval(timer);
    uploading.value = false;
    ElMessage.error('文件上传/解析发生故障，请检查后端网络状态');
  }
}

// View details
function viewMaterialDetail(mat: any) {
  detailMaterial.value = mat;
  detailDialogVisible.value = true;
}

function formatTime(isoStr: string) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
</script>

<style scoped>
.library-container {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.library-header-row {
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
  gap: 12px;
}

.semantic-toggle-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
  background-color: #f8fafc;
  padding: 6px 14px;
  border-radius: 20px;
  border: 1px solid #e2e8f0;
  margin-right: 8px;
}

.toggle-label {
  font-size: 12px;
  font-weight: 600;
  color: #5B6EF6;
}

.upload-btn {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.15);
}

.library-workspace {
  display: flex;
  gap: 20px;
  flex: 1;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.01);
}

/* Sidebar Folders */
.folders-sidebar {
  width: 240px;
  padding: 16px 0;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px 14px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: #334155;
  display: flex;
  align-items: center;
  gap: 6px;
}

.folder-list-wrapper {
  padding: 8px;
  flex: 1;
  overflow-y: auto;
}

.folder-item-row {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.2s ease;
  position: relative;
  color: #475569;
}

.folder-item-row:hover {
  background-color: #f8fafc;
  color: #5B6EF6;
}

.folder-item-row.active {
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.08) 0%, rgba(123, 92, 247, 0.08) 100%);
  color: #5B6EF6;
  font-weight: 600;
}

.folder-icon {
  font-size: 16px;
  margin-right: 10px;
}

.folder-name {
  font-size: 13px;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.folder-more-icon {
  font-size: 12px;
  color: #94a3b8;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
}

.folder-item-row:hover .folder-more-icon {
  opacity: 1;
}

/* Main Materials view */
.library-main-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.channel-tabs {
  display: flex;
  background-color: #ffffff;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  width: max-content;
}

.channel-tab-item {
  padding: 8px 24px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;
}

.channel-tab-item:hover {
  color: #5B6EF6;
}

.channel-tab-item.active {
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  color: #ffffff;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.15);
}

/* Category Filter Tags */
.tags-filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: #ffffff;
  padding: 12px 20px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
}

.filter-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
  white-space: nowrap;
}

.tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-pill {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 15px;
  background-color: #f1f5f9;
  color: #475569;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s ease;
}

.tag-pill:hover {
  background-color: #e2e8f0;
  color: #5B6EF6;
}

.tag-pill.active {
  background-color: rgba(91, 110, 246, 0.1);
  color: #5B6EF6;
  font-weight: 600;
}

/* Materials Cards */
.materials-viewport {
  flex: 1;
}

.material-card {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  padding: 18px;
  height: 200px;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: all 0.3s ease;
}

.material-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(91, 110, 246, 0.08);
  border-color: #5B6EF6;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.source-badge {
  font-size: 10px;
  background-color: #f1f5f9;
  color: #64748b;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

.word-badge {
  font-size: 11px;
  font-weight: 700;
  color: #5B6EF6;
}

.mat-title {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.material-card:hover .mat-title {
  color: #5B6EF6;
}

.mat-excerpt {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  flex: 1;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  border-top: 1px solid #f1f5f9;
  padding-top: 10px;
}

.upload-time {
  font-size: 11px;
  color: #94a3b8;
}

.footer-btn-actions {
  display: flex;
  gap: 6px;
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}

.empty-placeholder {
  background-color: #ffffff;
  padding: 60px 0;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}

/* Dialog layout Option lists */
.folder-options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
  margin-top: 12px;
}

.folder-option-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  transition: all 0.2s ease;
}

.folder-option-item:hover {
  background-color: #f8fafc;
  border-color: #5B6EF6;
}

.folder-option-item.active {
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.05) 0%, rgba(123, 92, 247, 0.05) 100%);
  border-color: #5B6EF6;
  color: #5B6EF6;
  font-weight: 600;
}

/* Uploader */
.upload-dialog-body {
  padding: 10px 0;
}

.upload-progress-box {
  margin-top: 20px;
  background-color: #f8fafc;
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.progress-title {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-bottom: 8px;
  font-weight: 600;
}

/* Details dialog */
.detail-dialog-body {
  max-height: 480px;
  overflow-y: auto;
  padding-right: 8px;
}

.detail-dialog-body .meta-row {
  display: flex;
  align-items: center;
  margin-bottom: 18px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f1f5f9;
}

.meta-word {
  font-size: 12px;
  color: #5B6EF6;
  font-weight: 600;
  margin-left: auto;
}

.meta-time {
  font-size: 12px;
  color: #94a3b8;
  margin-left: 12px;
}

.material-content-preview {
  background-color: #f8fafc;
  padding: 16px 20px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.preview-p {
  font-size: 14px;
  color: #334155;
  line-height: 1.8;
  margin-bottom: 14px;
  text-indent: 2em;
}

.preview-p:last-child {
  margin-bottom: 0;
}
</style>
