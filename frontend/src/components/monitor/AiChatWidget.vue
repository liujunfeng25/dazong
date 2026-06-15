<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import AiChatPanel from './AiChatPanel.vue'

const STORE_KEY = 'dz_ai_widget_v2'
const open = ref(false)

const DEFAULT_W = 760
const win = reactive({ width: DEFAULT_W })

const clamp = (v, min, max) => Math.min(Math.max(v, min), max)

function persist() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ open: open.value, width: win.width }))
  } catch { /* ignore */ }
}

function restore() {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (raw) {
      const s = JSON.parse(raw)
      if (s.width) win.width = clamp(s.width, 620, Math.min(920, window.innerWidth - 24))
      open.value = !!s.open
    }
  } catch { /* ignore */ }
  clampIntoView()
}

function clampIntoView() {
  const minWidth = window.innerWidth < 760 ? Math.max(340, window.innerWidth - 16) : 620
  win.width = clamp(win.width, minWidth, Math.min(920, window.innerWidth - 16))
}

function toggle() {
  open.value = !open.value
  if (open.value) clampIntoView()
  persist()
}
function minimize() { open.value = false; persist() }

const winRef = ref(null)
let resizing = false
let startX = 0
let baseWidth = 0

function onResizeStart(e) {
  if (e.button != null && e.button !== 0) return
  resizing = true
  startX = e.clientX
  baseWidth = win.width
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeEnd)
}
function onResizeMove(e) {
  if (!resizing) return
  win.width = clamp(baseWidth + (startX - e.clientX), 620, Math.min(920, window.innerWidth - 16))
}
function onResizeEnd() {
  resizing = false
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
  persist()
}

function onWindowResize() { if (open.value) clampIntoView() }

onMounted(() => {
  restore()
  window.addEventListener('resize', onWindowResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
})
</script>

<template>
  <div class="ai-widget-root">
    <!-- 浮窗：v-show 保活对话历史 -->
    <div
      v-show="open"
      ref="winRef"
      class="ai-win"
      :style="{ width: win.width + 'px' }"
    >
      <button class="ai-win__resize" type="button" aria-label="调整智能体工作台宽度" @pointerdown="onResizeStart"><i></i></button>
      <header class="ai-win__bar">
        <span class="ai-win__identity">
          <span class="ai-win__agent"><i></i><b></b></span>
          <span>
            <strong>监管智能体</strong>
            <em>REGULATORY COPILOT · ONLINE · 全域监管</em>
          </span>
        </span>
        <span class="ai-win__ops">
          <button type="button" title="最小化" @click.stop="minimize">—</button>
          <button type="button" title="关闭" @click.stop="minimize">✕</button>
        </span>
      </header>
      <div class="ai-win__body">
        <AiChatPanel />
      </div>
    </div>

    <!-- 气泡 launcher -->
    <button v-show="!open" type="button" class="ai-fab" title="监管智能体" @click="toggle">
      <span class="ai-fab__orb">
        <i></i>
        <b>AI</b>
      </span>
      <span class="ai-fab__copy">
        <strong>监管智能体</strong>
        <em><i></i> ONLINE · 随时调用</em>
      </span>
      <span class="ai-fab__action">↗</span>
    </button>
  </div>
</template>

<style scoped>
.ai-widget-root { position: fixed; inset: 0; pointer-events: none; z-index: 2400; }
.ai-win, .ai-fab { pointer-events: auto; }

.ai-win {
  position: fixed;
  top: 8px;
  right: 8px;
  bottom: 8px;
  display: flex;
  flex-direction: column;
  min-width: min(620px, calc(100vw - 16px));
  max-width: min(920px, calc(100vw - 16px));
  overflow: hidden;
  background:
    radial-gradient(circle at 82% 0%, rgba(104, 250, 221, .08), transparent 34%),
    rgba(5, 14, 25, 0.97);
  border: 1px solid rgba(0, 229, 255, 0.26);
  border-radius: 20px;
  box-shadow: -28px 0 90px rgba(0, 0, 0, 0.58), 0 0 0 1px rgba(104, 250, 221, 0.04);
  backdrop-filter: blur(18px);
}
.ai-win__resize {
  position: absolute; z-index: 5; left: -5px; top: 74px; bottom: 18px; width: 12px;
  padding: 0; border: 0; background: transparent; cursor: ew-resize;
}
.ai-win__resize i {
  position: absolute; left: 4px; top: 43%; width: 3px; height: 72px; border-radius: 9px;
  background: linear-gradient(180deg, transparent, rgba(0,229,255,.65), transparent);
  box-shadow: 0 0 12px rgba(0,229,255,.24);
}
.ai-win__bar {
  display: flex; align-items: center; justify-content: space-between;
  min-height: 58px;
  padding: 9px 12px 9px 14px;
  user-select: none;
  background: linear-gradient(90deg, rgba(0, 229, 255, .07), rgba(104, 250, 221, .025) 55%, transparent);
  border-bottom: 1px solid rgba(0, 229, 255, 0.13);
}
.ai-win__identity { display: flex; align-items: center; gap: 11px; }
.ai-win__identity > span:last-child { display: grid; gap: 4px; }
.ai-win__identity strong { color: #e6fbff; font-size: 14px; letter-spacing: .04em; }
.ai-win__identity em { color: #50818d; font: 700 8px/1 "JetBrains Mono", monospace; font-style: normal; letter-spacing: .15em; }
.ai-win__agent { position: relative; width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid rgba(0,229,255,.28); border-radius: 10px; background: rgba(0,229,255,.055); }
.ai-win__agent::before, .ai-win__agent::after { content: ''; position: absolute; border-radius: 50%; border: 1px solid rgba(104,250,221,.3); }
.ai-win__agent::before { width: 20px; height: 20px; }
.ai-win__agent::after { width: 10px; height: 10px; }
.ai-win__agent i { width: 4px; height: 4px; border-radius: 50%; background: #68fadd; box-shadow: 0 0 10px #68fadd; }
.ai-win__ops { display: flex; gap: 6px; }
.ai-win__ops button {
  width: 28px; height: 28px; border: 1px solid rgba(0, 229, 255, 0.16); border-radius: 8px;
  background: rgba(0,229,255,.025); color: #78aeb8; cursor: pointer; font-size: 13px; line-height: 1;
}
.ai-win__ops button:hover { background: rgba(0, 229, 255, 0.14); }
.ai-win__body { flex: 1; min-height: 0; overflow: hidden; }
/* 让原生 resize 抓手在右下角更明显 */

.ai-fab {
  position: fixed; right: 24px; bottom: 22px;
  width: 196px; height: 64px; padding: 7px 10px 7px 8px;
  border-radius: 19px;
  border: 1px solid rgba(0, 229, 255, 0.28);
  background:
    linear-gradient(115deg, rgba(0,229,255,.12), rgba(7,24,38,.94) 42%, rgba(5,15,27,.97)),
    #071522;
  color: #dffbff;
  cursor: pointer;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .42), inset 0 1px 0 rgba(255,255,255,.04);
  display: grid; grid-template-columns: 48px 1fr 22px; align-items: center; gap: 10px;
  text-align: left;
  overflow: hidden;
  backdrop-filter: blur(16px);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.ai-fab::before { content: ''; position: absolute; left: -20%; top: -80%; width: 72%; height: 220%; transform: rotate(24deg); background: linear-gradient(90deg, transparent, rgba(104,250,221,.08), transparent); animation: ai-scan 5s ease-in-out infinite; }
.ai-fab:hover { transform: translateY(-3px); border-color: rgba(104,250,221,.55); box-shadow: 0 22px 60px rgba(0,0,0,.5), 0 0 26px rgba(0,229,255,.12); }
.ai-fab.is-open { width: 64px; grid-template-columns: 1fr; padding: 7px; border-radius: 18px; }
.ai-fab.is-open .ai-fab__orb { opacity: .22; }
.ai-fab__orb { position: relative; width: 46px; height: 46px; display: grid; place-items: center; border: 1px solid rgba(0,229,255,.38); border-radius: 14px; background: radial-gradient(circle, rgba(104,250,221,.16), rgba(0,229,255,.04) 48%, transparent 50%); box-shadow: inset 0 0 20px rgba(0,229,255,.08); }
.ai-fab__orb::before, .ai-fab__orb::after, .ai-fab__orb i { content: ''; position: absolute; border-radius: 50%; }
.ai-fab__orb::before { width: 31px; height: 31px; border: 1px dashed rgba(104,250,221,.38); animation: ai-rotate 8s linear infinite; }
.ai-fab__orb::after { width: 20px; height: 20px; border: 1px solid rgba(0,229,255,.42); }
.ai-fab__orb i { width: 5px; height: 5px; right: 7px; top: 10px; background: #68fadd; box-shadow: 0 0 10px #68fadd; }
.ai-fab__orb b { position: relative; z-index: 1; color: #bffcff; font: 800 9px/1 "JetBrains Mono", monospace; letter-spacing: .06em; }
.ai-fab__copy { position: relative; z-index: 1; display: grid; gap: 6px; min-width: 0; }
.ai-fab__copy strong { overflow: hidden; color: #e7fbff; font-size: 13px; letter-spacing: .06em; white-space: nowrap; }
.ai-fab__copy em { display: flex; align-items: center; gap: 5px; color: #55808b; font: 700 8px/1 "JetBrains Mono", monospace; font-style: normal; letter-spacing: .08em; white-space: nowrap; }
.ai-fab__copy em i { width: 5px; height: 5px; border-radius: 50%; background: #68fadd; box-shadow: 0 0 8px rgba(104,250,221,.8); }
.ai-fab__action { position: relative; z-index: 2; color: #64aebb; font-size: 15px; text-align: center; }
.ai-fab.is-open .ai-fab__action { position: absolute; inset: 0; display: grid; place-items: center; color: #a8eef5; font-size: 20px; }
@keyframes ai-rotate { to { transform: rotate(360deg); } }
@keyframes ai-scan { 0%, 70% { transform: translateX(-30px) rotate(24deg); opacity: 0; } 78% { opacity: 1; } 100% { transform: translateX(260px) rotate(24deg); opacity: 0; } }
@media (max-width: 720px) {
  .ai-win { top: 6px; right: 6px; bottom: 6px; width: calc(100vw - 12px) !important; min-width: 0; max-width: none; }
  .ai-win__resize { display: none; }
  .ai-fab { right: 14px; bottom: 14px; width: 64px; grid-template-columns: 1fr; padding: 8px; }
  .ai-fab__copy, .ai-fab__action { display: none; }
  .ai-fab__orb { margin: auto; }
}
</style>
