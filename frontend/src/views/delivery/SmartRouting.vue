<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RoutePlanPanel from './RoutePlanPanel.vue'
import ElectronicFence from './ElectronicFence.vue'
import DispatchTrips from './DispatchTrips.vue'

const route = useRoute()
const router = useRouter()
const resolveTab = (tab) => {
  if (tab === 'fence') return 'fence'
  if (tab === 'dispatch') return 'dispatch'
  return 'route'
}
const activeTab = ref(resolveTab(String(route.query.tab || '')))

watch(
  () => route.query.tab,
  (t) => {
    activeTab.value = resolveTab(String(t || ''))
  },
)

const onTabChange = (name) => {
  if (name === 'fence') {
    router.replace({ path: route.path, query: { tab: 'fence' } })
  } else if (name === 'dispatch') {
    const query = { tab: 'dispatch' }
    if (route.query.date) query.date = route.query.date
    if (route.query.status) query.status = route.query.status
    router.replace({ path: route.path, query })
  } else {
    const query = {}
    if (route.query.date) query.date = route.query.date
    router.replace({ path: route.path, query })
  }
}
</script>

<template>
  <div class="smart-routing-page">
    <el-tabs v-model="activeTab" class="smart-routing-tabs" @tab-change="onTabChange">
      <el-tab-pane label="路线规划" name="route" lazy>
        <RoutePlanPanel />
      </el-tab-pane>
      <el-tab-pane label="发车计划" name="dispatch" lazy>
        <DispatchTrips />
      </el-tab-pane>
      <el-tab-pane label="电子围栏" name="fence" lazy>
        <ElectronicFence />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.smart-routing-page {
  padding: 0 4px;
}
.smart-routing-tabs :deep(.el-tabs__header) {
  margin-bottom: 12px;
}
</style>
