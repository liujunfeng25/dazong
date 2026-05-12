<script setup>
import { useRouter } from 'vue-router'
import { useNotificationStore } from '../../stores/notifications'
import { useUserStore } from '../../stores/user'

const router = useRouter()
const userStore = useUserStore()
const notificationStore = useNotificationStore()

const logout = () => {
  notificationStore.disconnect()
  userStore.logout()
  router.replace('/login')
}
</script>

<template>
  <div class="client-canteen-gate">
    <header class="gate-top">
      <div class="gate-top-left">
        <span class="gate-brand">大宗物资供应链管理系统</span>
        <span class="gate-divider" aria-hidden="true" />
        <span class="gate-sub">采购端 · 选择履约食堂</span>
      </div>
      <el-button class="gate-out" link type="primary" @click="logout">退出登录</el-button>
    </header>
    <main class="gate-body">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.client-canteen-gate {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(165deg, #0f172a 0%, #1e293b 42%, #0f172a 100%);
}
.gate-top {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(10px);
}
.gate-top-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.gate-brand {
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
  letter-spacing: 0.02em;
}
.gate-divider {
  width: 1px;
  height: 16px;
  background: rgba(148, 163, 184, 0.35);
}
.gate-sub {
  font-size: 13px;
  color: #94a3b8;
}
.gate-out {
  color: #93c5fd !important;
}
.gate-body {
  flex: 1;
  min-height: 0;
}
</style>
