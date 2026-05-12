<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listTenderApi, tenderMetaApi } from '../../api/contracts'

const router = useRouter()
const route = useRoute()
const list = ref([])
const categoryNameMap = ref({})
const categoryNames = (row) =>
  (row.category_ids_json || []).map((id) => categoryNameMap.value[id] || `一级分类#${id}`).join('、')
const load = async () => {
  const [rows, meta] = await Promise.all([listTenderApi(), tenderMetaApi()])
  list.value = rows
  categoryNameMap.value = Object.fromEntries((meta.level1_categories || []).map((i) => [i.id, i.name]))
}
onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <el-table :data="list" border>
    <el-table-column prop="id" label="招标编号" width="100" />
    <el-table-column prop="client_name" label="客户名称" min-width="180" />
    <el-table-column label="一级分类" min-width="260">
      <template #default="{ row }">
        {{ categoryNames(row) || '—' }}
      </template>
    </el-table-column>
    <el-table-column label="已报上浮率" width="140">
      <template #default="{ row }">
        {{ row.my_bid_float_rate == null ? '—' : Number(row.my_bid_float_rate).toFixed(4) }}
      </template>
    </el-table-column>
    <el-table-column prop="status" label="状态" />
    <el-table-column prop="period_start" label="开始" />
    <el-table-column prop="period_end" label="结束" />
    <el-table-column label="操作">
      <template #default="{ row }">
        <el-button size="small" @click="router.push(`/delivery/tenders/${row.id}`)">投标</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>
