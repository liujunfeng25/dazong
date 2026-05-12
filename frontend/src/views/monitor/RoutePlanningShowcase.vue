<script setup>
import { computed, onMounted, ref } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { monitorRoutePlanningShowcaseApi } from '../../api/monitor'

const loading = ref(false)
const data = ref({
  summary: {},
  route_cards: [],
  capability_cards: [],
  roadmap: [],
})

const onTimeRateText = computed(() => {
  const rate = Number(data.value?.summary?.estimated_on_time_rate || 0)
  if (!rate) return '-'
  return `${(rate * 100).toFixed(1)}%`
})

const onTimeRateNote = computed(
  () =>
    data.value?.summary?.estimated_on_time_rate_note ||
    '【一期】规划期示意值：由坐标覆盖率等规则合成，非基于历史送达的预测模型，便于汇报演示占位。【二期】接入签收与实际到达时间，按客户约定窗统计真实准点率，或再建设准点概率预测模型。',
)

const load = async () => {
  loading.value = true
  try {
    data.value = await monitorRoutePlanningShowcaseApi()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <el-row :gutter="12" v-loading="loading">
    <el-col :span="24">
      <el-card>
        <template #header>
          <span>路线规划价值看板（甲方/老板汇报）</span>
        </template>
        <el-alert
          class="mb-2"
          type="info"
          :closable="false"
          title="数据来自线上订单与在途配送记录摘要；配送端规划已统一为高德驾车路径与 ETA（接口失败时后端降级）。"
        />
        <div class="kpi-grid">
          <div class="kpi-item">
            <div class="kpi-label">活跃路线</div>
            <div class="kpi-value">{{ data.summary?.active_routes ?? '-' }}</div>
          </div>
          <div class="kpi-item">
            <div class="kpi-label">节省里程</div>
            <div class="kpi-value">{{ data.summary?.distance_saved_km ?? '-' }} km</div>
          </div>
          <div class="kpi-item">
            <div class="kpi-label">节省时长</div>
            <div class="kpi-value">{{ data.summary?.duration_saved_minutes ?? '-' }} 分钟</div>
          </div>
          <div class="kpi-item kpi-item--wide-note">
            <div class="kpi-label kpi-label--row">
              <span>准点率示意（一期）</span>
              <el-tooltip placement="top" effect="dark" :content="onTimeRateNote" :max-width="420">
                <el-icon class="cursor-help text-slate-400 kpi-help-ico"><QuestionFilled /></el-icon>
              </el-tooltip>
            </div>
            <div class="kpi-value">{{ onTimeRateText }}</div>
            <div class="kpi-note">{{ onTimeRateNote }}</div>
          </div>
          <div class="kpi-item">
            <div class="kpi-label">在途载重总量</div>
            <div class="kpi-value">{{ data.summary?.total_weight_kg ?? '-' }} kg</div>
          </div>
          <div class="kpi-item">
            <div class="kpi-label">在途体积总量</div>
            <div class="kpi-value">{{ data.summary?.total_volume_m3 ?? '-' }} m3</div>
          </div>
        </div>
      </el-card>
    </el-col>

    <el-col :span="14">
      <el-card class="mt-3">
        <template #header>路线执行卡片</template>
        <el-table :data="data.route_cards || []" border size="small">
          <el-table-column prop="route_no" label="路线编号" min-width="120" />
          <el-table-column prop="vehicle_no" label="车辆" min-width="120" />
          <el-table-column prop="delivery_name" label="配送商" min-width="160" />
          <el-table-column prop="distance_km" label="里程(km)" width="100" />
          <el-table-column prop="status" label="状态" width="100" />
        </el-table>
      </el-card>
    </el-col>
    <el-col :span="10">
      <el-card class="mt-3">
        <template #header>能力清单（当前可讲）</template>
        <el-timeline>
          <el-timeline-item v-for="item in data.capability_cards || []" :key="item.title">
            <div class="font-semibold">{{ item.title }}</div>
            <div class="text-slate-500 text-xs mt-1">{{ item.desc }}</div>
          </el-timeline-item>
        </el-timeline>
      </el-card>
      <el-card class="mt-3">
        <template #header>演进路线</template>
        <el-steps direction="vertical" :active="3">
          <el-step v-for="item in data.roadmap || []" :key="item.stage" :title="item.stage" :description="item.value" />
        </el-steps>
      </el-card>
    </el-col>
  </el-row>
</template>

<style scoped>
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.kpi-item {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  background: #f8fafc;
}
.kpi-label {
  color: #64748b;
  font-size: 12px;
}
.kpi-value {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
}
.kpi-item--wide-note {
  grid-column: span 3;
}
.kpi-label--row {
  display: flex;
  align-items: center;
  gap: 4px;
}
.kpi-help-ico {
  font-size: 14px;
}
.kpi-note {
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.45;
  color: #64748b;
}
</style>
