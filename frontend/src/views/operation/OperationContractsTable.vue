<script setup>
import { QuestionFilled } from '@element-plus/icons-vue'
import { contractDbStatusTagType, contractLifecycleTagType } from '../../utils/contractStatus'

defineProps({
  data: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  /** 看板紧凑模式：列略少、字号略小 */
  compact: { type: Boolean, default: false },
  /** 是否展示「定标状态」（招标中/已中标/已过期）列 */
  showDbStatus: { type: Boolean, default: true },
})

const emit = defineEmits(['view-contract', 'view-order'])

const money = (v) => `¥${Number(v || 0).toLocaleString()}`

const periodText = (row) => {
  const a = row.period_start || ''
  const b = row.period_end || ''
  return a && b ? `${a} ~ ${b}` : '—'
}
</script>

<template>
  <el-table
    v-loading="loading"
    :data="data"
    border
    :size="compact ? 'small' : 'default'"
    class="op-contracts-table"
    @row-click="(row) => emit('view-contract', row)"
  >
    <el-table-column prop="contract_no" label="合约号" min-width="120" />
    <el-table-column prop="client_name" label="采购方" min-width="130" show-overflow-tooltip />
    <el-table-column prop="delivery_name" label="配送方" min-width="130" show-overflow-tooltip />
    <el-table-column label="合约期" min-width="200">
      <template #default="{ row }">{{ periodText(row) }}</template>
    </el-table-column>
    <el-table-column prop="lifecycle_status" label="生命周期" width="110" align="center">
      <template #default="{ row }">
        <el-tag :type="contractLifecycleTagType(row.lifecycle_status)" size="small" effect="dark">
          {{ row.lifecycle_status || '—' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="showDbStatus" prop="status" width="120" align="center">
      <template #header>
        <span>定标状态</span>
        <el-tooltip
          placement="top"
          content="指合约在系统里的登记阶段：招标中、已定标（已中标）、或整单已记为过期。与「生命周期」不同：后者按合约起止日期和今天是否在约内等综合显示（例如已定标但未到合约开始日，生命周期可为「待生效」）。"
        >
          <el-icon class="header-tip-icon"><QuestionFilled /></el-icon>
        </el-tooltip>
      </template>
      <template #default="{ row }">
        <el-tag :type="contractDbStatusTagType(row.status)" size="small" effect="plain">
          {{ row.status || '—' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="订单数" width="88" align="right">
      <template #default="{ row }">{{ Number(row.order_count || 0).toLocaleString() }}</template>
    </el-table-column>
    <el-table-column label="订单金额" width="120" align="right">
      <template #default="{ row }">{{ money(row.order_total_amount) }}</template>
    </el-table-column>
    <el-table-column v-if="!compact" label="操作" width="100" align="center" @click.stop>
      <template #default="{ row }">
        <el-button type="primary" link @click.stop="emit('view-contract', row)">详情</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<style scoped>
.op-contracts-table :deep(.el-table__body tr) {
  cursor: pointer;
}

.header-tip-icon {
  margin-left: 4px;
  vertical-align: -2px;
  color: #94a3b8;
  cursor: help;
}
</style>
