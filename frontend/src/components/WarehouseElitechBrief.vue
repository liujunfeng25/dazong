<script setup>
import { computed } from 'vue'
import { elitechFormatValue } from '../utils/elitechDeviceMeta'

const props = defineProps({
  warehouse: { type: Object, default: null },
  /** card：详情抽屉；inline：表格/列表 */
  variant: { type: String, default: 'inline' },
})

const bound = computed(() =>
  Boolean(props.warehouse?.elitech_bound || props.warehouse?.elitech_sn),
)
</script>

<template>
  <div v-if="bound" class="wh-elitech-brief" :class="`wh-elitech-brief--${variant}`">
    <div class="wh-elitech-brief-main">
      <span class="wh-elitech-temp">{{ elitechFormatValue(warehouse.elitech_temperature, '℃') }}</span>
      <span class="wh-elitech-sep">/</span>
      <span class="wh-elitech-hum">{{ elitechFormatValue(warehouse.elitech_humidity, '%RH') }}</span>
    </div>
    <div class="wh-elitech-brief-meta">
      <el-tag
        v-if="warehouse.elitech_online === true"
        type="success"
        size="small"
        effect="plain"
      >
        在线
      </el-tag>
      <el-tag
        v-else-if="warehouse.elitech_online === false"
        type="info"
        size="small"
        effect="plain"
      >
        离线
      </el-tag>
      <span v-if="warehouse.elitech_device_name" class="wh-elitech-name">{{ warehouse.elitech_device_name }}</span>
    </div>
  </div>
  <span v-else class="wh-elitech-unbound">未绑定温湿度仪</span>
</template>

<style scoped>
.wh-elitech-brief {
  display: flex;
  flex-direction: column;
  gap: 4px;
  line-height: 1.35;
}

.wh-elitech-brief--card {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f0f9ff;
}

.wh-elitech-brief-main {
  font-weight: 600;
  color: #0f172a;
  font-size: 15px;
}

.wh-elitech-sep {
  margin: 0 4px;
  color: #94a3b8;
  font-weight: 400;
}

.wh-elitech-brief-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.wh-elitech-name {
  font-size: 12px;
  color: #64748b;
}

.wh-elitech-unbound {
  font-size: 13px;
  color: #94a3b8;
}
</style>
