import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * 响应式判断是否移动端（窄屏，≤768px）。
 * 用于在脚本里驱动 el-descriptions :column、el-col :span、弹窗/抽屉宽度等。
 */
export function useIsMobile(maxWidth = 768) {
  const isMobile = ref(false)
  let mql = null
  const apply = (e) => {
    isMobile.value = e.matches
  }
  onMounted(() => {
    mql = window.matchMedia(`(max-width: ${maxWidth}px)`)
    isMobile.value = mql.matches
    if (mql.addEventListener) mql.addEventListener('change', apply)
    else mql.addListener(apply)
  })
  onBeforeUnmount(() => {
    if (!mql) return
    if (mql.removeEventListener) mql.removeEventListener('change', apply)
    else mql.removeListener(apply)
  })
  return { isMobile }
}
