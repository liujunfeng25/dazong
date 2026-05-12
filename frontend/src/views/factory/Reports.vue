<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listQualityReportsApi } from '../../api/qualityReports'
import { formatChinaDateTime } from '../../utils/datetime'

const list = ref([])
const loading = ref(false)
const router = useRouter()

const load = async () => {
  loading.value = true
  try {
    list.value = await listQualityReportsApi()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <span class="font-semibold">质检报告</span>
      <div class="crud-actions">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="router.push('/factory/reports/upload')">上传报告</el-button>
      </div>
    </div>
  </el-card>

  <el-card>
    <el-table v-loading="loading" :data="list" border>
      <el-table-column prop="report_no" label="报告编号" min-width="160" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === '待审核' ? 'warning' : 'success'">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="file_url" label="报告文件" min-width="300">
        <template #default="{ row }">
          <el-link :href="row.file_url" target="_blank" type="primary">查看文件</el-link>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" min-width="190">
        <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.crud-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
