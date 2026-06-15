<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from './AppHeader.vue'
import { useUserStore } from '../stores/user'

const props = defineProps({
  title: String,
  roleLabel: String,
  color: String,
  menu: { type: Array, default: () => [] },
})

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const roleThemes = {
  客户端: {
    accent: '#4f7cff',
    sidebarStart: '#264A9E',
    sidebarEnd: '#0b1120',
    contentGlowA: 'rgba(79, 124, 255, 0.14)',
    contentGlowB: 'rgba(147, 197, 253, 0.14)',
  },
  供货商端: {
    accent: '#f97316',
    sidebarStart: '#9A3412',
    sidebarEnd: '#101321',
    contentGlowA: 'rgba(249, 115, 22, 0.15)',
    contentGlowB: 'rgba(251, 146, 60, 0.12)',
  },
  配送商端: {
    accent: '#0ea5e9',
    sidebarStart: '#1E3A8A',
    sidebarEnd: '#0a1224',
    contentGlowA: 'rgba(14, 165, 233, 0.16)',
    contentGlowB: 'rgba(56, 189, 248, 0.14)',
  },
  厂家端: {
    accent: '#22c55e',
    sidebarStart: '#14532D',
    sidebarEnd: '#0b1613',
    contentGlowA: 'rgba(34, 197, 94, 0.14)',
    contentGlowB: 'rgba(74, 222, 128, 0.12)',
  },
  运营端: {
    accent: '#8b5cf6',
    sidebarStart: '#312E81',
    sidebarEnd: '#0f0f25',
    contentGlowA: 'rgba(139, 92, 246, 0.16)',
    contentGlowB: 'rgba(167, 139, 250, 0.13)',
  },
  监管端: {
    accent: '#22d3ee',
    sidebarStart: '#111827',
    sidebarEnd: '#050914',
    contentGlowA: 'rgba(34, 211, 238, 0.15)',
    contentGlowB: 'rgba(45, 212, 191, 0.12)',
  },
}
/** 侧栏主题按端关键字匹配；roleLabel 若带副标题须仍以「客户端」等前缀开头，否则会误用默认蓝主题 */
const roleThemeKey = computed(() => {
  const label = String(props.roleLabel || '').trim()
  const keys = ['客户端', '供货商端', '配送商端', '厂家端', '运营端', '监管端']
  for (const k of keys) {
    if (label === k || label.startsWith(k)) return k
  }
  return '客户端'
})
const currentTheme = computed(() => roleThemes[roleThemeKey.value] || roleThemes['客户端'])
const sidebarStyle = computed(() => ({
  background: `linear-gradient(180deg, ${currentTheme.value.sidebarStart || props.color || '#1f2937'} 0%, ${currentTheme.value.sidebarEnd || '#0b1120'} 100%)`,
}))
const shellStyle = computed(() => ({
  '--role-accent': currentTheme.value.accent,
  '--role-glow-a': currentTheme.value.contentGlowA,
  '--role-glow-b': currentTheme.value.contentGlowB,
  '--el-color-primary': currentTheme.value.accent,
}))
const monitorFullscreen = computed(() => {
  return route.path === '/monitor/dashboard'
    || route.path === '/monitor/tianshu'
    || route.path === '/monitor/price-cockpit'
})

const showBack = computed(() => {
  // 使用 fullPath：嵌套路由下 route.path 可能不含父级（如 /orders/new），导致深度判断错误
  const pathOnly = String(route.fullPath || '').split('?')[0].split('#')[0]
  const parts = pathOnly.split('/').filter(Boolean)
  return parts.length >= 3
})

const goBack = () => {
  if (window.history.length > 1) {
    router.back()
    return
  }
  if (userStore.role) {
    router.push(`/${userStore.role}`)
    return
  }
  router.push('/login')
}

// 移动端：侧栏抽屉开关；切换路由后自动收起
const mobileNavOpen = ref(false)
const navTo = (path) => {
  router.push(path)
  mobileNavOpen.value = false
}
watch(() => route.fullPath, () => {
  mobileNavOpen.value = false
})
</script>

<template>
  <div v-if="monitorFullscreen" class="h-screen overflow-hidden">
    <router-view />
  </div>
  <div v-else class="h-screen flex overflow-hidden role-shell" :class="{ 'nav-open': mobileNavOpen }" :style="shellStyle">
    <div class="nav-overlay" @click="mobileNavOpen = false" />
    <aside class="portal-aside w-66 p-4 text-white" :style="sidebarStyle">
      <div class="glass-card p-4 mb-4 border-white/15! bg-white/8!">
        <div class="text-xs text-slate-200/85 tracking-[0.2em] mb-1">DAZONG PLATFORM</div>
        <div class="text-lg font-bold leading-tight">{{ props.roleLabel }}</div>
      </div>
      <el-menu
        :default-active="route.path"
        class="!border-none !bg-transparent portal-menu"
        :style="{ background: 'transparent' }"
      >
        <el-menu-item
          v-for="item in props.menu"
          :key="item.path"
          :index="item.path"
          @click="navTo(item.path)"
        >
          {{ item.label }}
        </el-menu-item>
      </el-menu>
    </aside>
    <div class="flex-1 flex flex-col bg-transparent role-content min-w-0">
      <AppHeader :title="props.title" :role-label="props.roleLabel" @toggle-nav="mobileNavOpen = !mobileNavOpen" />
      <div class="app-content-area p-5 overflow-auto min-w-0">
        <div v-if="showBack" class="back-row">
          <el-button size="small" plain @click="goBack">返回上一层</el-button>
        </div>
        <router-view />
      </div>
    </div>
  </div>
</template>

<style scoped>
:deep(.role-content) {
  background:
    radial-gradient(circle at 18% 12%, var(--role-glow-a), transparent 36%),
    radial-gradient(circle at 86% 88%, var(--role-glow-b), transparent 34%);
}

:deep(.portal-menu .el-menu-item) {
  height: 44px;
  margin-bottom: 8px;
  border-radius: 12px;
  color: rgba(241, 245, 249, 0.84);
  transition: all 180ms ease;
}

:deep(.portal-menu .el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
}

:deep(.portal-menu .el-menu-item.is-active) {
  background: linear-gradient(90deg, color-mix(in srgb, var(--role-accent) 92%, #ffffff 8%), color-mix(in srgb, var(--role-accent) 72%, #a5d8ff 28%));
  color: #fff;
  box-shadow: 0 10px 18px color-mix(in srgb, var(--role-accent) 34%, transparent);
}
.back-row {
  margin-bottom: 10px;
}

/* 桌面默认隐藏遮罩 */
.nav-overlay {
  display: none;
}

/* 移动端：侧栏抽屉化 */
@media (max-width: 768px) {
  .portal-aside {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 1001;
    width: 78vw;
    max-width: 300px;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    overflow-y: auto;
  }
  .role-shell.nav-open .portal-aside {
    transform: translateX(0);
    box-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
  }
  .nav-overlay {
    position: fixed;
    inset: 0;
    z-index: 1000;
    background: rgba(15, 23, 42, 0.45);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s ease;
  }
  .role-shell.nav-open .nav-overlay {
    opacity: 1;
    pointer-events: auto;
  }
  .app-content-area {
    padding: 12px !important;
  }
}
</style>
