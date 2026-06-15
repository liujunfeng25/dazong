<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useYs7LivePlayer } from '../composables/useYs7LivePlayer'
import { ys7MetaFromRow } from '../utils/ys7DeviceMeta'
import Ys7BatteryDisplay from './Ys7BatteryDisplay.vue'
import Ys7PtzPanel from './Ys7PtzPanel.vue'

const props = defineProps({
  camera: { type: Object, default: null },
  /** 父组件已拉流时传入 */
  url: { type: String, default: '' },
  mode: { type: String, default: 'hls' },
  accessToken: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  /** 传入则组件内自动拉流 */
  liveUrlApi: { type: Function, default: null },
  ptzControl: { type: Function, default: null },
  ezDomId: { type: String, required: true },
  layout: { type: String, default: 'side' },
  ptzTheme: { type: String, default: 'dark' },
  compactPtz: { type: Boolean, default: false },
  showMeta: { type: Boolean, default: true },
  /** 错峰拉流：多路电池机时按序号递增延迟（毫秒） */
  startDelayMs: { type: Number, default: 0 },
})

const selfLoading = ref(false)
const selfError = ref('')
const selfUrl = ref('')
const selfMode = ref('hls')
const selfToken = ref('')

const { videoRef, ezDivRef, destroy, init } = useYs7LivePlayer()

const isBusy = computed(() => props.loading || selfLoading.value)
const displayError = computed(() => props.error || selfError.value)
const streamUrl = computed(() => (props.liveUrlApi ? selfUrl.value : props.url))
const streamMode = computed(() => (props.liveUrlApi ? selfMode.value : props.mode))
const streamToken = computed(() => (props.liveUrlApi ? selfToken.value : props.accessToken))
const isEz = computed(
  () => streamMode.value === 'ezuikit' || String(streamUrl.value || '').startsWith('ezopen://'),
)

const isBatteryCam = computed(() => ys7MetaFromRow(props.camera).powerKind === 'battery')

const loadingHint = computed(() => {
  if (isBatteryCam.value) return '电池机休眠中，正在唤醒并连接（约 10–30 秒）'
  return '正在连接直播…'
})

let loadGeneration = 0

const loadStream = async () => {
  if (!props.liveUrlApi || !props.camera?.id) return
  selfLoading.value = true
  selfError.value = ''
  selfUrl.value = ''
  destroy()
  try {
    const res = await props.liveUrlApi(props.camera.id)
    const url = String(res?.hls || '').trim()
    const mode = String(res?.ys7_play_mode || 'hls')
    selfMode.value = mode === 'ezuikit' || url.startsWith('ezopen://') ? 'ezuikit' : 'hls'
    selfToken.value = String(res?.ys7_access_token || '').trim()
    if (!url) {
      selfError.value = '未获取到直播地址'
      return
    }
    if (selfMode.value === 'ezuikit' && !selfToken.value) {
      selfError.value = '萤石 EZOPEN 播放缺少 accessToken'
      return
    }
    selfUrl.value = url
    await nextTick()
    await init(url, selfMode.value, selfToken.value)
  } catch (err) {
    selfError.value = err?.response?.data?.detail || '获取直播地址失败'
  } finally {
    selfLoading.value = false
  }
}

const scheduleLoad = async () => {
  const gen = ++loadGeneration
  const delay = Number(props.startDelayMs) || 0
  if (delay > 0) {
    await new Promise((r) => setTimeout(r, delay))
  }
  if (gen !== loadGeneration) return
  if (props.liveUrlApi) {
    if (props.camera?.id) await loadStream()
    return
  }
  if (displayError.value || !streamUrl.value) {
    destroy()
    return
  }
  await nextTick()
  await init(streamUrl.value, streamMode.value, streamToken.value)
}

watch(
  () => [
    props.camera?.id,
    props.url,
    props.mode,
    props.accessToken,
    props.error,
    props.startDelayMs,
  ],
  () => {
    scheduleLoad()
  },
  { immediate: true },
)
</script>

<template>
  <div
    v-loading="isBusy"
    :element-loading-text="loadingHint"
    class="ys7-live-ptz"
    :class="[`ys7-live-ptz--${layout}`, { 'ys7-live-ptz--has-ptz': !!ptzControl && !isBatteryCam }]"
  >
    <div v-if="showMeta && camera" class="ys7-live-meta">
      <strong>{{ camera.device_name || camera.device_code || '摄像头' }}</strong>
      <span>通道 {{ camera.channel_no || 1 }}</span>
      <span v-if="isBatteryCam" class="ys7-live-battery-wrap">
        <Ys7BatteryDisplay :row="camera" compact />
      </span>
      <span v-if="isBatteryCam" class="ys7-live-no-ptz">无云台</span>
    </div>

    <div v-if="displayError" class="ys7-live-empty">{{ displayError }}</div>
    <template v-else-if="streamUrl || isBusy">
      <div class="ys7-live-stage">
        <div class="ys7-live-player">
          <div
            v-show="isEz"
            :id="ezDomId"
            ref="ezDivRef"
            class="ys7-live-ez"
          />
          <video
            v-show="!isEz"
            ref="videoRef"
            class="ys7-live-video"
            controls
            autoplay
            muted
            playsinline
            webkit-playsinline
          />
        </div>
        <Ys7PtzPanel
          v-if="ptzControl && camera && !isBatteryCam"
          :device="camera"
          :ptz-control="ptzControl"
          :theme="ptzTheme"
          :compact="compactPtz"
          class="ys7-live-ptz-side"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.ys7-live-ptz {
  width: 100%;
}

.ys7-live-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  font-size: 13px;
  color: #cbd5e1;
}

.ys7-live-meta strong {
  color: #f8fafc;
  font-weight: 600;
}

.ys7-live-meta span {
  font-size: 12px;
  color: #94a3b8;
}

.ys7-live-battery-wrap {
  flex: 1 1 120px;
  min-width: 100px;
  max-width: 160px;
}

.ys7-live-battery-wrap :deep(.ys7-battery-pct) {
  color: #cbd5e1;
}

.ys7-live-no-ptz {
  font-size: 11px;
  color: #64748b;
  white-space: nowrap;
}

.ys7-live-empty {
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
  padding: 16px;
}

.ys7-live-stage {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-start;
}

.ys7-live-ptz--stack .ys7-live-stage {
  flex-direction: column;
}

.ys7-live-player {
  flex: 1 1 280px;
  min-width: 0;
}

.ys7-live-video,
.ys7-live-ez {
  width: 100%;
  aspect-ratio: 16 / 9;
  min-height: 140px;
  border-radius: 10px;
  background: #020617;
  display: block;
}

.ys7-live-ptz-side {
  flex: 0 0 auto;
}

.ys7-live-ptz--side .ys7-live-ptz-side {
  margin-top: 0;
}

@media (max-width: 720px) {
  .ys7-live-stage {
    flex-direction: column;
  }
}
</style>
