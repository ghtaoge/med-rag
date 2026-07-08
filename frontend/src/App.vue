<template>
  <el-container class="app-container">
    <!-- 侧边导航 -->
    <el-aside width="220px" class="app-aside">
      <div class="aside-header">
        <el-icon :size="28" color="#409EFF"><FirstAidKit /></el-icon>
        <span class="aside-title">Med-Rag</span>
      </div>
      <el-menu
        :default-active="activeRoute"
        class="aside-menu"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Folder /></el-icon>
          <span>文档管理</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Clock /></el-icon>
          <span>历史记录</span>
        </el-menu-item>
        <el-menu-item index="/evaluation">
          <el-icon><DataAnalysis /></el-icon>
          <span>效果评估</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系统设置</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <el-text size="small" type="info">v1.0.0</el-text>
      </div>
    </el-aside>

    <!-- 主内容 -->
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()

const activeRoute = computed(() => route.path)

function handleMenuSelect(index) {
  router.push(index)
}
</script>

<style scoped>
.app-container {
  height: 100vh;
  background: #f0f2f5;
}

.app-aside {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.aside-header {
  padding: 20px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.aside-title {
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.aside-menu {
  border-right: none;
  flex: 1;
}

.aside-footer {
  padding: 12px 16px;
  text-align: center;
  border-top: 1px solid #e4e7ed;
}

.app-main {
  padding: 20px;
  overflow-y: auto;
}
</style>
