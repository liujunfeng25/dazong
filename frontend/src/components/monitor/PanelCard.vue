<script setup>
// 大屏面板容器：标题 + eyebrow + 角标括号 + 玻璃呼吸辉光；右上 header 插槽放控件。
defineProps({
  title: { type: String, default: '' },
  eyebrow: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  spotlight: { type: Boolean, default: false },
  // 入场动画延迟序号（交错出现）
  index: { type: Number, default: 0 },
})
</script>

<template>
  <section
    class="pcard"
    :class="{ spotlight }"
    :style="{ animationDelay: `${Math.min(index, 10) * 70}ms` }"
  >
    <i class="pc-corner tl"></i><i class="pc-corner tr"></i>
    <i class="pc-corner bl"></i><i class="pc-corner br"></i>

    <header class="pc-head" v-if="title || eyebrow || $slots.header">
      <div class="pc-titles">
        <p v-if="eyebrow" class="pc-eyebrow">{{ eyebrow }}</p>
        <h3 v-if="title" class="pc-title">{{ title }}</h3>
      </div>
      <div class="pc-actions"><slot name="header" /></div>
    </header>

    <div class="pc-body"><slot /></div>

    <transition name="pc-fade">
      <div v-if="loading" class="pc-loading"><i class="pc-spin"></i></div>
    </transition>
  </section>
</template>

<style scoped>
.pcard {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 14px 16px 12px;
  border: 1px solid rgba(92, 239, 255, .16);
  border-radius: 12px;
  background:
    linear-gradient(150deg, rgba(15, 26, 44, .82), rgba(8, 14, 26, .76));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .05), 0 16px 40px -22px rgba(0, 0, 0, .7);
  backdrop-filter: blur(6px);
  overflow: hidden;
  animation: pcEnter .6s cubic-bezier(.22, 1, .36, 1) both, pcBreath 6s ease-in-out infinite;
}
@keyframes pcEnter {
  from { opacity: 0; transform: translateY(16px) scale(.99); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes pcBreath {
  0%, 100% { border-color: rgba(92, 239, 255, .16); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .05), 0 16px 40px -22px rgba(0, 0, 0, .7); }
  50% { border-color: rgba(92, 239, 255, .3); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06), 0 16px 40px -20px rgba(0, 0, 0, .7), 0 0 26px -6px rgba(92, 239, 255, .22); }
}
.pcard.spotlight {
  border-color: rgba(92, 239, 255, .5);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .08), 0 0 32px -4px rgba(92, 239, 255, .4);
  animation-play-state: running, paused;
}

/* 角标括号 */
.pc-corner { position: absolute; width: 14px; height: 14px; border: 2px solid rgba(92, 239, 255, .5); pointer-events: none; }
.pc-corner.tl { top: 7px; left: 7px; border-right: 0; border-bottom: 0; border-radius: 4px 0 0 0; }
.pc-corner.tr { top: 7px; right: 7px; border-left: 0; border-bottom: 0; border-radius: 0 4px 0 0; }
.pc-corner.bl { bottom: 7px; left: 7px; border-right: 0; border-top: 0; border-radius: 0 0 0 4px; }
.pc-corner.br { bottom: 7px; right: 7px; border-left: 0; border-top: 0; border-radius: 0 0 4px 0; }

.pc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 8px; }
.pc-titles { min-width: 0; }
.pc-eyebrow { margin: 0 0 3px; color: rgba(92, 239, 255, .68); font: 800 10px/1.2 "JetBrains Mono", monospace; letter-spacing: .14em; text-transform: uppercase; }
.pc-title { margin: 0; color: #e6f9ff; font-size: 15px; font-weight: 700; letter-spacing: .01em; }
.pc-actions { flex-shrink: 0; display: inline-flex; align-items: center; gap: 8px; }
.pc-body { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }

.pc-loading {
  position: absolute; inset: 0; display: grid; place-items: center;
  background: rgba(6, 12, 22, .5); backdrop-filter: blur(2px); z-index: 5;
}
.pc-spin {
  width: 26px; height: 26px; border-radius: 50%;
  border: 2px solid rgba(92, 239, 255, .25); border-top-color: #5cefff;
  animation: pcSpin .8s linear infinite;
}
@keyframes pcSpin { to { transform: rotate(360deg); } }
.pc-fade-enter-active, .pc-fade-leave-active { transition: opacity .2s; }
.pc-fade-enter-from, .pc-fade-leave-to { opacity: 0; }
</style>
