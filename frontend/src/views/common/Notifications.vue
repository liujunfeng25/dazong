<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNotificationStore } from '../../stores/notifications'
import { resolveNotificationRoute } from '../../utils/notificationRoute'
import { useUserStore } from '../../stores/user'
import { useIsMobile } from '../../composables/useIsMobile'

const route = useRoute()
const router = useRouter()
const notificationStore = useNotificationStore()
const userStore = useUserStore()
const { isMobile } = useIsMobile()

const unreadOnly = ref(false)
const eventType = ref('')
const keyword = ref('')

const eventOptions = computed(() =>
  Object.entries(notificationStore.eventTypeLabelMap).map(([value, label]) => ({ value, label })),
)

const list = computed(() =>
  notificationStore.getFilteredItems({
    unreadOnly: unreadOnly.value,
    eventType: eventType.value,
    keyword: keyword.value,
  }),
)

const load = async () => {
  await notificationStore.refresh()
}

const openItem = async (item) => {
  if (item?.id) await notificationStore.markReadOne(item.id)
  if (!item?.route) return
  const to = resolveNotificationRoute(router, userStore.role, item.route)
  await router.push({
    path: to.path,
    query: { ...to.query, _notify_refresh: String(Date.now()) },
  })
}

onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-page">
    <div class="m-notif-header">
      <div class="m-notif-header__counts">
        共 {{ list.length }} 条，未读 <strong>{{ notificationStore.unread }}</strong> 条
      </div>
      <button class="m-notif-mark-all" @click="notificationStore.markAllRead">全部已读</button>
    </div>

    <div class="m-filter-bar">
      <button class="m-filter-chip" :class="{ 'is-active': !unreadOnly }" @click="unreadOnly = false">全部</button>
      <button class="m-filter-chip" :class="{ 'is-active': unreadOnly }" @click="unreadOnly = true">仅未读</button>
      <el-input v-model="keyword" clearable placeholder="搜索" size="small" style="flex:1;min-width:80px" />
    </div>

    <div v-if="notificationStore.loading" class="m-notif-empty">加载中...</div>
    <div v-else-if="!list.length" class="m-notif-empty">暂无消息</div>
    <div v-else class="m-notif-list">
      <div
        v-for="item in list"
        :key="`${item.id}-${item.created_at}`"
        class="m-notif-item"
        :class="[`tone-${item.event_meta?.tone || 'general'}`, { unread: !item.is_read }]"
        @click="openItem(item)"
      >
        <div class="m-notif-icon" :class="{ unread: !item.is_read }">{{ item.event_meta?.icon || '系' }}</div>
        <div class="m-notif-body">
          <div class="m-notif-title">{{ item.title || '消息提醒' }}</div>
          <div class="m-notif-content">{{ item.content || '有新的业务动态，请查看。' }}</div>
          <div class="m-notif-footer">
            <span class="m-notif-tag">{{ item.event_label || '系统通知' }}</span>
            <span class="m-notif-time">{{ item.time_text || '' }}</span>
          </div>
        </div>
        <div v-if="!item.is_read" class="m-notif-dot" />
      </div>
    </div>
  </div>

  <!-- ── PC ── -->
  <template v-else>
  <el-card class="mb-3">
    <div class="notify-toolbar">
      <div class="notify-toolbar-left">
        <el-input v-model="keyword" clearable placeholder="搜索标题或内容" style="width: 260px" />
        <el-select v-model="eventType" clearable placeholder="全部类型" style="width: 180px">
          <el-option v-for="item in eventOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-switch v-model="unreadOnly" inline-prompt active-text="仅未读" inactive-text="全部" />
      </div>
      <div class="notify-toolbar-right">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" plain @click="notificationStore.markAllRead">全部已读</el-button>
      </div>
    </div>
  </el-card>

  <el-card>
    <template #header>
      <div class="notify-center-header">
        <span class="font-semibold">消息中心</span>
        <span class="notify-count">共 {{ list.length }} 条，未读 {{ notificationStore.unread }} 条</span>
      </div>
    </template>

    <div v-if="notificationStore.loading" class="notify-center-empty">正在加载消息...</div>
    <div v-else-if="!list.length" class="notify-center-empty">暂无符合条件的消息</div>
    <div v-else class="notify-center-list">
      <div
        v-for="item in list"
        :key="`${item.id}-${item.created_at}`"
        class="notify-center-item"
        :class="[`tone-${item.event_meta?.tone || 'general'}`, { unread: !item.is_read }]"
        @click="openItem(item)"
      >
        <div class="notify-center-dot">{{ item.event_meta?.icon || '系' }}</div>
        <div class="notify-center-main">
          <div class="notify-center-top">
            <div class="notify-center-title">{{ item.title || '消息提醒' }}</div>
            <div class="notify-center-time">{{ item.time_text || '' }}</div>
          </div>
          <div class="notify-center-content">{{ item.content || '有新的业务动态，请查看。' }}</div>
          <div class="notify-center-tag">{{ item.event_label || '系统通知' }}</div>
        </div>
      </div>
    </div>
  </el-card>
  </template>
</template>

<style scoped>
.notify-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.notify-toolbar-left,
.notify-toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.notify-center-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.notify-count {
  font-size: 12px;
  color: #64748b;
}

.notify-center-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 36px 10px;
}

.notify-center-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.notify-center-item {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #fff;
  padding: 12px;
  cursor: pointer;
  display: flex;
  gap: 10px;
}

.notify-center-item.unread {
  border-left: 3px solid #3b82f6;
  background: #f8fbff;
}

.notify-center-dot {
  width: 20px;
  height: 20px;
  margin-top: 2px;
  border-radius: 999px;
  background: #cbd5e1;
  flex-shrink: 0;
  color: #fff;
  font-size: 12px;
  line-height: 20px;
  text-align: center;
  font-weight: 700;
}

.notify-center-item.unread .notify-center-dot {
  background: #3b82f6;
}

.notify-center-item.tone-fulfillment.unread {
  border-left-color: #2563eb;
  background: #eff6ff;
}

.notify-center-item.tone-fulfillment .notify-center-dot {
  background: #2563eb;
}

.notify-center-item.tone-bill-create.unread {
  border-left-color: #0f766e;
  background: #ecfdf5;
}

.notify-center-item.tone-bill-create .notify-center-dot {
  background: #0f766e;
}

.notify-center-item.tone-bill-receive.unread {
  border-left-color: #0f766e;
  background: #ecfdf5;
}

.notify-center-item.tone-bill-receive .notify-center-dot {
  background: #0f766e;
}

.notify-center-item.tone-bill-pay.unread {
  border-left-color: #d97706;
  background: #fffbeb;
}

.notify-center-item.tone-bill-pay .notify-center-dot {
  background: #d97706;
}

.notify-center-item.tone-bill-settle.unread {
  border-left-color: #15803d;
  background: #f0fdf4;
}

.notify-center-item.tone-bill-settle .notify-center-dot {
  background: #15803d;
}

.notify-center-item.tone-procurement.unread {
  border-left-color: #7c3aed;
  background: #f5f3ff;
}

.notify-center-item.tone-procurement .notify-center-dot {
  background: #7c3aed;
}

.notify-center-item.tone-important.unread {
  border-left-color: #b91c1c;
  background: #fef2f2;
}

.notify-center-item.tone-important .notify-center-dot {
  background: #b91c1c;
}

.notify-center-item.tone-general.unread {
  border-left-color: #475569;
  background: #f8fafc;
}

.notify-center-item.tone-general .notify-center-dot {
  background: #475569;
}

.notify-center-main {
  flex: 1;
  min-width: 0;
}

.notify-center-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.notify-center-title {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.notify-center-time {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

.notify-center-content {
  margin-top: 4px;
  font-size: 13px;
  color: #64748b;
}

.notify-center-tag {
  margin-top: 6px;
  font-size: 12px;
  color: #475569;
}

/* ── Mobile styles ── */
.m-page {
  font-family: var(--m-font-body);
  min-height: 100%;
  padding-bottom: 16px;
}
.m-notif-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--m-surface-container-lowest);
  border-bottom: 1px solid var(--m-outline-variant);
}
.m-notif-header__counts {
  font-size: 13px;
  color: var(--m-on-surface-variant);
}
.m-notif-mark-all {
  border: none;
  background: transparent;
  color: var(--m-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--m-font-body);
}
.m-filter-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 10px 16px;
  background: var(--m-surface-container-low);
  border-bottom: 1px solid var(--m-outline-variant);
}
.m-filter-chip {
  padding: 5px 14px;
  border-radius: 20px;
  border: 1.5px solid var(--m-outline-variant);
  background: transparent;
  color: var(--m-on-surface-variant);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  flex: none;
  font-family: var(--m-font-body);
  transition: all 0.18s;
}
.m-filter-chip.is-active {
  background: var(--m-primary);
  border-color: var(--m-primary);
  color: var(--m-on-primary);
}
.m-notif-list {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.m-notif-item {
  background: var(--m-surface-container-lowest);
  border: 1px solid var(--m-outline-variant);
  border-radius: 12px;
  display: flex;
  gap: 10px;
  padding: 12px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
}
.m-notif-item.unread {
  border-left: 3px solid var(--m-primary);
  background: #f5f9ff;
}
.m-notif-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--m-surface-container-high);
  color: var(--m-on-surface-variant);
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  flex: none;
}
.m-notif-icon.unread {
  background: var(--m-primary);
  color: var(--m-on-primary);
}
.m-notif-item.tone-important .m-notif-icon { background: #fef2f2; color: #b91c1c; }
.m-notif-item.tone-important.unread .m-notif-icon { background: #b91c1c; color: #fff; }
.m-notif-item.tone-procurement .m-notif-icon { background: #f5f3ff; color: #7c3aed; }
.m-notif-item.tone-procurement.unread .m-notif-icon { background: #7c3aed; color: #fff; }
.m-notif-item.tone-bill-settle .m-notif-icon { background: #f0fdf4; color: #15803d; }
.m-notif-item.tone-bill-settle.unread .m-notif-icon { background: #15803d; color: #fff; }
.m-notif-item.tone-fulfillment .m-notif-icon { background: #eff6ff; color: #2563eb; }
.m-notif-item.tone-fulfillment.unread .m-notif-icon { background: #2563eb; color: #fff; }
.m-notif-body { flex: 1; min-width: 0; }
.m-notif-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--m-on-surface);
  margin-bottom: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-notif-content {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  line-height: 1.5;
  margin-bottom: 4px;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.m-notif-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.m-notif-tag {
  font-size: 11px;
  background: var(--m-secondary-fixed);
  color: var(--m-primary);
  padding: 2px 8px;
  border-radius: 8px;
  font-weight: 600;
}
.m-notif-time {
  font-size: 11px;
  color: var(--m-on-surface-variant);
  white-space: nowrap;
}
.m-notif-dot {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 8px;
  height: 8px;
  background: var(--m-primary);
  border-radius: 50%;
}
.m-notif-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 48px 16px;
  font-size: 14px;
}
</style>
