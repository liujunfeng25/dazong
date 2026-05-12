<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listMyTendersApi, tenderMetaApi } from '../../api/contracts'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const list = ref([])
const categoryNameMap = ref({})
const deliveryNameMap = ref({})
const categoryNames = (row) =>
  (row.category_ids_json || []).map((id) => categoryNameMap.value[id] || `一级分类#${id}`).join('、')
const deliveryNames = (row) =>
  (row.delivery_ids_json || []).map((id) => deliveryNameMap.value[id] || `配送方#${id}`).join('、')
const statusType = computed(() => ({ 招标中: 'warning', 已中标: 'success', 已关闭: 'info' }))

const load = async () => {
  loading.value = true
  try {
    const [rows, meta] = await Promise.all([listMyTendersApi(), tenderMetaApi()])
    list.value = rows
    categoryNameMap.value = Object.fromEntries((meta.level1_categories || []).map((i) => [i.id, i.name]))
    deliveryNameMap.value = Object.fromEntries(
      (meta.deliveries || []).map((i) => [i.id, i.company_name || i.username || `配送方#${i.id}`]),
    )
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <el-card>
    <el-table v-loading="loading" :data="list" border empty-text="暂无招标记录，先去发起招标">
      <el-table-column prop="id" label="招标编号" width="100" />
      <el-table-column label="一级分类" min-width="280">
        <template #default="{ row }">
          {{ categoryNames(row) || '—' }}
        </template>
      </el-table-column>
      <el-table-column label="邀请配送方" min-width="220">
        <template #default="{ row }">{{ deliveryNames(row) }}</template>
      </el-table-column>
      <el-table-column prop="bid_count" label="已报价数" width="100" />
      <el-table-column prop="status" label="进度" width="120">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status] || 'info'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="period_start" label="开始" min-width="120" />
      <el-table-column prop="period_end" label="结束" min-width="120" />
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="router.push(`/client/contracts/${row.id}/bids`)">
            查看报价 / 选择中标
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
