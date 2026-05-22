<template>
  <div class="layout-container">
    <!-- Top Header -->
    <header class="header">
      <div class="logo-area">
        <el-icon class="logo-icon"><Platform /></el-icon>
        <span class="logo-title">个知AI工作站</span>
        <span class="logo-badge">写作助手</span>
      </div>

      <div class="header-right">
        <!-- Token Usage Indicator -->
        <div class="quota-container" v-if="userStore.usage">
          <el-tooltip effect="dark" placement="bottom">
            <template #content>
              <div class="quota-tooltip">
                <p><strong>通根总额度:</strong> {{ formatNumber(userStore.usage.totalTokens) }}</p>
                <p><strong>已消耗额度:</strong> {{ formatNumber(userStore.usage.usedTokens) }}</p>
                <p><strong>有效期至:</strong> {{ userStore.usage.expireAt }}</p>
              </div>
            </template>
            <div class="quota-bar-wrapper">
              <span class="quota-label">AI 算力额度</span>
              <el-progress
                :percentage="usagePercentage"
                :stroke-width="8"
                :color="progressColors"
                style="width: 140px;"
                :show-text="false"
              />
              <span class="quota-val">{{ formatRemaining(userStore.usage.remainingTokens) }}</span>
            </div>
          </el-tooltip>
        </div>

        <!-- User Info -->
        <el-dropdown trigger="click" class="user-dropdown">
          <div class="user-info">
            <el-avatar :size="32" class="user-avatar" icon="UserFilled" />
            <span class="username">{{ userStore.userInfo?.nickname || '公文助理_小春' }}</span>
            <el-icon class="dropdown-arrow"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item>
                <el-icon><User /></el-icon>个人中心
              </el-dropdown-item>
              <el-dropdown-item>
                <el-icon><Setting /></el-icon>系统设置
              </el-dropdown-item>
              <el-dropdown-item divided style="color: #f56c6c;">
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="main-body">
      <!-- Sidebar Navigation -->
      <aside class="sidebar">
        <!-- New Document Launcher -->
        <div class="action-btn-area">
          <el-button
            type="primary"
            class="new-write-btn"
            icon="Plus"
            @click="openCreateDialog"
          >
            新建写作
          </el-button>
        </div>

        <!-- Sidebar Navigation Menu -->
        <el-menu
          :default-active="activeMenu"
          class="sidebar-menu"
          router
        >
          <el-menu-item index="/writer/document-list">
            <el-icon><Document /></el-icon>
            <span>创作中心</span>
          </el-menu-item>
          <el-menu-item index="/writer/document-list/library">
            <el-icon><Folder /></el-icon>
            <span>素材文稿</span>
          </el-menu-item>
          <el-menu-item index="/writer/document-list/typed">
            <el-icon><Grid /></el-icon>
            <span>智能排版</span>
          </el-menu-item>
          <el-menu-item index="/writer/document-list/style">
            <el-icon><MagicStick /></el-icon>
            <span>文风模板</span>
          </el-menu-item>
          <el-menu-item index="/writer/document-list/dustbin">
            <el-icon><Delete /></el-icon>
            <span>回收站</span>
          </el-menu-item>
        </el-menu>

        <div class="sidebar-footer">
          <p>© 2026 个知AI工作站</p>
          <p>Version 1.22.0</p>
        </div>
      </aside>

      <!-- Main Workspace Router View -->
      <main class="content-viewport">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>

    <!-- Create Document Dialog Component -->
    <el-dialog
      v-model="createDialogVisible"
      title="新建写作任务"
      width="780px"
      destroy-on-close
      align-center
      class="create-task-dialog"
    >
      <div class="dialog-body">
        <div class="creation-tabs">
          <div
            class="creation-tab"
            :class="{ active: creationMode === 'guided' }"
            @click="creationMode = 'guided'"
          >
            <div class="tab-icon-wrapper guided">
              <el-icon><MagicStick /></el-icon>
            </div>
            <div class="tab-text">
              <h3>向导式写作</h3>
              <p>适合正式公文，包含交代、参考、生成提纲、流式起草完整步骤</p>
            </div>
          </div>

          <div
            class="creation-tab"
            :class="{ active: creationMode === 'free' }"
            @click="creationMode = 'free'"
          >
            <div class="tab-icon-wrapper free">
              <el-icon><EditPen /></el-icon>
            </div>
            <div class="tab-text">
              <h3>单步快速写作</h3>
              <p>适合通知、年终总结等常规题材，输入构思要求直接流式起草</p>
            </div>
          </div>
        </div>

        <!-- Guided Writing Options -->
        <div v-if="creationMode === 'guided'" class="mode-options">
          <h4>选择公文文种（支持完整向导）</h4>
          <div class="genre-grid">
            <div
              v-for="item in guidedGenres"
              :key="item.code"
              class="genre-card"
              @click="startGuidedWriting(item.code)"
            >
              <div class="genre-icon">
                <el-icon><Document /></el-icon>
              </div>
              <span class="genre-name">{{ item.name }}</span>
            </div>
          </div>
        </div>

        <!-- Free Writing Options -->
        <div v-else class="mode-options">
          <h4>选择创作方向（快速单步起草）</h4>
          <div class="genre-grid">
            <div
              v-for="item in freeGenres"
              :key="item.code"
              class="genre-card free-genre"
              @click="startFreeWriting(item.code)"
            >
              <div class="genre-icon">
                <el-icon><Notebook /></el-icon>
              </div>
              <span class="genre-name">{{ item.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useUserStore } from '../store/user';


const userStore = useUserStore();
const route = useRoute();
const router = useRouter();

const createDialogVisible = ref(false);
const creationMode = ref<'guided' | 'free'>('guided');

const activeMenu = computed(() => route.path);

onMounted(() => {
  userStore.fetchUserInfo();
  userStore.fetchUsage();
  userStore.fetchConfig();
});

// Calculate remaining tokens usage percentage
const usagePercentage = computed(() => {
  if (!userStore.usage) return 0;
  const remaining = userStore.usage.remainingTokens;
  const total = userStore.usage.totalTokens;
  return Math.max(0, Math.min(100, Math.round((remaining / total) * 100)));
});

const progressColors = [
  { color: '#f56c6c', percentage: 20 },
  { color: '#e6a23c', percentage: 50 },
  { color: '#5B6EF6', percentage: 100 }
];

const guidedGenres = [
  { code: 'SPEECH', name: '讲话稿' },
  { code: 'REFLECTION', name: '心得体会' },
  { code: 'WORK_REPORT', name: '工作报告' },
  { code: 'RESEARCH_REPORT', name: '调研报告' },
  { code: 'NOTICE', name: '通知' },
  { code: 'THANK_YOU_LETTER', name: '感谢信' }
];

const freeGenres = [
  { code: 'FREE_WRITING', name: '自由创作' },
  { code: 'MEETING_SUMMARY', name: '会议纪要' },
  { code: 'INDIVIDUAL_YEAR_END_REPORT', name: '年终总结' },
  { code: 'OFFICIAL_ACCOUNT_ARTICLE', name: '公众号文章' },
  { code: 'DAILY_MONTHLY_REPORT', name: '日报月报' },
  { code: 'TRAINING_REFLECTION', name: '培训心得' }
];

function formatNumber(num: number) {
  return num.toLocaleString();
}

function formatRemaining(num: number) {
  if (num > 1000000) {
    return (num / 1000000).toFixed(2) + ' M';
  }
  return num.toLocaleString();
}

function openCreateDialog() {
  createDialogVisible.value = true;
}

// Routes into Multi-step Guided Writing Wizard
function startGuidedWriting(category: string) {
  createDialogVisible.value = false;
  router.push({
    path: '/writer/document-list',
    query: { writingMenu: 'true', category }
  });
}

// Routes into Fast Single-step writing setup (launches creation draft)
function startFreeWriting(category: string) {
  createDialogVisible.value = false;
  // Navigates directly to the wizard setup for single page
  router.push({
    path: '/writer/document-list',
    query: { writingMenu: 'true', category, quickMode: 'true' }
  });
}
</script>

<style scoped>
.layout-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background-color: #f5f7ff;
}

/* Header styling with subtle blue-purple shadows */
.header {
  height: 60px;
  background-color: #ffffff;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  border-bottom: 1px solid #e2e8f0;
  box-shadow: 0 2px 10px rgba(91, 110, 246, 0.05);
  z-index: 100;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 24px;
  color: #5B6EF6;
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.logo-title {
  font-size: 18px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.5px;
}

.logo-badge {
  font-size: 11px;
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  color: #ffffff;
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 24px;
}

.quota-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
  background-color: #f8fafc;
  padding: 6px 14px;
  border-radius: 30px;
  border: 1px solid #f1f5f9;
  cursor: pointer;
  transition: all 0.3s ease;
}

.quota-bar-wrapper:hover {
  border-color: #5B6EF6;
  background-color: #f5f7ff;
}

.quota-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

.quota-val {
  font-size: 13px;
  font-weight: 700;
  color: #5B6EF6;
}

.quota-tooltip p {
  margin: 4px 0;
  font-size: 12px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
  transition: background-color 0.3s;
}

.user-info:hover {
  background-color: #f1f5f9;
}

.user-avatar {
  background-color: #5B6EF6;
}

.username {
  font-size: 14px;
  font-weight: 500;
  color: #334155;
}

.dropdown-arrow {
  font-size: 12px;
  color: #64748b;
}

.main-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Sidebar styling */
.sidebar {
  width: 200px;
  background-color: #ffffff;
  border-right: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  padding: 20px 0;
  z-index: 90;
}

.action-btn-area {
  padding: 0 16px 20px 16px;
}

.new-write-btn {
  width: 100%;
  height: 40px;
  border-radius: 8px;
  background: linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%);
  border: none;
  font-weight: 600;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.2);
  transition: all 0.3s ease;
}

.new-write-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(91, 110, 246, 0.3);
}

.sidebar-menu {
  border-right: none;
  flex: 1;
}

.sidebar-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  margin: 4px 12px;
  border-radius: 8px;
  color: #475569;
  font-weight: 500;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background-color: #f1f5f9;
  color: #5B6EF6;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.08) 0%, rgba(123, 92, 247, 0.08) 100%);
  color: #5B6EF6;
  font-weight: 600;
}

.sidebar-footer {
  padding: 20px 16px 0 16px;
  border-top: 1px solid #f1f5f9;
  text-align: center;
}

.sidebar-footer p {
  margin: 2px 0;
  font-size: 11px;
  color: #94a3b8;
}

/* Content viewport */
.content-viewport {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background-color: #f8fafc;
}

/* Dialog Styles */
.creation-tabs {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
}

.creation-tab {
  flex: 1;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 20px;
  cursor: pointer;
  display: flex;
  align-items: flex-start;
  gap: 16px;
  transition: all 0.3s ease;
}

.creation-tab:hover {
  border-color: #5B6EF6;
  background-color: #fcfdff;
}

.creation-tab.active {
  border-color: #5B6EF6;
  background: linear-gradient(135deg, rgba(91, 110, 246, 0.02) 0%, rgba(123, 92, 247, 0.02) 100%);
  box-shadow: 0 4px 12px rgba(91, 110, 246, 0.06);
}

.tab-icon-wrapper {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.tab-icon-wrapper.guided {
  background-color: rgba(91, 110, 246, 0.1);
  color: #5B6EF6;
}

.tab-icon-wrapper.free {
  background-color: rgba(123, 92, 247, 0.1);
  color: #7B5CF7;
}

.tab-text h3 {
  margin: 0 0 6px 0;
  font-size: 16px;
  color: #1e293b;
  font-weight: 600;
}

.tab-text p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.mode-options h4 {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #475569;
  font-weight: 600;
}

.genre-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.genre-card {
  border: 1px solid #f1f5f9;
  background-color: #f8fafc;
  border-radius: 8px;
  padding: 16px 12px;
  text-align: center;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  transition: all 0.2s ease;
}

.genre-card:hover {
  background-color: #ffffff;
  border-color: #5B6EF6;
  color: #5B6EF6;
  box-shadow: 0 4px 10px rgba(91, 110, 246, 0.08);
  transform: translateY(-2px);
}

.genre-icon {
  font-size: 22px;
  color: #64748b;
  transition: color 0.2s;
}

.genre-card:hover .genre-icon {
  color: #5B6EF6;
}

.genre-name {
  font-size: 13px;
  font-weight: 500;
  color: #334155;
}

.genre-card:hover .genre-name {
  color: #5B6EF6;
}

/* Animations */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
