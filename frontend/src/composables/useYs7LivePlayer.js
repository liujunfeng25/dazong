import Hls from 'hls.js'
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'

let ezUiKitScriptPromise = null

export function ensureEzUiKitScript() {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if (window.EZUIKit?.EZUIKitPlayer) return Promise.resolve()
  if (!ezUiKitScriptPromise) {
    ezUiKitScriptPromise = new Promise((resolve, reject) => {
      const s = document.createElement('script')
      s.src = 'https://cdn.jsdelivr.net/npm/ezuikit-js@8.2.6/ezuikit.js'
      s.async = true
      s.onload = () => resolve()
      s.onerror = () => reject(new Error('ezuikit'))
      document.head.appendChild(s)
    })
  }
  return ezUiKitScriptPromise
}

/** 单路萤石/HLS 播放器：挂载到 video + ezopen 容器 */
export function useYs7LivePlayer() {
  const videoRef = ref(null)
  const ezDivRef = ref(null)
  const hlsPlayer = ref(null)
  const ezPlayer = ref(null)
  const playMode = ref('hls')
  const accessToken = ref('')

  const destroy = () => {
    if (ezPlayer.value) {
      try {
        if (typeof ezPlayer.value.destroy === 'function') ezPlayer.value.destroy()
      } catch {
        // ignore
      }
      try {
        if (typeof ezPlayer.value.stop === 'function') ezPlayer.value.stop()
      } catch {
        // ignore
      }
      ezPlayer.value = null
    }
    if (hlsPlayer.value) {
      hlsPlayer.value.destroy()
      hlsPlayer.value = null
    }
    const video = videoRef.value
    if (video) {
      try {
        video.pause()
      } catch {
        // ignore
      }
      video.removeAttribute('src')
      video.load()
    }
  }

  const init = async (url, mode, token) => {
    const liveUrl = String(url || '').trim()
    if (!liveUrl) return
    destroy()
    const m = mode === 'ezuikit' || liveUrl.startsWith('ezopen://') ? 'ezuikit' : 'hls'
    playMode.value = m
    accessToken.value = String(token || '').trim()

    if (m === 'ezuikit') {
      if (!accessToken.value) {
        ElMessage.warning('萤石播放缺少 accessToken，请检查后端萤石配置')
        return
      }
      await nextTick()
      const wrap = ezDivRef.value
      if (!wrap?.id) return
      try {
        await ensureEzUiKitScript()
      } catch {
        ElMessage.error('萤石 EZUIKit 脚本加载失败，请检查网络')
        return
      }
      const w = Math.max(260, wrap.clientWidth || 320)
      const h = Math.max(146, Math.floor((w * 9) / 16))
      try {
        ezPlayer.value = new window.EZUIKit.EZUIKitPlayer({
          id: wrap.id,
          accessToken: accessToken.value,
          url: liveUrl,
          width: w,
          height: h,
        })
      } catch {
        ElMessage.error('萤石播放器初始化失败')
      }
      return
    }

    await nextTick()
    const video = videoRef.value
    if (!video) return
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = liveUrl
      video.play().catch(() => {})
      return
    }
    if (Hls.isSupported()) {
      const hls = new Hls()
      hlsPlayer.value = hls
      hls.loadSource(liveUrl)
      hls.attachMedia(video)
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}))
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data?.fatal) ElMessage.error('直播流播放失败，请稍后重试')
      })
      return
    }
    ElMessage.warning('当前浏览器不支持 HLS 播放')
  }

  onBeforeUnmount(destroy)

  return {
    videoRef,
    ezDivRef,
    playMode,
    accessToken,
    destroy,
    init,
  }
}
