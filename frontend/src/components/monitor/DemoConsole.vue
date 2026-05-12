<script setup>
import { ref } from 'vue'
import {
  demoNewOrderApi,
  demoResetApi,
  demoSimulateDeliveryApi,
  demoTriggerTempAlertApi,
} from '../../api/demo'

const open = ref(false)
const loading = ref(false)
const enabled = (import.meta.env.VITE_DEMO_MODE || 'false') === 'true'

const run = async (fn) => {
  loading.value = true
  try {
    await fn()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="enabled" class="fixed right-6 bottom-6 z-50">
    <el-button type="primary" @click="open = !open">演示控制台</el-button>
    <el-card v-if="open" class="mt-2 w-72">
      <el-space direction="vertical" fill>
        <el-button :loading="loading" @click="run(demoNewOrderApi)">模拟新订单</el-button>
        <el-button :loading="loading" @click="run(demoTriggerTempAlertApi)">触发温度预警</el-button>
        <el-button :loading="loading" @click="run(demoSimulateDeliveryApi)">模拟向客户配送</el-button>
        <el-button :loading="loading" type="danger" @click="run(demoResetApi)">重置演示数据</el-button>
      </el-space>
    </el-card>
  </div>
</template>
