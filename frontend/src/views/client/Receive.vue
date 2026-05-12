<script setup>
import { reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { receiveOrderApi, reviewOrderApi, settleOrderApi } from '../../api/orders'

const route = useRoute()
const form = reactive({ rating: 5, comment: '' })
const loading = ref(false)
const received = ref(false)
const reviewed = ref(false)
const settled = ref(false)

const receive = async () => {
  loading.value = true
  try {
    await receiveOrderApi(route.params.id)
    received.value = true
    ElMessage.success('收货完成')
  } finally {
    loading.value = false
  }
}
const review = async () => {
  loading.value = true
  try {
    await reviewOrderApi(route.params.id, form)
    reviewed.value = true
    ElMessage.success('评价已提交')
  } finally {
    loading.value = false
  }
}
const settle = async () => {
  loading.value = true
  try {
    await settleOrderApi(route.params.id)
    settled.value = true
    ElMessage.success('已完成结算')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-card v-loading="loading">
    <template #header>
      <span class="font-semibold">收货与结算</span>
    </template>
    <div class="mb-3">
      <el-button type="primary" :disabled="received" @click="receive">确认收货</el-button>
      <el-tag v-if="received" type="success" class="ml-2">已收货</el-tag>
    </div>
    <el-divider />
    <el-form label-width="80px">
      <el-form-item label="评分"><el-input-number v-model="form.rating" :min="1" :max="5" /></el-form-item>
      <el-form-item label="评价"><el-input v-model="form.comment" type="textarea" /></el-form-item>
      <el-button :disabled="reviewed" @click="review">提交评价</el-button>
      <el-button type="success" :disabled="settled || !received" @click="settle">结算</el-button>
      <el-tag v-if="settled" type="success" class="ml-2">已结算</el-tag>
    </el-form>
  </el-card>
</template>
