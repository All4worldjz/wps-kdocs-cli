<template>
  <div class="dustbin-container">
    <div class="dustbin-header">
      <h2 class="page-title">回收站</h2>
      <div class="header-actions" v-if="recycledDocs.length > 0">
        <el-button
          type="danger"
          plain
          icon="Delete"
          size="default"
          @click="emptyRecycleBinConfirm"
        >
          清空回收站
        </el-button>
      </div>
    </div>

    <!-- Main Table View -->
    <div class="dustbin-workspace card-panel" v-loading="loading">
      <div v-if="recycledDocs.length > 0" class="table-area-wrapper">
        <el-table
          :data="recycledDocs"
          style="width: 100%"
          class="custom-table"
          @selection-change="handleSelectionChange"
        >
          <el-table-column type="selection" width="55" />

          <el-table-column label="文稿标题" min-width="200">
            <template #default="scope">
              <div class="doc-title-cell">
                <el-icon class="doc-icon"><Document /></el-icon>
                <span class="doc-title">{{ scope.row.title }}</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="原分类" width="120">
            <template #default="scope">
              <el-tag size="small" :type="getTagType(scope.row.category)">
                {{ getCategoryName(scope.row.category) }}
              </el-tag>
            </template>
          </el-table-column>

          <el-table-column label="字数" width="100">
            <template #default="scope">
              <span class="word-count">{{ scope.row.wordCount }} 字</span>
            </template>
          </el-table-column>

          <el-table-column label="删除时间" width="160">
            <template #default="scope">
              <span class="deleted-time">{{ formatTime(scope.row.deletedAt) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="160" fixed="right">
            <template #default="scope">
              <div class="action-buttons-cell">
                <el-button
                  type="primary"
                  size="small"
                  link
                  icon="RefreshLeft"
                  @click="restoreDocSingle(scope.row.id)"
                >
                  恢复
                </el-button>
                <el-button
                  type="danger"
                  size="small"
                  link
                  icon="Delete"
                  @click="deleteDocPermanent(scope.row.id)"
                >
                  彻底删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <!-- Selection bottom action toolbar -->
        <div class="selection-toolbar" v-if="selectedIds.length > 0">
          <span class="toolbar-txt">已选择 <strong>{{ selectedIds.length }}</strong> 项公文</span>
          <div class="toolbar-actions">
            <el-button
              type="primary"
              icon="RefreshLeft"
              size="small"
              @click="restoreBatch"
            >
              批量恢复
            </el-button>
            <el-button
              type="danger"
              icon="Delete"
              size="small"
              @click="deleteBatchPermanent"
            >
              批量彻底删除
            </el-button>
          </div>
        </div>

        <!-- Pagination -->
        <div class="pagination-row" v-if="totalDocs > 0">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :page-sizes="[10, 20, 50]"
            background
            layout="total, sizes, prev, pager, next"
            :total="totalDocs"
            @size-change="handleSizeChange"
            @current-change="handleCurrentChange"
          />
        </div>
      </div>

      <!-- Empty state -->
      <div v-else class="empty-bin-placeholder">
        <el-empty description="您的回收站空空如也，公文创作安全无忧！" :image-size="120" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';
import axios from '../utils/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

const genres = [
  { code: 'SPEECH', name: '讲话稿' },
  { code: 'REFLECTION', name: '心得体会' },
  { code: 'WORK_REPORT', name: '工作报告' },
  { code: 'RESEARCH_REPORT', name: '调研报告' },
  { code: 'NOTICE', name: '通知' },
  { code: 'THANK_YOU_LETTER', name: '感谢信' }
];

// State
const recycledDocs = ref<any[]>([]);
const loading = ref(false);
const totalDocs = ref(0);
const currentPage = ref(1);
const pageSize = ref(10);

const selectedIds = ref<string[]>([]);

onMounted(() => {
  fetchRecycledDocs();
});

// APIs
async function fetchRecycledDocs() {
  loading.value = true;
  try {
    const res: any = await axios.post('/geekseek/aiwriter/document/v1/list', {
      page: currentPage.value,
      pageSize: pageSize.value,
      isRecycled: true
    });
    if (res && res.data) {
      recycledDocs.value = res.data.list || [];
      totalDocs.value = res.data.total || 0;
    }
  } catch (err) {
    console.error(err);
  } finally {
    loading.value = false;
  }
}

function handleSelectionChange(selection: any[]) {
  selectedIds.value = selection.map(item => item.id);
}

// Single Action Dispatchers
async function restoreDocSingle(id: string) {
  try {
    await axios.post('/geekseek/aiwriter/document/v1/recycle', {
      ids: [id],
      action: 'restore'
    });
    ElMessage.success('公文已还原至创作中心');
    fetchRecycledDocs();
  } catch (err) {
    console.error(err);
  }
}

function deleteDocPermanent(id: string) {
  ElMessageBox.confirm('确定要将该公文永久彻底删除吗？删除后数据将无法找回。', '彻底删除', {
    confirmButtonText: '确定彻底删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await axios.post('/geekseek/aiwriter/document/v2/delete', { ids: [id] });
      ElMessage.success('公文已永久删除');
      fetchRecycledDocs();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// Batch Actions
async function restoreBatch() {
  if (selectedIds.value.length === 0) return;
  try {
    await axios.post('/geekseek/aiwriter/document/v1/recycle', {
      ids: selectedIds.value,
      action: 'restore'
    });
    ElMessage.success(`成功还原 ${selectedIds.value.length} 篇公文`);
    selectedIds.value = [];
    fetchRecycledDocs();
  } catch (err) {
    console.error(err);
  }
}

function deleteBatchPermanent() {
  if (selectedIds.value.length === 0) return;
  ElMessageBox.confirm(`确定要将选中的 ${selectedIds.value.length} 篇公文永久彻底删除吗？删除后数据将无法恢复。`, '批量彻底删除', {
    confirmButtonText: '确定彻底删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      await axios.post('/geekseek/aiwriter/document/v2/delete', { ids: selectedIds.value });
      ElMessage.success('选定公文已全部永久删除');
      selectedIds.value = [];
      fetchRecycledDocs();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// Empty entire bin
function emptyRecycleBinConfirm() {
  ElMessageBox.confirm('确定要清空回收站吗？所有已删除的公文将永久消逝，且不可恢复。', '清空回收站', {
    confirmButtonText: '确定清空',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try {
      // Collect all IDs
      const allIds = recycledDocs.value.map(d => d.id);
      await axios.post('/geekseek/aiwriter/document/v2/delete', { ids: allIds });
      ElMessage.success('回收站已成功清空');
      fetchRecycledDocs();
    } catch (err) {
      console.error(err);
    }
  }).catch(() => {});
}

// Helpers
function getCategoryName(code: string) {
  const g = genres.find(item => item.code === code);
  return g ? g.name : '其他';
}

function getTagType(category: string) {
  switch (category) {
    case 'SPEECH': return 'primary';
    case 'NOTICE': return 'warning';
    case 'WORK_REPORT': return 'success';
    default: return 'info';
  }
}

function handleSizeChange(val: number) {
  pageSize.value = val;
  fetchRecycledDocs();
}

function handleCurrentChange(val: number) {
  currentPage.value = val;
  fetchRecycledDocs();
}

function formatTime(isoStr: string) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
</script>

<style scoped>
.dustbin-container {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dustbin-header {
  background-color: #ffffff;
  padding: 16px 24px;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.01);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
}

.card-panel {
  background-color: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.01);
  padding: 20px;
  flex: 1;
}

.table-area-wrapper {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.custom-table {
  border-radius: 8px;
  overflow: hidden;
}

.doc-title-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-icon {
  font-size: 16px;
  color: #64748b;
}

.doc-title {
  font-size: 13.5px;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.word-count {
  font-size: 12.5px;
  font-weight: 500;
  color: #475569;
}

.deleted-time {
  font-size: 12px;
  color: #64748b;
}

.action-buttons-cell {
  display: flex;
  gap: 12px;
}

/* Bottom selection toolbar */
.selection-toolbar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background-color: #1e293b;
  color: #ffffff;
  padding: 12px 24px;
  border-radius: 40px;
  display: flex;
  align-items: center;
  gap: 20px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.toolbar-txt {
  font-size: 12px;
}

.toolbar-txt strong {
  color: #5B6EF6;
  font-size: 14px;
  margin: 0 4px;
}

.toolbar-actions {
  display: flex;
  gap: 10px;
}

.pagination-row {
  display: flex;
  justify-content: center;
  margin-top: 10px;
}

.empty-bin-placeholder {
  background-color: #ffffff;
  padding: 80px 0;
  border-radius: 12px;
  text-align: center;
}
</style>
