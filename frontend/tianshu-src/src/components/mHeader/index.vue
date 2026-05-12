<template>
  <div class="m-header">
    <div class="m-header-wrap" :class="{ 'm-header-wrap--brand': hasBrand }">
      <slot name="brand">
        <div class="m-header-title">{{ title }}</div>
        <div class="m-header-subtext">{{ subText }}</div>
      </slot>
    </div>
    <div class="m-header-left" style="color: #fff">
      <slot name="left"></slot>
    </div>
    <div class="m-header-right"><slot name="right"></slot></div>
    <div class="m-header-line">
      <mSvglineAnimation
        class="m-header-line-left"
        :width="961"
        :height="79"
        color="#67e8f9"
        :strokeWidth="1.5"
        :dir="[0, 1]"
        :length="100"
        path="M1 1.52783L535 25.6808C552.73 26.5835 571.454 31.3851 588.834 39.2194C593.758 41.4385 598.692 43.7289 603.643 46.0273C633.567 59.9182 664.121 74.1016 696.754 74.6262C696.765 74.6264 696.775 74.6265 696.786 74.6267C821.602 76.5993 879.336 78 961 78"
      ></mSvglineAnimation>
      <mSvglineAnimation
        class="m-header-line-right"
        :width="961"
        :height="79"
        color="#67e8f9"
        :strokeWidth="1.5"
        :dir="[0, 1]"
        :length="100"
        path="M1 1.52783L535 25.6808C552.73 26.5835 571.454 31.3851 588.834 39.2194C593.758 41.4385 598.692 43.7289 603.643 46.0273C633.567 59.9182 664.121 74.1016 696.754 74.6262C696.765 74.6264 696.775 74.6265 696.786 74.6267C821.602 76.5993 879.336 78 961 78"
      ></mSvglineAnimation>
    </div>
  </div>
</template>
<script setup>
import { computed, useSlots } from "vue"
import mSvglineAnimation from "@/components/mSvglineAnimation/index.vue"

defineProps({
  title: {
    type: String,
    default: "数据可视化大屏",
  },
  subText: {
    type: String,
    default: "Visualization Platform",
  },
})

const slots = useSlots()
const hasBrand = computed(() => !!slots.brand)
</script>
<style lang="scss">
.m-header {
  position: relative;
  left: 0;
  top: 0;
  right: 0;
  width: 100%;
  height: 90px;
  z-index: 2;
  &-wrap {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);

    width: 1920px;
    height: 90px;
    margin: 0 auto;
    background: url("~@/assets/images/header-bg.png");
    background-size: 100%;
    text-align: center;
    box-sizing: border-box;
    padding-top: 10px;
    filter: drop-shadow(0 10px 36px rgba(0, 0, 0, 0.5));

    &::after {
      content: "";
      position: absolute;
      left: 10%;
      right: 10%;
      top: 4px;
      height: 58px;
      pointer-events: none;
      background: radial-gradient(ellipse 100% 120% at 50% 0%, rgba(103, 232, 249, 0.14), transparent 70%);
      opacity: 0.85;
      mix-blend-mode: screen;
    }

    &--brand {
      display: flex;
      align-items: center;
      justify-content: center;
      padding-top: 4px;
      filter: drop-shadow(0 10px 36px rgba(0, 0, 0, 0.5)) drop-shadow(0 8px 28px rgba(0, 0, 0, 0.38))
        drop-shadow(0 0 46px rgba(56, 189, 248, 0.07));
    }
  }

  &-title {
    color: #fff;
    font-size: 44px;
    letter-spacing: 1px;
    font-family: "YouSheBiaoTiHei", "阿里妈妈数黑体 Bold";
    background: -webkit-linear-gradient(rgba(117, 232, 255, 1), rgba(255, 255, 255, 1));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  &-subtext {
    opacity: 0.64;
    font-size: 12px;
    letter-spacing: 3px;
    font-weight: 300;
    font-family: "D-DIN";
    line-height: 14.4px;
    color: rgba(196, 243, 254, 1);
  }
  &-left {
    color: #fff;
    position: absolute;
    top: 47px;
    left: 32px;
  }
  &-right {
    color: #fff;
    position: absolute;
    top: 47px;
    right: 32px;
  }
  &-line {
    &-left {
      position: absolute;
      right: 50%;
      top: 11px;
      width: 961px;
      height: 79px;
      margin-right: 14px;
    }
    &-right {
      position: absolute;
      left: 50%;
      top: 11px;
      width: 961px;
      height: 79px;
      margin-left: -14px;
      transform: scaleX(-1);
    }
    &-left-top {
      position: absolute;
      right: 50%;
      top: -6px;
      width: 329px;
      height: 30px;
      margin-right: 295px;
    }
    &-right-top {
      position: absolute;
      left: 50%;
      top: -6px;
      width: 329px;
      height: 30px;
      margin-left: 293px;
      transform: scaleX(-1);
    }
  }
}
</style>
