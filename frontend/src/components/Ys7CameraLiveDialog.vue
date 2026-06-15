<script setup>
import { computed } from 'vue'
import Ys7CameraLiveWithPtz from './Ys7CameraLiveWithPtz.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  camera: { type: Object, default: null },
  liveUrlApi: { type: Function, required: true },
  ptzControl: { type: Function, required: true },
  title: { type: String, default: '摄像头直播' },
  width: { type: String, default: '980px' },
  playerKey: { type: String, default: 'ys7-live' },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const ezDomId = computed(
  () => `${props.playerKey}-ez-${props.camera?.id || 'x'}`,
)
</script>

<template>
  <el-dialog v-model="visible" :title="title" :width="width" destroy-on-close class="ys7-live-dialog">
    <Ys7CameraLiveWithPtz
      v-if="visible && camera"
      :camera="camera"
      :live-url-api="liveUrlApi"
      :ptz-control="ptzControl"
      :ez-dom-id="ezDomId"
      layout="side"
      ptz-theme="light"
      :show-meta="true"
    />
  </el-dialog>
</template>

<style scoped>
.ys7-live-dialog :deep(.ys7-live-meta) {
  color: #475569;
}

.ys7-live-dialog :deep(.ys7-live-meta strong) {
  color: #0f172a;
}

.ys7-live-dialog :deep(.ys7-live-meta span) {
  color: #64748b;
}
</style>
