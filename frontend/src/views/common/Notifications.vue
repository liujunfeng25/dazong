<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useNotificationStore } from '../../stores/notifications'

const route = useRoute()
const router = useRouter()
const notificationStore = useNotificationStore()

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
  const to = router.resolve(item.route)
  await router.push({
    path: to.path,
    query: { ...to.query, _notify_refresh: String(Date.now()) },
  })
}

onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
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
</style>
