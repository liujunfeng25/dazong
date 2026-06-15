<template>
  <div class="tianshu-shell" :class="{ 'tianshu-shell--embedded': embedded }">
    <iframe
      ref="iframeRef"
      :src="iframeSrc"
      class="tianshu-iframe"
      title="天枢大屏"
      referrerpolicy="same-origin"
      allow="fullscreen"
      allowfullscreen
      @load="onIframeLoad"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

defineProps({
  embedded: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['director-state'])
const devUrl = import.meta.env.VITE_TIANSHU_URL
const iframeRef = ref(null)

const iframeSrc = computed(() => {
  const u = devUrl != null ? String(devUrl).trim() : ''
  if (!u) return '/tianshu/index.html'
  const base = u.endsWith('/') ? u.slice(0, -1) : u
  return `${base}/`
})

function getFullscreenElement() {
  const d = document
  return (
    d.fullscreenElement ||
    d.webkitFullscreenElement ||
    d.mozFullScreenElement ||
    d.msFullscreenElement ||
    null
  )
}

function notifyIframeFullscreenState() {
  const w = iframeRef.value?.contentWindow
  if (!w) return
  const el = iframeRef.value
  const on = Boolean(el && getFullscreenElement() === el)
  try {
    w.postMessage({ type: 'tianshu-fullscreen-state', value: on }, '*')
  } catch {
    /* ignore */
  }
}

function sendDirectorControl(action) {
  const w = iframeRef.value?.contentWindow
  if (!w) return
  try {
    w.postMessage({ type: 'tianshu-director-control', action }, '*')
  } catch {
    /* ignore */
  }
}

function startDirector() {
  sendDirectorControl('start')
}

function stopDirector() {
  sendDirectorControl('stop')
}

function toggleDirector() {
  sendDirectorControl('toggle')
}

defineExpose({
  startDirector,
  stopDirector,
  toggleDirector,
})

function onIframeLoad() {
  notifyIframeFullscreenState()
}

function onParentFullscreenChange() {
  notifyIframeFullscreenState()
}

function onChildMessage(ev) {
  if (ev.data?.type === 'tianshu-director-state') {
    emit('director-state', {
      running: Boolean(ev.data.running),
      phase: ev.data.phase || '',
      stepIndex: Number(ev.data.stepIndex ?? -1),
    })
    return
  }
  if (ev.data?.type !== 'tianshu-toggle-fullscreen') return
  const el = iframeRef.value
  if (!el) return
  const fs = getFullscreenElement()
  const req =
    el.requestFullscreen ||
    el.webkitRequestFullscreen ||
    el.mozRequestFullScreen ||
    el.msRequestFullscreen
  const exit =
    document.exitFullscreen ||
    document.webkitExitFullscreen ||
    document.mozCancelFullScreen ||
    document.msExitFullscreen
  try {
    let pending
    if (fs === el) {
      pending = exit?.call(document)
    } else {
      pending = req?.call(el)
    }
    pending?.catch?.(() => {})
  } catch {
    /* ignore */
  }
}

onMounted(() => {
  window.addEventListener('message', onChildMessage)
  document.addEventListener('fullscreenchange', onParentFullscreenChange)
  document.addEventListener('webkitfullscreenchange', onParentFullscreenChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onChildMessage)
  document.removeEventListener('fullscreenchange', onParentFullscreenChange)
  document.removeEventListener('webkitfullscreenchange', onParentFullscreenChange)
})
</script>

<style scoped>
.tianshu-shell {
  width: 100%;
  height: 100vh;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #050914;
}

.tianshu-shell--embedded {
  height: 100%;
  border-radius: 8px;
}

.tianshu-iframe {
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}
</style>
