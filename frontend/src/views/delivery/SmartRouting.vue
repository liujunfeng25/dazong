<script setup>
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import RoutePlanPanel from './RoutePlanPanel.vue'
import ElectronicFence from './ElectronicFence.vue'

const route = useRoute()
const router = useRouter()
const activeTab = ref(String(route.query.tab) === 'fence' ? 'fence' : 'route')

watch(
  () => route.query.tab,
  (t) => {
    activeTab.value = t === 'fence' ? 'fence' : 'route'
  },
)

const onTabChange = (name) => {
  if (name === 'fence') {
    router.replace({ path: route.path, query: { tab: 'fence' } })
  } else {
    router.replace({ path: route.path, query: {} })
  }
}
</script>

<template>
  <div class="smart-routing-page">
    <el-tabs v-model="activeTab" class="smart-routing-tabs" @tab-change="onTabChange">
      <el-tab-pane label="路线规划" name="route" lazy>
        <RoutePlanPanel />
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
