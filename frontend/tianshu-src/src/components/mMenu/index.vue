<template>
  <div class="m-menu">
    <slot></slot>
  </div>
</template>
<script setup>
import { defineComponent, ref, onMounted, watch, provide } from "vue";
const emit = defineEmits(["select"]);
const props = defineProps({
  defaultActive: {
    type: [String, Number],
    default: "",
  },
});
const activeIndex = ref(props.defaultActive);
// 提供一个方法来供子组件调用，用于更新活动项
const updateActive = (index) => {
  activeIndex.value = index;
  emit("select", index);
};
// 使用 provide 使得子组件可以访问 updateActive
provide("updateActive", updateActive);
provide("activeIndex", activeIndex);
// 监听 props.defaultActive 的变化，以便从外部更新时同步内部状态
watch(
  () => props.defaultActive,
  (newVal) => {
    if (newVal !== activeIndex.value) {
      activeIndex.value = newVal;
    }
  }
);
</script>
<style lang="scss">
.m-menu {
  display: flex;
  &-item {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    pointer-events: all;
    justify-content: center;
    width: 100px;
    height: 32px;
    background-image: url("~@/assets/images/menu-btn.png");
    background-size: 100%;
    color: rgba(255, 255, 255, 0.6);
    font-size: 16px;
    margin: 0 12px;

    cursor: pointer;
    transition:
      filter 0.28s ease,
      transform 0.28s ease;

    &:hover {
      filter: drop-shadow(0 0 14px rgba(103, 232, 249, 0.45));
      transform: translateY(-1px);
    }

    &:hover,
    &.is-active {
      color: rgba(255, 255, 255, 1);
      background-image: url("~@/assets/images/menu-btn-hover.png");
    }
    &.is-active {
      filter: drop-shadow(0 0 18px rgba(103, 232, 249, 0.55));
      &:after {
        display: block;
        width: 100px;
        height: 32px;
        background-size: 100%;
        content: "";
        position: absolute;
        left: 50%;
        top: 50%;
        margin-left: -50px;
        margin-top: -16px;
        z-index: -1;
        opacity: 1;
        background: radial-gradient(
          ellipse at 50% 50%,
          rgba(103, 232, 249, 0.55) 0%,
          rgba(56, 189, 248, 0.22) 55%,
          transparent 72%
        );
        border-radius: 32px;
        transform: scale(1.1, 1.2);
        animation: menuActiveScale 1.1s infinite;
        box-shadow: 0 0 22px rgba(103, 232, 249, 0.35);
      }
    }
  }
}
@keyframes menuActiveScale {
  0% {
    transform: scale(1);
    opacity: 0.85;
  }
  50% {
    transform: scale(1.12, 1.24);
    opacity: 1;
  }
  100% {
    transform: scale(1.12, 1.24);
    opacity: 0;
  }
}
@media (prefers-reduced-motion: reduce) {
  .m-menu-item:hover {
    transform: none;
  }
}
</style>
