/**
 * 北斗历史轨迹播放（对齐 sxw 物流地图：播放/暂停/继续/停止/复位/从新播放/
 * 进度拖动、倍速、循环、地图跟随、渐进轨迹线、航向角）。
 */
import { computed, reactive, ref } from 'vue'
import {
  bearingDegrees,
  buildSortedHistoryPath,
  escapeHtmlForMap,
  formatMonitorTimeUnix,
  historyPlaybackDurationMs,
  interpolatePath,
  subpathWithTip,
} from '../utils/amapPathPlayback'

export function useBeidouHistoryPlayback() {
  const playSpeed = ref(1)
  const followMap = ref(true)
  const loopPlay = ref(false)
  const progressiveTrail = ref(true)
  const progressPercent = ref(0)

  /** idle | playing | paused | ended */
  const session = ref('idle')

  let rafId = null
  let mapInst = null
  let markerInst = null
  let infoInst = null
  let playedPoly = null
  let path = []
  let meta = []
  let durationMs = 15000
  let tBase = 0
  let titleStr = ''
  let lastPop = 0

  const isPlaying = computed(() => session.value === 'playing')
  const isPaused = computed(() => session.value === 'paused')
  const canScrub = computed(() => path.length >= 2)

  const POP_MS = 140

  const cleanupRaf = () => {
    if (rafId != null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  const cleanupVisuals = () => {
    cleanupRaf()
    if (infoInst) {
      try {
        infoInst.close()
      } catch {
        /* ignore */
      }
      infoInst = null
    }
    if (playedPoly) {
      try {
        playedPoly.setMap(null)
      } catch {
        /* ignore */
      }
      playedPoly = null
    }
    if (markerInst) {
      try {
        markerInst.setMap(null)
      } catch {
        /* ignore */
      }
      markerInst = null
    }
  }

  /** 弹窗关闭 / 换页：清空一切 */
  const destroy = () => {
    cleanupVisuals()
    session.value = 'idle'
    mapInst = null
    progressPercent.value = 0
    path = []
    meta = []
    titleStr = ''
  }

  /** 仅地图容器销毁（重绘底图）：保留 path/meta/进度，便于不重查即可再播 */
  const detachForMapDestroyed = () => {
    cleanupVisuals()
    mapInst = null
    if (session.value === 'playing' || session.value === 'paused') {
      session.value = path.length >= 2 ? 'paused' : 'idle'
    }
  }

  /** 查询到新轨迹：停播并缓存路径供拖动条预览 */
  const syncTrackPoints = (points) => {
    cleanupVisuals()
    session.value = 'idle'
    mapInst = null
    const built = buildSortedHistoryPath(points || [])
    path = built.path
    meta = built.meta
    progressPercent.value = 0
    titleStr = ''
  }

  const metaIndexForRatio = (ratio) => {
    if (!meta.length) return 0
    const r = Math.min(1, Math.max(0, ratio))
    return Math.min(meta.length - 1, Math.max(0, Math.floor(r * (meta.length - 1))))
  }

  const updateMarkerAngle = (ratio) => {
    if (!markerInst || typeof markerInst.setAngle !== 'function') return
    const idx = metaIndexForRatio(ratio)
    const m = meta[idx] || {}
    let ang = m.course
    if (!Number.isFinite(ang)) {
      const n = path.length
      if (n >= 2) {
        const t = Math.min(1, Math.max(0, ratio))
        const seg = Math.min(n - 2, Math.max(0, Math.floor(t * (n - 1))))
        const a = path[seg]
        const b = path[seg + 1]
        if (a && b) ang = bearingDegrees(a[0], a[1], b[0], b[1])
      }
    }
    if (Number.isFinite(ang)) {
      try {
        markerInst.setAngle(ang)
      } catch {
        /* ignore */
      }
    }
  }

  const openInfo = (ratio) => {
    if (!markerInst || !infoInst || !mapInst) return
    const pos = markerInst.getPosition?.()
    if (!pos) return
    const idx = metaIndexForRatio(ratio)
    const m = meta[idx] || {}
    const sp = m.speed != null && Number.isFinite(m.speed) ? String(m.speed) : '—'
    const crs =
      m.course != null && Number.isFinite(m.course) ? `${Math.round(m.course)}°` : '—'
    const html = `<div style="padding:8px 10px;font-size:12px;min-width:178px;line-height:1.45;color:#0f172a;">
      <div style="font-weight:600;margin-bottom:4px;">${escapeHtmlForMap(titleStr)}</div>
      <div>时间：<b>${escapeHtmlForMap(formatMonitorTimeUnix(m.monitorTime))}</b></div>
      <div>速度：${escapeHtmlForMap(sp)}　航向：${escapeHtmlForMap(crs)}</div>
      <div style="color:#64748b;margin-top:4px;">进度 ${(Math.min(1, Math.max(0, ratio)) * 100).toFixed(1)}%</div>
    </div>`
    infoInst.setContent(html)
    infoInst.open(mapInst, pos)
  }

  const ensureMarkerInfo = (map) => {
    if (!map || !window.AMap || !path.length) return
    mapInst = map
    if (!markerInst) {
      markerInst = new window.AMap.Marker({
        position: path[0],
        title: `回放 · ${titleStr || '历史轨迹'}`,
        zIndex: 520,
      })
      markerInst.setMap(mapInst)
    }
    if (!infoInst) {
      infoInst = new window.AMap.InfoWindow({
        isCustom: true,
        offset: new window.AMap.Pixel(0, -38),
      })
    }
    if (progressiveTrail.value && !playedPoly) {
      playedPoly = new window.AMap.Polyline({
        path: [path[0]],
        strokeColor: '#16a34a',
        strokeWeight: 5,
        lineJoin: 'round',
        zIndex: 480,
      })
      playedPoly.setMap(mapInst)
    }
  }

  const applyFrame = (ratio, withInfo) => {
    const r = Math.min(1, Math.max(0, ratio))
    progressPercent.value = Math.round(r * 1000) / 10
    if (!path.length || !mapInst) return
    const pos = interpolatePath(path, r)
    if (markerInst) markerInst.setPosition(pos)
    updateMarkerAngle(r)
    if (progressiveTrail.value && playedPoly) {
      playedPoly.setPath(subpathWithTip(path, r))
    }
    if (followMap.value && mapInst && pos) {
      try {
        mapInst.setCenter(pos)
      } catch {
        /* ignore */
      }
    }
    if (withInfo) openInfo(r)
  }

  const tick = (nowMs) => {
    if (session.value !== 'playing') return
    let raw = (nowMs - tBase) / durationMs
    if (loopPlay.value && raw >= 1) {
      raw %= 1
      tBase = nowMs - raw * durationMs
    }
    if (raw >= 1 && !loopPlay.value) {
      applyFrame(1, true)
      session.value = 'ended'
      cleanupRaf()
      return
    }
    applyFrame(raw, false)
    if (nowMs - lastPop >= POP_MS || raw >= 0.998) {
      lastPop = nowMs
      openInfo(raw)
    }
    rafId = requestAnimationFrame(tick)
  }

  const startFromRatio = (getMap, getPoints, getTitle, ratio0) => {
    const map = getMap?.()
    if (!map || !window.AMap) return { ok: false, reason: 'no_map' }
    const built = buildSortedHistoryPath(getPoints?.() || [])
    if (built.path.length < 2) return { ok: false, reason: 'short_path' }

    cleanupVisuals()
    path = built.path
    meta = built.meta
    mapInst = map
    titleStr = getTitle?.() || '历史轨迹'
    durationMs = historyPlaybackDurationMs(meta, playSpeed.value)

    const r0 = Math.min(1, Math.max(0, ratio0))
    markerInst = new window.AMap.Marker({
      position: interpolatePath(path, r0),
      title: `回放 · ${titleStr}`,
      zIndex: 520,
    })
    markerInst.setMap(mapInst)

    infoInst = new window.AMap.InfoWindow({
      isCustom: true,
      offset: new window.AMap.Pixel(0, -38),
    })

    if (progressiveTrail.value) {
      playedPoly = new window.AMap.Polyline({
        path: subpathWithTip(path, r0),
        strokeColor: '#16a34a',
        strokeWeight: 5,
        lineJoin: 'round',
        zIndex: 480,
      })
      playedPoly.setMap(mapInst)
    }

    session.value = 'playing'
    lastPop = performance.now()
    tBase = performance.now() - r0 * durationMs
    applyFrame(r0, true)
    rafId = requestAnimationFrame(tick)
    return { ok: true }
  }

  /** 播放 / 继续：暂停则续播；结束且进度满则重头；否则从当前进度条位置播 */
  const playOrContinue = (getMap, getPoints, getTitle) => {
    if (session.value === 'playing') return { ok: true }
    if (session.value === 'paused') {
      resume()
      return { ok: true }
    }
    if (session.value === 'ended' && progressPercent.value >= 99.9) {
      return startFromRatio(getMap, getPoints, getTitle, 0)
    }
    const from = progressPercent.value / 100
    return startFromRatio(getMap, getPoints, getTitle, from)
  }

  const restartFromBeginning = (getMap, getPoints, getTitle) => {
    progressPercent.value = 0
    cleanupVisuals()
    session.value = 'idle'
    return startFromRatio(getMap, getPoints, getTitle, 0)
  }

  const pause = () => {
    if (session.value !== 'playing') return
    cleanupRaf()
    session.value = 'paused'
  }

  const resume = () => {
    if (session.value === 'ended' && progressPercent.value >= 99.9) return
    if (session.value !== 'paused' && session.value !== 'ended') return
    if (!mapInst || !path.length) return
    if (!markerInst) ensureMarkerInfo(mapInst)
    const r = progressPercent.value / 100
    session.value = 'playing'
    durationMs = historyPlaybackDurationMs(meta, playSpeed.value)
    tBase = performance.now() - r * durationMs
    lastPop = performance.now()
    rafId = requestAnimationFrame(tick)
  }

  /** 停止：去掉播放车标与渐进线，保留底图折线与 path 供拖动条 */
  const endPlayback = () => {
    cleanupRaf()
    cleanupVisuals()
    session.value = path.length >= 2 ? 'ended' : 'idle'
  }

  const seekPercent = (pct, getMap) => {
    if (!path.length) return
    const map = getMap?.() || mapInst
    if (!map) return
    ensureMarkerInfo(map)
    const r = Math.min(100, Math.max(0, pct)) / 100
    if (session.value === 'ended' || session.value === 'idle') {
      session.value = 'paused'
    }
    applyFrame(r, true)
    if (session.value === 'playing') {
      tBase = performance.now() - r * durationMs
    }
  }

  const resetToStart = (getMap) => {
    cleanupRaf()
    seekPercent(0, getMap)
    session.value = 'paused'
  }

  return reactive({
    playSpeed,
    followMap,
    loopPlay,
    progressiveTrail,
    progressPercent,
    session,
    isPlaying,
    isPaused,
    canScrub,
    syncTrackPoints,
    playOrContinue,
    pause,
    resume,
    restartFromBeginning,
    endPlayback,
    seekPercent,
    resetToStart,
    destroy,
    detachForMapDestroyed,
  })
}
