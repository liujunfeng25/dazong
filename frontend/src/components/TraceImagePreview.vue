<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useAttrs, watch } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  src: { type: String, default: '' },
  previewList: { type: Array, default: () => [] },
  initialIndex: { type: Number, default: 0 },
  fit: { type: String, default: 'cover' },
  alt: { type: String, default: '留痕图片' },
})

const attrs = useAttrs()
const visible = ref(false)
const current = ref(0)
const loadFailed = ref(false)
const previewFailed = ref(false)

const images = computed(() => {
  const list = (props.previewList || []).filter(Boolean)
  return list.length ? list : (props.src ? [props.src] : [])
})
const activeSrc = computed(() => images.value[current.value] || props.src || '')

const open = async () => {
  if (!props.src) return
  current.value = Math.min(Math.max(Number(props.initialIndex || 0), 0), Math.max(images.value.length - 1, 0))
  previewFailed.value = false
  visible.value = true
  await nextTick()
  document.body.classList.add('trace-preview-lock')
}

const close = () => {
  visible.value = false
  document.body.classList.remove('trace-preview-lock')
}

const move = (step) => {
  const total = images.value.length
  if (total <= 1) return
  current.value = (current.value + step + total) % total
  previewFailed.value = false
}

const onKeydown = (e) => {
  if (!visible.value) return
  if (e.key === 'Escape') close()
  if (e.key === 'ArrowLeft') move(-1)
  if (e.key === 'ArrowRight') move(1)
}

watch(visible, (v) => {
  if (v) window.addEventListener('keydown', onKeydown)
  else window.removeEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.classList.remove('trace-preview-lock')
})
</script>

<template>
  <button v-bind="attrs" type="button" class="trace-preview-thumb" @click.stop="open">
    <img
      v-if="src && !loadFailed"
      :src="src"
      :alt="alt"
      :style="{ objectFit: fit }"
      @error="loadFailed = true"
    />
    <span v-else>加载失败</span>
  </button>

  <Teleport to="body">
    <div v-if="visible" class="trace-preview-mask" @click.self="close">
      <button type="button" class="trace-preview-close" @click="close">×</button>
      <button
        v-if="images.length > 1"
        type="button"
        class="trace-preview-nav trace-preview-prev"
        @click.stop="move(-1)"
      >
        ‹
      </button>
      <div class="trace-preview-body">
        <img
          v-if="activeSrc && !previewFailed"
          :src="activeSrc"
          :alt="alt"
          @error="previewFailed = true"
        />
        <div v-else class="trace-preview-error">图片加载失败，请检查网络或重试</div>
        <div v-if="images.length > 1" class="trace-preview-count">
          {{ current + 1 }} / {{ images.length }}
        </div>
      </div>
      <button
        v-if="images.length > 1"
        type="button"
        class="trace-preview-nav trace-preview-next"
        @click.stop="move(1)"
      >
        ›
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.trace-preview-thumb {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 0;
  border: 1px solid #dce5dd;
  border-radius: 6px;
  background: #eef3f5;
  color: #6b7280;
  cursor: pointer;
}

.trace-preview-thumb img {
  display: block;
  width: 100%;
  height: 100%;
}

.trace-preview-thumb span {
  padding: 0 6px;
  font-size: 12px;
}

.trace-preview-mask {
  position: fixed;
  inset: 0;
  z-index: 5000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(15, 23, 42, 0.78);
}

.trace-preview-body {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  max-width: 92vw;
  max-height: 88vh;
}

.trace-preview-body img {
  display: block;
  max-width: 88vw;
  max-height: 82vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.32);
  background: #111827;
}

.trace-preview-error {
  padding: 24px 32px;
  border-radius: 8px;
  background: #fff;
  color: #334155;
}

.trace-preview-close,
.trace-preview-nav {
  position: fixed;
  z-index: 5001;
  border: 0;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
  cursor: pointer;
}

.trace-preview-close {
  top: 26px;
  right: 30px;
  width: 44px;
  height: 44px;
  font-size: 32px;
  line-height: 40px;
}

.trace-preview-nav {
  top: 50%;
  width: 52px;
  height: 52px;
  font-size: 42px;
  transform: translateY(-50%);
}

.trace-preview-prev {
  left: 32px;
}

.trace-preview-next {
  right: 32px;
}

.trace-preview-count {
  position: fixed;
  bottom: 28px;
  left: 50%;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.62);
  color: #fff;
  transform: translateX(-50%);
}
</style>

<style>
body.trace-preview-lock {
  overflow: hidden;
}
</style>
