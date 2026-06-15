<script setup>
/**
 * el-image 的轻封装：懒加载 + 骨架占位 + 失败兜底。
 * 透传全部属性（src/fit/preview-src-list/initial-index/class 等）到 el-image。
 * 用于图片密集的详情页，滚动时先显示占位骨架再填充图片，减少首屏负担与视觉跳动。
 */
defineOptions({ inheritAttrs: true })
</script>

<template>
  <el-image v-bind="$attrs" lazy>
    <template #placeholder>
      <div class="img-skeleton" />
    </template>
    <template #error>
      <div class="img-skeleton img-skeleton--error">加载失败</div>
    </template>
  </el-image>
</template>

<style scoped>
.img-skeleton {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #cbd5e1;
  font-size: 12px;
  background: linear-gradient(100deg, #eef2f7 28%, #f8fafc 50%, #eef2f7 72%);
  background-size: 200% 100%;
  animation: img-shimmer 1.2s ease-in-out infinite;
}
.img-skeleton--error {
  animation: none;
  background: #f1f5f9;
}
@keyframes img-shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
