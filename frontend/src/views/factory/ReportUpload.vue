<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { uploadQualityReportApi } from '../../api/qualityReports'

const QR_MAX_BYTES = 20 * 1024 * 1024
const uploadFileList = ref([])
const form = reactive({ product_id: 1, order_id: 1, report_no: '' })

const beforeQrUpload = (rawFile) => {
  if (rawFile.size > QR_MAX_BYTES) {
    ElMessage.error('单张不能超过 20MB')
    return false
  }
  const ok =
    /^image\/(jpeg|png|gif|webp)$/i.test(rawFile.type) ||
    rawFile.type === 'application/pdf' ||
    /\.(jpe?g|png|gif|webp|pdf)$/i.test(rawFile.name || '')
  if (!ok) {
    ElMessage.error('仅支持 JPG、PNG、GIF、WebP、PDF')
    return false
  }
  return true
}

const submit = async () => {
  const raws = (uploadFileList.value || []).map((f) => f.raw).filter(Boolean)
  if (!raws.length) {
    ElMessage.warning('请至少选择一个文件')
    return
  }
  try {
    const fd = new FormData()
    fd.append('product_id', String(form.product_id))
    fd.append('order_id', String(form.order_id))
    fd.append('report_no', form.report_no || `QR-${form.order_id}`)
    raws.forEach((file) => fd.append('files', file))
    await uploadQualityReportApi(fd)
    ElMessage.success('已上传')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
}
</script>

<template>
  <el-card>
    <el-form label-width="90px">
      <el-form-item label="商品编号"><el-input-number v-model="form.product_id" :min="1" /></el-form-item>
      <el-form-item label="订单编号"><el-input-number v-model="form.order_id" :min="1" /></el-form-item>
      <el-form-item label="报告编号"><el-input v-model="form.report_no" /></el-form-item>
      <el-form-item label="文件">
        <el-upload
          v-model:file-list="uploadFileList"
          :auto-upload="false"
          multiple
          :limit="20"
          list-type="picture-card"
          :before-upload="beforeQrUpload"
          accept=".jpg,.jpeg,.png,.gif,.webp,.pdf,image/*"
        >
          <el-icon><Plus /></el-icon>
        </el-upload>
      </el-form-item>
      <el-button type="primary" @click="submit">上传</el-button>
    </el-form>
  </el-card>
</template>
