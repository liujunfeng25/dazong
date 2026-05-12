<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { awardTenderApi, listTenderBidsApi } from '../../api/contracts'
import { formatChinaDateTime } from '../../utils/datetime'

const route = useRoute()
const router = useRouter()
const list = ref([])
const loading = ref(false)
const awarding = ref(false)
const load = async () => {
  loading.value = true
  try {
    const bids = await listTenderBidsApi(route.params.id)
    list.value = bids
  } finally {
    loading.value = false
  }
}
const award = async (deliveryId) => {
  if (awarding.value) return
  await ElMessageBox.confirm('确认将该配送单位设为中标吗？确认后将生成合约并结束本次招标。', '中标确认', {
    type: 'warning',
    confirmButtonText: '确认中标',
    cancelButtonText: '取消',
    customClass: 'award-confirm-dialog',
    confirmButtonClass: 'award-confirm-btn',
    cancelButtonClass: 'award-cancel-btn',
  })
  awarding.value = true
  try {
    await awardTenderApi(route.params.id, { delivery_id: deliveryId })
    ElMessage.success('中标已确认，正在跳转到我的合约')
    router.push('/client/contracts')
  } finally {
    awarding.value = false
  }
}
onMounted(load)
watch(() => route.fullPath, load)
</script>

<template>
  <el-table v-loading="loading" :data="list" border>
    <el-table-column type="expand" width="50">
      <template #default="{ row }">
        <div class="category-rates">
          <div class="category-rates-title">分类报价明细</div>
          <div v-if="(row.category_rates || []).length" class="category-rate-list">
            <span v-for="item in row.category_rates" :key="`${row.delivery_id}-${item.category_id}`" class="rate-chip">
              {{ item.category_name || `分类#${item.category_id}` }}：{{ Number(item.float_rate || 0).toFixed(4) }}
            </span>
          </div>
          <div v-else class="category-rates-empty">暂无分类报价明细</div>
        </div>
      </template>
    </el-table-column>
    <el-table-column label="配送单位" min-width="180">
      <template #default="{ row }">
        {{ row.delivery_name || `配送方#${row.delivery_id}` }}
      </template>
    </el-table-column>
    <el-table-column prop="price_float_rate" label="上浮率" width="140">
      <template #default="{ row }">{{ Number(row.price_float_rate || 0).toFixed(4) }}</template>
    </el-table-column>
    <el-table-column label="报价时间" min-width="180">
      <template #default="{ row }">{{ formatChinaDateTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="操作" width="140" align="center">
      <template #default="{ row }">
        <el-button size="small" type="primary" :loading="awarding" :disabled="awarding" @click="award(row.delivery_id)">
          中标
        </el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.category-rates {
  padding: 4px 8px;
}
.category-rates-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.category-rate-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.rate-chip {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #334155;
}
.category-rates-empty {
  color: #94a3b8;
}
</style>
