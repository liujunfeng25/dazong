<template>
  <div class="count-card">
    <div class="count-card-left">
      <div class="count-card-icon" :class="'icon-' + info.icon"></div>
      <div class="count-card-title">
        <div class="title-zh">{{ info.zh }}</div>
        <div class="title-en">{{ toUpper(info.en) }}</div>
      </div>
    </div>
    <div class="count-card-right">
      <div class="value">
        <TianshuDigitalFlop
          :value="info.value"
          :decimals="info.decimals ?? 0"
          :duration="1050"
          easing="cubic-bezier(0.33, 1, 0.68, 1)"
        />
      </div>
      <div class="unit">{{ info.unit }}</div>
    </div>
  </div>
</template>
<script setup>
import TianshuDigitalFlop from "@/components/TianshuDigitalFlop/TianshuDigitalFlop.vue"

defineProps({
  info: {
    type: Object,
    default: () => {
      return {
        icon: "xiaoshoujine",
        zh: "2023年销售金额",
        en: "Sales amount in 2023",
        value: 9500,
        unit: "元",
        decimals: 0,
      }
    },
  },
})
function toUpper(text) {
  return text.toUpperCase()
}
</script>
<style lang="scss">
.count-card {
  display: flex;
  align-items: center;
  &-left {
    display: flex;
    align-items: center;
  }
  &-right {
    display: flex;
    align-items: flex-end;
    padding-left: 20px;
    .value {
      font-family: D-DIN;
      font-weight: bold;
      font-size: 28px;
      color: #ffffff;
      letter-spacing: 0;
      margin-right: 10px;
      white-space: nowrap;
      line-height: 1;
    }
    .unit {
      font-weight: 500;
      font-size: 12px;
      color: #ffffff;
      padding-bottom: 2px;
      opacity: 0.5;
      white-space: nowrap;
    }
  }
  &-icon {
    width: 58px;
    height: 58px;
    margin-right: 10px;
    background-repeat: no-repeat;
    background-position: center center;
    background-size: 100%;
    // 2023销售金额
    &.icon-xiaoshoujine {
      background-image: url("~@/assets/images/icon1.png");
    }
    // 2023总销量
    &.icon-zongxiaoliang {
      background-image: url("~@/assets/images/icon2.png");
    }
  }
  &-title {
    .title-zh {
      font-weight: bold;
      font-size: 18px;
      white-space: nowrap;
      background: linear-gradient(185deg, rgba(236, 254, 255, 1) 0%, rgba(186, 240, 255, 0.95) 100%);
      -webkit-background-clip: text;
      background-clip: text;
      -webkit-text-fill-color: transparent;
      text-shadow: 0 2px 18px rgba(56, 189, 248, 0.08);
    }
    .title-en {
      font-family: D-DIN;
      font-weight: 400;
      font-size: 12px;
      color: rgba(196, 236, 255, 0.62);
      padding-top: 5px;
      white-space: nowrap;
    }
  }
}
</style>
