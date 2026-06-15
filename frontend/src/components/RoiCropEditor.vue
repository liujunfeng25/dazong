<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  imageUrl: { type: String, default: '' },
  modelValue: {
    type: Object,
    default: () => ({ x: 0.25, y: 0.2, width: 0.5, height: 0.55, rotation: 0 }),
  },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['update:modelValue', 'change'])
const editorRef = ref(null)
const imageSize = ref({ width: 4, height: 3 })
let interaction = null

const normalized = computed(() => ({
  x: Number(props.modelValue?.x ?? 0.25),
  y: Number(props.modelValue?.y ?? 0.2),
  width: Number(props.modelValue?.width ?? 0.5),
  height: Number(props.modelValue?.height ?? 0.55),
  rotation: Number(props.modelValue?.rotation ?? 0),
}))

const frameStyle = computed(() => ({
  left: `${normalized.value.x * 100}%`,
  top: `${normalized.value.y * 100}%`,
  width: `${normalized.value.width * 100}%`,
  height: `${normalized.value.height * 100}%`,
}))

const previewStyle = computed(() => ({
  aspectRatio: `${Math.max(1, normalized.value.width * imageSize.value.width)} / ${Math.max(
    1,
    normalized.value.height * imageSize.value.height,
  )}`,
}))

const previewImageStyle = computed(() => ({
  width: `${100 / Math.max(0.05, normalized.value.width)}%`,
  left: `${(-normalized.value.x / Math.max(0.05, normalized.value.width)) * 100}%`,
  top: `${(-normalized.value.y / Math.max(0.05, normalized.value.height)) * 100}%`,
}))

const clamp = (value, min, max) => Math.min(max, Math.max(min, value))

const update = (next) => {
  const value = {
    x: Number(next.x.toFixed(6)),
    y: Number(next.y.toFixed(6)),
    width: Number(next.width.toFixed(6)),
    height: Number(next.height.toFixed(6)),
    rotation: normalized.value.rotation,
  }
  emit('update:modelValue', value)
  emit('change', value)
}

const startInteraction = (event, mode) => {
  if (props.disabled || !editorRef.value) return
  event.preventDefault()
  event.stopPropagation()
  const rect = editorRef.value.getBoundingClientRect()
  interaction = {
    mode,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    rect,
    roi: { ...normalized.value },
  }
  event.currentTarget.setPointerCapture?.(event.pointerId)
}

const moveInteraction = (event) => {
  if (!interaction || event.pointerId !== interaction.pointerId) return
  const dx = (event.clientX - interaction.startX) / Math.max(1, interaction.rect.width)
  const dy = (event.clientY - interaction.startY) / Math.max(1, interaction.rect.height)
  const start = interaction.roi
  if (interaction.mode === 'move') {
    update({
      ...start,
      x: clamp(start.x + dx, 0, 1 - start.width),
      y: clamp(start.y + dy, 0, 1 - start.height),
    })
    return
  }
  const width = clamp(start.width + dx, 0.05, 1 - start.x)
  const height = clamp(start.height + dy, 0.05, 1 - start.y)
  update({ ...start, width, height })
}

const endInteraction = (event) => {
  if (interaction && event.pointerId === interaction.pointerId) interaction = null
}

const onImageLoad = (event) => {
  imageSize.value = {
    width: event.target.naturalWidth || 4,
    height: event.target.naturalHeight || 3,
  }
}
</script>

<template>
  <div class="roi-editor">
    <div
      ref="editorRef"
      class="roi-stage"
      @pointermove="moveInteraction"
      @pointerup="endInteraction"
      @pointercancel="endInteraction"
    >
      <img v-if="imageUrl" :src="imageUrl" alt="ROI 校准原图" @load="onImageLoad" />
      <div v-else class="roi-empty">该设备还没有可用于校准的原图</div>
      <div
        v-if="imageUrl"
        class="roi-frame"
        :class="{ 'is-disabled': disabled }"
        :style="frameStyle"
        @pointerdown="startInteraction($event, 'move')"
      >
        <span class="roi-label">训练 / 识别区域</span>
        <button
          type="button"
          class="roi-handle"
          aria-label="调整 ROI 大小"
          @pointerdown="startInteraction($event, 'resize')"
        />
      </div>
    </div>

    <div class="roi-preview">
      <div>
        <strong>裁剪预览</strong>
        <span>
          x {{ Math.round(normalized.x * 100) }}% · y {{ Math.round(normalized.y * 100) }}% ·
          {{ Math.round(normalized.width * 100) }}% × {{ Math.round(normalized.height * 100) }}%
        </span>
      </div>
      <div class="preview-viewport" :style="previewStyle">
        <img v-if="imageUrl" :src="imageUrl" alt="ROI 裁剪预览" :style="previewImageStyle" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.roi-editor {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(180px, 0.8fr);
  gap: 14px;
}

.roi-stage {
  position: relative;
  min-height: 260px;
  overflow: hidden;
  border: 1px solid rgba(122, 102, 194, 0.2);
  border-radius: 14px;
  background: #edf0f6;
  touch-action: none;
}

.roi-stage > img {
  display: block;
  width: 100%;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}

.roi-empty {
  display: grid;
  min-height: 260px;
  place-items: center;
  padding: 24px;
  color: #8b95aa;
  text-align: center;
}

.roi-frame {
  position: absolute;
  box-sizing: border-box;
  border: 3px solid #ef4444;
  cursor: move;
  box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.32);
}

.roi-frame.is-disabled {
  cursor: default;
}

.roi-label {
  position: absolute;
  top: -30px;
  left: -3px;
  padding: 4px 8px;
  border-radius: 6px 6px 0 0;
  color: #fff;
  background: #ef4444;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.roi-handle {
  position: absolute;
  right: -8px;
  bottom: -8px;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 3px solid #fff;
  border-radius: 50%;
  cursor: nwse-resize;
  background: #ef4444;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.25);
}

.roi-preview {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
}

.roi-preview strong,
.roi-preview span {
  display: block;
}

.roi-preview strong {
  color: #27324e;
  font-size: 13px;
}

.roi-preview span {
  margin-top: 4px;
  color: #7b879e;
  font-size: 10px;
  line-height: 1.5;
}

.preview-viewport {
  position: relative;
  min-height: 150px;
  overflow: hidden;
  border: 1px solid rgba(122, 102, 194, 0.18);
  border-radius: 12px;
  background: #f1f3f8;
}

.preview-viewport img {
  position: absolute;
  max-width: none;
  height: auto;
  user-select: none;
  -webkit-user-drag: none;
}

@media (max-width: 760px) {
  .roi-editor {
    grid-template-columns: 1fr;
  }
}
</style>
