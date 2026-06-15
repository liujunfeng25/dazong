<script setup>
import { computed } from 'vue'
import { ys7BatteryFromRow, ys7BatteryLevel, ys7MetaFromRow } from '../utils/ys7DeviceMeta'

const props = defineProps({
  row: { type: Object, default: null },
  compact: { type: Boolean, default: false },
  showSignal: { type: Boolean, default: false },
})

const meta = computed(() => ys7MetaFromRow(props.row))
const percent = computed(() => ys7BatteryFromRow(props.row))
const level = computed(() => ys7BatteryLevel(percent.value))

const progressStatus = computed(() => {
  if (level.value === 'low') return 'exception'
  if (level.value === 'medium') return 'warning'
  return 'success'
})

const show = computed(() => meta.value.powerKind === 'battery')
</script>

<template>
  <div v-if="show" class="ys7-battery" :class="{ 'ys7-battery--compact': compact }">
    <template v-if="percent != null">
      <el-progress
        :percentage="percent"
        :status="progressStatus"
        :stroke-width="compact ? 6 : 8"
        :show-text="!compact"
      />
      <span v-if="compact" class="ys7-battery-pct">{{ percent }}%</span>
      <span
        v-if="showSignal && row?.ys7_signal != null"
        class="ys7-battery-signal"
      >信号 {{ row.ys7_signal }}</span>
    </template>
    <span v-else class="ys7-battery-unknown">电量未知</span>
  </div>
  <span v-else class="text-slate-400">—</span>
</template>

<style scoped>
.ys7-battery {
  min-width: 88px;
}

.ys7-battery--compact {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ys7-battery--compact :deep(.el-progress) {
  flex: 1;
  min-width: 56px;
}

.ys7-battery-pct {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  white-space: nowrap;
}

.ys7-battery-unknown {
  font-size: 12px;
  color: #94a3b8;
}

.ys7-battery-signal {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
}
</style>
