<script setup>
// 全屏大屏背景特效层：扫描线 + 网格 + 极光 + 浮动粒子，纯 CSS，pointer-events:none。
defineProps({
  reduced: { type: Boolean, default: false },
})
</script>

<template>
  <div class="cfx" :class="{ reduced }" aria-hidden="true">
    <div class="cfx-grid"></div>
    <div class="cfx-aurora"></div>
    <div class="cfx-scan"></div>
    <div class="cfx-particles"></div>
    <div class="cfx-vignette"></div>
  </div>
</template>

<style scoped>
.cfx {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.cfx > div { position: absolute; inset: 0; }

/* 网格 */
.cfx-grid {
  background-image:
    linear-gradient(rgba(92, 239, 255, .045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(92, 239, 255, .045) 1px, transparent 1px);
  background-size: 54px 54px;
  -webkit-mask-image: radial-gradient(ellipse 90% 80% at 50% 38%, #000 35%, transparent 80%);
  mask-image: radial-gradient(ellipse 90% 80% at 50% 38%, #000 35%, transparent 80%);
  opacity: .5;
}

/* 极光（缓慢旋转的 conic 渐变） */
.cfx-aurora {
  background: conic-gradient(from 210deg at 50% 30%,
    transparent 0deg,
    rgba(56, 189, 248, .10) 60deg,
    rgba(129, 140, 248, .08) 150deg,
    transparent 240deg,
    rgba(92, 239, 255, .09) 320deg,
    transparent 360deg);
  -webkit-mask-image: radial-gradient(ellipse 80% 70% at 50% 22%, #000, transparent 75%);
  mask-image: radial-gradient(ellipse 80% 70% at 50% 22%, #000, transparent 75%);
  mix-blend-mode: screen;
  animation: cfxSpin 46s linear infinite;
}
@keyframes cfxSpin { to { transform: rotate(360deg); } }

/* 扫描线 */
.cfx-scan {
  background: repeating-linear-gradient(180deg,
    transparent 0, transparent 5px,
    rgba(92, 239, 255, .035) 5px, rgba(92, 239, 255, .035) 6px);
  mix-blend-mode: soft-light;
  opacity: .5;
  animation: cfxScan 14s linear infinite;
}
@keyframes cfxScan { from { background-position-y: 0; } to { background-position-y: 600px; } }

/* 浮动粒子（多点径向渐变 + 横向漂移） */
.cfx-particles {
  background-image:
    radial-gradient(1.6px 1.6px at 8% 22%, rgba(220, 250, 255, .9), transparent),
    radial-gradient(1.4px 1.4px at 24% 64%, rgba(120, 220, 255, .7), transparent),
    radial-gradient(1.6px 1.6px at 47% 18%, rgba(220, 250, 255, .8), transparent),
    radial-gradient(1.3px 1.3px at 63% 78%, rgba(129, 140, 248, .7), transparent),
    radial-gradient(1.7px 1.7px at 78% 34%, rgba(220, 250, 255, .85), transparent),
    radial-gradient(1.4px 1.4px at 90% 60%, rgba(120, 220, 255, .7), transparent),
    radial-gradient(1.3px 1.3px at 36% 90%, rgba(220, 250, 255, .6), transparent);
  -webkit-mask-image: radial-gradient(ellipse 95% 90% at 50% 40%, #000, transparent 85%);
  mask-image: radial-gradient(ellipse 95% 90% at 50% 40%, #000, transparent 85%);
  mix-blend-mode: screen;
  animation: cfxFloat 26s ease-in-out infinite alternate;
}
@keyframes cfxFloat {
  from { transform: translate3d(0, 0, 0); }
  to { transform: translate3d(-26px, -14px, 0); }
}

/* 暗角 */
.cfx-vignette {
  background: radial-gradient(ellipse 120% 100% at 50% 0%, transparent 55%, rgba(2, 6, 14, .55) 100%);
}

.cfx.reduced .cfx-aurora,
.cfx.reduced .cfx-scan,
.cfx.reduced .cfx-particles { animation: none; }

@media (prefers-reduced-motion: reduce) {
  .cfx-aurora, .cfx-scan, .cfx-particles { animation: none; }
}
</style>
