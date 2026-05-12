<script setup>
import { reactive, ref } from 'vue'
import { uploadQualityReportApi } from '../../api/qualityReports'

const file = ref(null)
const form = reactive({ product_id: 1, order_id: 1, report_no: '' })

const onFileChange = (f) => { file.value = f.raw }
const submit = async () => {
  const fd = new FormData()
  fd.append('product_id', form.product_id)
  fd.append('order_id', form.order_id)
  fd.append('report_no', form.report_no)
  fd.append('file', file.value)
  await uploadQualityReportApi(fd)
}
</script>

<template>
  <el-card>
    <el-form label-width="90px">
      <el-form-item label="商品编号"><el-input-number v-model="form.product_id" :min="1" /></el-form-item>
      <el-form-item label="订单编号"><el-input-number v-model="form.order_id" :min="1" /></el-form-item>
      <el-form-item label="报告编号"><el-input v-model="form.report_no" /></el-form-item>
      <el-form-item label="文件">
        <el-upload :auto-upload="false" :on-change="onFileChange" :limit="1">
          <el-button>选择文件</el-button>
        </el-upload>
      </el-form-item>
      <el-button type="primary" @click="submit">上传</el-button>
    </el-form>
  </el-card>
</template>
