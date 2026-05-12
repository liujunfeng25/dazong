<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Food, Switch } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { changePasswordApi } from '../api/auth'
import { getBeijingWeatherApi } from '../api/delivery'
import { useNotificationStore } from '../stores/notifications'
import { useUserStore } from '../stores/user'
import { formatChinaClock } from '../utils/datetime'

const props = defineProps({
  title: { type: String, default: '大宗供应链系统' },
  roleLabel: { type: String, default: '' },
})

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const notificationStore = useNotificationStore()
const nowText = ref('')
const passwordDialogVisible = ref(false)
const changingPassword = ref(false)
const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
})
const weather = ref({
  available: false,
  city: '北京',
  text: '',
  temperature: '',
  message: '',
})
let timer = null

const onLogout = () => {
  notificationStore.disconnect()
  userStore.logout()
  router.replace('/login')
}

const onOpenNotifications = () => {
  notificationStore.refresh()
}

const centerRoute = computed(() => {
  if (!userStore.role) return '/login'
  return `/${userStore.role}/notifications`
})

const recentItems = computed(() => notificationStore.viewItems.slice(0, 8))
const displayName = computed(() => userStore.userInfo?.username || userStore.userInfo?.company_name || '用户')
const avatarText = computed(() => String(displayName.value || 'U').slice(0, 1).toUpperCase())
const showWeather = computed(() => userStore.role === 'delivery')
const isClientPortal = computed(() => userStore.role === 'client')
const clientCanteenLabel = computed(() => {
  if (!isClientPortal.value) return ''
  const name = userStore.userInfo?.canteen_name
  const id = userStore.userInfo?.canteen_id
  if (id != null && name) return String(name)
  if (id != null) return '食堂已选'
  return ''
})
const weatherText = computed(() => {
  if (!weather.value.available) return '天气未接入'
  const t = weather.value.temperature ? `${weather.value.temperature}℃` : ''
  return `${weather.value.city} ${weather.value.text} ${t}`.trim()
})
const weatherIcon = computed(() => {
  const txt = String(weather.value?.text || '')
  if (!txt) return '🌤️'
  if (txt.includes('雷')) return '⛈️'
  if (txt.includes('雪') || txt.includes('冰')) return '🌨️'
  if (txt.includes('雨')) return '🌧️'
  if (txt.includes('雾') || txt.includes('霾') || txt.includes('沙')) return '🌫️'
  if (txt.includes('阴')) return '☁️'
  if (txt.includes('多云')) return '⛅'
  if (txt.includes('晴')) return '☀️'
  return '🌤️'
})

const goMessageCenter = () => {
  router.push({
    path: centerRoute.value,
    query: { _notify_refresh: String(Date.now()) },
  })
}

const onClickNotification = (item) => {
  if (item?.id) notificationStore.markReadOne(item.id)
  if (!item?.route) return
  const to = router.resolve(item.route)
  router.push({
    path: to.path,
    query: { ...to.query, _notify_refresh: String(Date.now()) },
  })
}

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

onMounted(() => {
  nowText.value = formatChinaClock()
  timer = setInterval(() => {
    nowText.value = formatChinaClock()
  }, 1000)
})

onMounted(async () => {
  if (!showWeather.value) return
  try {
    const res = await getBeijingWeatherApi()
    weather.value = { ...weather.value, ...(res || {}) }
  } catch (err) {
    weather.value.available = false
    weather.value.message = err?.message || '实时天气获取失败'
  }
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="h-18 px-5 pt-3">
    <div class="glass-card h-full px-5 flex items-center gap-3 min-h-[4.5rem]">
      <div class="header-left shrink-0">
        <div class="text-base font-semibold text-slate-900">{{ props.title }}</div>
        <div class="text-xs text-slate-500 mt-0.5">{{ nowText }}</div>
      </div>
      <div class="header-center flex-1 min-w-0 flex justify-center items-center px-2">
        <div v-if="showWeather" class="header-weather-inner">
          <el-tooltip
            :content="weather.available ? weatherText : weather.message || '天气未接入'"
            placement="bottom"
            effect="dark"
          >
            <span class="header-weather-chip">{{ weatherIcon }} {{ weatherText }}</span>
          </el-tooltip>
        </div>
        <div v-else-if="isClientPortal && clientCanteenLabel" class="client-canteen-ribbon">
          <div class="cc-icon-wrap cc-icon-wrap--on" aria-hidden="true">
            <el-icon :size="20"><Food /></el-icon>
          </div>
          <div class="cc-text">
            <span class="cc-kicker">当前履约食堂</span>
            <span class="cc-name">{{ clientCanteenLabel }}</span>
          </div>
        </div>
      </div>
      <div class="header-right shrink-0 flex items-center gap-3">
        <el-popover
          placement="bottom-end"
          :width="420"
          trigger="click"
          popper-class="notify-popover-panel"
          @show="onOpenNotifications"
        >
          <template #reference>
            <el-badge :value="notificationStore.unread" :hidden="!notificationStore.unread">
              <el-button size="small" plain class="notify-trigger">通知</el-button>
            </el-badge>
          </template>
          <div class="notify-popover">
            <div class="notify-topbar">
              <div>
                <div class="notify-headline">消息通知</div>
                <div class="notify-subtitle">未读 {{ notificationStore.unread }} 条</div>
              </div>
              <div class="notify-actions">
                <el-button link size="small" @click="notificationStore.markAllRead">全部已读</el-button>
                <el-button link size="small" @click="goMessageCenter">消息中心</el-button>
              </div>
            </div>
            <div class="notify-list">
              <div v-if="notificationStore.loading" class="notify-empty">正在加载...</div>
              <div v-else-if="!recentItems.length" class="notify-empty">暂无通知</div>
              <div
                v-for="(item, idx) in recentItems"
                :key="idx"
                class="notify-item"
                :class="{ unread: !item.is_read }"
                @click="onClickNotification(item)"
              >
                <div class="notify-item-top">
                  <div class="notify-title">{{ item.title || '消息提醒' }}</div>
                  <div class="notify-time">{{ item.time_text || '' }}</div>
                </div>
                <div class="notify-content">{{ item.content || '有新的业务动态，请查看。' }}</div>
                <div class="notify-meta">{{ item.event_label || '系统通知' }}</div>
              </div>
            </div>
            <div v-if="recentItems.length" class="notify-footer">
              <el-button text type="primary" @click="goMessageCenter">查看全部消息</el-button>
            </div>
          </div>
        </el-popover>
        <span class="role-chip px-3 py-1 text-xs rounded-full border">{{ props.roleLabel }}</span>
        <el-dropdown trigger="click" @command="onUserCommand">
          <div class="user-avatar-wrap">
            <el-avatar size="small" class="default-avatar">{{ avatarText }}</el-avatar>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>{{ displayName }}</el-dropdown-item>
              <el-dropdown-item v-if="isClientPortal" command="switch-canteen">
                <span class="dropdown-canteen-row">
                  <el-icon class="dropdown-canteen-ico"><Switch /></el-icon>
                  切换食堂
                </span>
              </el-dropdown-item>
              <el-dropdown-item command="change-password">更换密码</el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>
  </div>
  <el-dialog v-model="passwordDialogVisible" title="更换密码" width="420px">
    <el-form label-width="92px">
      <el-form-item label="旧密码">
        <el-input v-model="passwordForm.old_password" type="password" show-password placeholder="请输入旧密码" />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="passwordForm.new_password" type="password" show-password placeholder="请输入新密码（至少6位）" />
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
.role-chip {
  background: color-mix(in srgb, var(--role-accent, #4f7cff) 12%, #ffffff 88%);
  color: color-mix(in srgb, var(--role-accent, #4f7cff) 88%, #0f172a 12%);
  border-color: color-mix(in srgb, var(--role-accent, #4f7cff) 22%, #ffffff 78%);
}

.notify-trigger {
  min-width: 64px;
}

.user-avatar-wrap {
  cursor: pointer;
  display: flex;
  align-items: center;
}

.default-avatar {
  background: color-mix(in srgb, var(--role-accent, #4f7cff) 84%, #ffffff 16%);
  color: #fff;
}

.dropdown-canteen-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.dropdown-canteen-ico {
  font-size: 16px;
}

.header-weather-inner {
  display: flex;
  justify-content: center;
  max-width: 100%;
}

.client-canteen-ribbon {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  max-width: min(520px, 100%);
  padding: 10px 20px 10px 16px;
  border-radius: 14px;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--role-accent, #4f7cff) 14%, #ffffff 86%) 0%,
    color-mix(in srgb, var(--role-accent, #4f7cff) 6%, #f8fafc 94%) 100%
  );
  border: 1px solid color-mix(in srgb, var(--role-accent, #4f7cff) 28%, #e2e8f0 72%);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.75) inset,
    0 8px 22px color-mix(in srgb, var(--role-accent, #4f7cff) 12%, transparent);
}

.cc-icon-wrap {
  flex-shrink: 0;
  width: 2.5rem;
  height: 2.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(148, 163, 184, 0.35);
  color: #64748b;
}

.cc-icon-wrap--on {
  color: color-mix(in srgb, var(--role-accent, #4f7cff) 88%, #1e293b 12%);
  border-color: color-mix(in srgb, var(--role-accent, #4f7cff) 38%, #e2e8f0 62%);
  background: rgba(255, 255, 255, 0.95);
}

.cc-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.cc-kicker {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: none;
  color: color-mix(in srgb, var(--role-accent, #4f7cff) 55%, #64748b 45%);
}

.cc-name {
  font-size: 1.125rem;
  font-weight: 700;
  line-height: 1.35;
  color: #0f172a;
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-weather-chip {
  font-size: 12px;
  line-height: 1;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(14, 165, 233, 0.1);
  color: #0f172a;
  border: 1px solid rgba(14, 165, 233, 0.22);
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

</style>
