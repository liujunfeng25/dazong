<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { changePasswordApi } from '../../api/auth'
import { useNotificationStore } from '../../stores/notifications'
import { useUserStore } from '../../stores/user'

const route = useRoute()
const router = useRouter()
const notifStore = useNotificationStore()
const userStore = useUserStore()

const tabs = [
  { label: '看板', icon: 'dashboard', path: '/client/dashboard' },
  { label: '订单', icon: 'receipt_long', path: '/client/orders' },
  { label: '合约', icon: 'handshake', path: '/client/contracts' },
  { label: '账单', icon: 'account_balance_wallet', path: '/client/bills' },
  { label: '消息', icon: 'notifications', path: '/client/notifications' },
]

const isActive = (tab) => {
  if (tab.path === '/client/orders') {
    return route.path.startsWith('/client/orders') || route.path.startsWith('/client/receive')
  }
  if (tab.path === '/client/contracts') {
    return route.path.startsWith('/client/contracts') || route.path.startsWith('/client/tenders')
  }
  return route.path.startsWith(tab.path)
}

const pageTitle = () => {
  const p = route.path
  if (p.startsWith('/client/dashboard')) return '采购看板'
  if (p.startsWith('/client/orders/new')) return '新建订单'
  if (p.match(/^\/client\/orders\/\d+/)) return '订单详情'
  if (p.startsWith('/client/orders')) return '我的订单'
  if (p.startsWith('/client/receive')) return '确认收货'
  if (p.startsWith('/client/contracts/new')) return '发起招标'
  if (p.match(/^\/client\/contracts\/\d+\/bids/)) return '招标详情'
  if (p.startsWith('/client/contracts')) return '我的合约'
  if (p.startsWith('/client/tenders')) return '招标进度'
  if (p.startsWith('/client/bills')) return '我的账单'
  if (p.startsWith('/client/notifications')) return '消息中心'
  return '客户端'
}

const canBack = () => {
  const p = route.path
  return (
    p.match(/^\/client\/orders\/\d+/) != null ||
    p.startsWith('/client/orders/new') ||
    p.startsWith('/client/receive/') ||
    p.startsWith('/client/contracts/new') ||
    p.match(/^\/client\/contracts\/\d+\/bids/) != null ||
    p.startsWith('/client/tenders/')
  )
}

const goBack = () => router.back()
const goNotifications = () => router.push('/client/notifications')

const displayName = computed(() => userStore.userInfo?.username || userStore.userInfo?.company_name || '用户')
const avatarText = computed(() => String(displayName.value || 'U').slice(0, 1).toUpperCase())
const canteenLabel = computed(() => {
  const name = userStore.userInfo?.canteen_name
  const id = userStore.userInfo?.canteen_id
  if (id != null && name) return String(name)
  if (id != null) return '已选食堂'
  return ''
})

const passwordDialogVisible = ref(false)
const changingPassword = ref(false)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const resetPasswordForm = () => {
  passwordForm.old_password = ''
  passwordForm.new_password = ''
  passwordForm.confirm_password = ''
}
const openChangePassword = () => {
  resetPasswordForm()
  passwordDialogVisible.value = true
}
const submitChangePassword = async () => {
  if (!passwordForm.old_password.trim() || !passwordForm.new_password.trim() || !passwordForm.confirm_password.trim()) {
    ElMessage.warning('请完整填写密码信息')
    return
  }
  if (passwordForm.new_password.trim().length < 6) {
    ElMessage.warning('新密码长度不能少于6位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  changingPassword.value = true
  try {
    const res = await changePasswordApi({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    ElMessage.success(res?.message || '密码修改成功')
    passwordDialogVisible.value = false
    resetPasswordForm()
  } finally {
    changingPassword.value = false
  }
}

const onLogout = () => {
  notifStore.disconnect()
  userStore.logout()
  router.replace('/login')
}

const onUserCommand = (cmd) => {
  if (cmd === 'switch-canteen') {
    router.push({
      path: '/client/select-canteen',
      query: { repick: '1', redirect: route.fullPath },
    })
    return
  }
  if (cmd === 'change-password') {
    openChangePassword()
    return
  }
  if (cmd === 'logout') onLogout()
}
</script>

<template>
  <div class="m-shell">
    <header class="m-topbar">
      <button v-if="canBack()" class="m-topbar__back" @click="goBack">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <div class="m-topbar__title-wrap">
        <span class="m-topbar__title">{{ pageTitle() }}</span>
        <span v-if="canteenLabel" class="m-topbar__sub">{{ canteenLabel }}</span>
      </div>
      <button class="m-topbar__action" @click="goNotifications">
        <span class="material-symbols-outlined">notifications</span>
        <span v-if="notifStore.unread > 0" class="m-topbar__badge">{{ notifStore.unread > 99 ? '99+' : notifStore.unread }}</span>
      </button>
      <el-dropdown trigger="click" placement="bottom-end" @command="onUserCommand">
        <button class="m-topbar__avatar">{{ avatarText }}</button>
        <template #dropdown>
          <el-dropdown-menu class="m-user-menu">
            <el-dropdown-item disabled>
              <div class="m-user-menu__name">{{ displayName }}</div>
            </el-dropdown-item>
            <el-dropdown-item v-if="canteenLabel" disabled>
              <div class="m-user-menu__canteen">
                <span class="material-symbols-outlined m-user-menu__ico">restaurant</span>
                当前食堂：{{ canteenLabel }}
              </div>
            </el-dropdown-item>
            <el-dropdown-item divided command="switch-canteen">
              <span class="material-symbols-outlined m-user-menu__ico">swap_horiz</span>
              切换食堂
            </el-dropdown-item>
            <el-dropdown-item command="change-password">
              <span class="material-symbols-outlined m-user-menu__ico">lock_reset</span>
              更换密码
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              <span class="material-symbols-outlined m-user-menu__ico">logout</span>
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </header>

    <main class="m-content">
      <router-view />
    </main>

    <nav class="m-bottomnav">
      <button
        v-for="tab in tabs"
        :key="tab.path"
        class="m-bottomnav__tab"
        :class="{ 'is-active': isActive(tab) }"
        @click="router.push(tab.path)"
      >
        <span class="material-symbols-outlined m-bottomnav__icon">{{ tab.icon }}</span>
        <span class="m-bottomnav__label">{{ tab.label }}</span>
        <span v-if="tab.path === '/client/notifications' && notifStore.unread > 0" class="m-bottomnav__dot" />
      </button>
    </nav>
  </div>

  <el-dialog
    v-model="passwordDialogVisible"
    title="更换密码"
    :fullscreen="true"
    destroy-on-close
  >
    <el-form label-width="92px">
      <el-form-item label="旧密码">
        <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入旧密码" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="新密码（至少6位）" />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input
          v-model="passwordForm.confirm_password"
          type="password"
          show-password
          placeholder="请再次输入新密码"
          @keyup.enter="submitChangePassword"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="passwordDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="changingPassword" @click="submitChangePassword">确认</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.m-shell {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  background: var(--m-surface);
  font-family: var(--m-font-body);
  overflow: hidden;
}

.m-topbar {
  flex: none;
  height: 56px;
  background: linear-gradient(120deg, var(--m-primary) 0%, var(--m-primary-container) 100%);
  color: var(--m-on-primary);
  display: flex;
  align-items: center;
  padding: 0 8px 0 4px;
  gap: 4px;
  position: relative;
  z-index: 10;
  box-shadow: 0 2px 12px rgba(31, 122, 83, 0.28);
}

.m-topbar__back,
.m-topbar__action {
  width: 44px;
  height: 44px;
  border: none;
  background: transparent;
  color: inherit;
  border-radius: 50%;
  display: grid;
  place-items: center;
  cursor: pointer;
  flex: none;
  position: relative;
}

.m-topbar__title-wrap {
  flex: 1;
  min-width: 0;
  padding-left: 4px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  line-height: 1.15;
  overflow: hidden;
}

.m-topbar__title {
  font-family: var(--m-font-accent);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-topbar__sub {
  font-size: 11px;
  opacity: 0.78;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.m-topbar__badge {
  position: absolute;
  top: 6px;
  right: 6px;
  background: #ef4444;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
}

.m-topbar__avatar {
  width: 36px;
  height: 36px;
  border: 2px solid rgba(255, 255, 255, 0.45);
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  border-radius: 50%;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  flex: none;
  margin-left: 4px;
  font-family: var(--m-font-body);
}

.m-content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
}

.m-bottomnav {
  flex: none;
  height: 64px;
  background: var(--m-surface-container-lowest);
  border-top: 1px solid var(--m-outline-variant);
  display: flex;
  align-items: stretch;
  padding-bottom: env(safe-area-inset-bottom, 0px);
  box-shadow: 0 -2px 14px rgba(35, 39, 31, 0.05);
}

.m-bottomnav__tab {
  flex: 1;
  border: none;
  background: transparent;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  cursor: pointer;
  color: var(--m-on-surface-variant);
  transition: color 0.2s;
  position: relative;
  padding: 8px 4px 6px;
}

.m-bottomnav__tab.is-active {
  color: var(--m-primary);
}

/* 激活态：图标后一颗醒目的森绿胶囊高亮 */
.m-bottomnav__icon {
  font-size: 23px;
  font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
  display: grid;
  place-items: center;
  width: 60px;
  height: 32px;
  border-radius: 16px;
  transition: background 0.24s ease, color 0.24s ease, transform 0.24s ease;
}

.m-bottomnav__tab.is-active .m-bottomnav__icon {
  font-variation-settings: 'FILL' 1;
  color: var(--m-on-primary);
  background: linear-gradient(135deg, var(--m-primary) 0%, var(--m-primary-container) 100%);
  box-shadow: 0 4px 12px rgba(31, 122, 83, 0.36);
  transform: translateY(-1px);
}

.m-bottomnav__label {
  font-size: 11px;
  font-weight: 500;
  transition: font-weight 0.2s;
}

.m-bottomnav__tab.is-active .m-bottomnav__label {
  font-weight: 700;
}

.m-bottomnav__dot {
  position: absolute;
  top: 6px;
  right: calc(50% - 14px);
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
}
</style>

<style>
/* Unscoped — el-dropdown menu is teleported to body */
.m-user-menu .m-user-menu__name {
  font-weight: 700;
  color: var(--m-on-surface, #1a1b21);
  padding: 2px 4px;
}
.m-user-menu .m-user-menu__canteen {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--m-primary, #003286);
  font-size: 13px;
  padding: 2px 4px;
}
.m-user-menu .m-user-menu__ico {
  font-size: 18px;
  vertical-align: middle;
}
</style>
