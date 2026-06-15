<template>
  <div class="map" :style="mapWrapperStyle">
    <canvas id="canvasMap"></canvas>
  </div>
</template>
<script setup>
import { onMounted, shallowRef, onBeforeUnmount, computed } from "vue";
import { World } from "./map.js";
import emitter from "@/utils/emitter";

const props = defineProps({
  /** 百分比，100 = 不变；作用于整层 WebGL 画布（CSS filter） */
  mapBrightness: { type: Number, default: 100 },
  mapContrast: { type: Number, default: 100 },
});

const mapWrapperStyle = computed(() => {
  const b = Math.max(40, Math.min(220, Number(props.mapBrightness) || 100));
  const c = Math.max(40, Math.min(220, Number(props.mapContrast) || 100));
  return {
    filter: `brightness(${b / 100}) contrast(${c / 100})`,
  };
});

const canvasMap = shallowRef(null);
onMounted(() => {
  emitter.$on("loadMap", loadMap);
});
onBeforeUnmount(() => {
  canvasMap.value && canvasMap.value.destroy();
  emitter.$off("loadMap", loadMap);
});
function loadMap(assets) {
  canvasMap.value = new World(document.getElementById("canvasMap"), assets);
  if (import.meta.env.DEV || new URLSearchParams(window.location.search).get("demo")) {
    window.__TIANSHU_MAP_WORLD__ = canvasMap.value;
  }
  canvasMap.value.time.pause();
}
async function play() {
  canvasMap.value.time.resume();
  canvasMap.value.animateTl.timeScale(1); // 设置播放速度正常
  canvasMap.value.animateTl.play();
}
function toggleDistrictDrill(name) {
  canvasMap.value?.toggleDistrictDrill?.(name);
}
defineExpose({
  loadMap,
  play,
  canvasMap,
  toggleDistrictDrill,
});
</script>

<style lang="scss">
.map {
  position: absolute;
  z-index: 1;
  left: 0;
  top: 0;
  right: 0;
  bottom: 0;
  background-color: #060d18;
  box-shadow:
    inset 0 0 140px rgba(0, 0, 0, 0.52),
    inset 0 0 48px rgba(56, 189, 248, 0.04);
  .info-point {
    background: rgba(0, 0, 0, 0.5);
    color: #a3dcde;
    font-size: 14px;
    width: 170px;
    height: 106px;
    padding: 16px 12px 0;
    margin-bottom: 30px;
    will-change: transform;
    &-wrap {
      &:after,
      &:before {
        display: block;
        content: "";
        position: absolute;
        top: 0;
        width: 15px;
        height: 15px;
        border-top: 1px solid #4b87a6;
      }
      &:before {
        left: 0;
        border-left: 1px solid #4b87a6;
      }
      &:after {
        right: 0;
        border-right: 1px solid #4b87a6;
      }
      &-inner {
        &:after,
        &:before {
          display: block;
          content: "";
          position: absolute;
          bottom: 0;
          width: 15px;
          height: 15px;
          border-bottom: 1px solid #4b87a6;
        }
        &:before {
          left: 0;
          border-left: 1px solid #4b87a6;
        }
        &:after {
          right: 0;
          border-right: 1px solid #4b87a6;
        }
      }
    }
    &-line {
      position: absolute;
      top: 7px;
      right: 12px;
      display: flex;
      .line {
        width: 5px;
        height: 2px;
        margin-right: 5px;
        background: #17e5c3;
      }
    }
    &-content {
      .content-item {
        display: flex;
        height: 28px;
        line-height: 28px;
        background: rgba(35, 47, 58, 0.6);
        margin-bottom: 5px;
        .label {
          width: 60px;
          padding-left: 10px;
        }
        .value {
          color: #ffffff;
        }
      }
    }
    /** 订单光柱悬停：原 info-point 固定 170×106 与行高 28 会导致长地址/客户名叠字 */
    &.info-point--order {
      width: 288px;
      min-width: 240px;
      height: auto;
      min-height: 0;
      max-width: min(320px, 92vw);
      padding: 14px 12px 12px;
      box-sizing: border-box;
      .info-point-wrap-inner {
        position: relative;
      }
      .info-point-content .content-item {
        height: auto;
        min-height: 32px;
        line-height: 1.45;
        align-items: flex-start;
        padding: 8px 6px;
        margin-bottom: 6px;
        box-sizing: border-box;
        gap: 8px;
        &:last-child {
          margin-bottom: 0;
        }
        .label {
          flex-shrink: 0;
          width: 44px;
          padding: 2px 0 0 8px;
          line-height: 1.35;
          color: rgba(163, 220, 222, 0.95);
        }
        .value {
          flex: 1;
          min-width: 0;
          word-break: break-word;
          overflow-wrap: anywhere;
          white-space: normal;
          padding-right: 6px;
        }
        &.content-item--metrics .value {
          display: flex;
          flex-direction: column;
          align-items: flex-start;
          gap: 4px;
          .order-metric {
            display: block;
            line-height: 1.35;
          }
          .order-metric--gmv {
            color: #7efbf6;
            font-weight: 600;
          }
        }
      }
    }
  }
  .provinces-label {
    &-wrap {
      transform: translate(50%, 200%);
      opacity: 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0 18px;
      width: 200px;
      height: 53px;
      border-radius: 30px 30px 30px 0px;
      background: rgba(0, 0, 0, 0.4);
    }
    .number {
      color: #fff;
      font-size: 30px;
      font-weight: 700;

      .unit {
        color: #fff;
        font-size: 12px;
        font-weight: 400;
        opacity: 0.5;
        padding-left: 5px;
      }
    }
    .name {
      color: #fff;
      font-size: 16px;
      font-weight: 700;
      span {
        display: block;
      }
      .en {
        color: #fff;
        font-size: 10px;
        opacity: 0.5;
        font-weight: 700;
      }
    }
    .no {
      color: #7efbf6;
      text-shadow: 0 0 5px #7efbf6, 0 0 10px #7efbf6;
      font-size: 30px;
      font-weight: 700;
    }
    .yellow {
      .no {
        color: #fef99e !important;
        text-shadow: 0 0 5px #fef99e, 0 0 10px #fef99e !important;
      }
    }
  }

  .china-label {
    color: #fff;

    font-size: 12px;
    will-change: transform;
    .other-label {
      display: flex;
      align-items: center;
      padding: 5px;
      border-radius: 4px;
      background: rgba(0, 0, 0, 0.6);
      will-change: transform;
    }

    &.blur {
      filter: blur(2px);
      opacity: 0.5;
    }
    .label-icon {
      display: block;
      width: 20px;
      height: 20px;
      margin: 0 10px 0 0;
    }
  }
  .map-label {
    padding: 5px;
    color: #fff;
    will-change: transform;
    font-size: 36px;
    font-weight: bold;
    letter-spacing: 4.5px;
    -webkit-box-reflect: below 0 -webkit-linear-gradient(transparent, transparent
          20%, rgba(255, 255, 255, 0.3));
    .other-label {
      display: flex;
      flex-direction: column;
    }
    span {
      font-size: 46px;
      &:last-child {
        font-size: 12px;
        font-weight: normal;
        letter-spacing: 0px;
        color: #a7d5ef;
      }
    }
  }
  .decoration-label {
    // &.reflect {
    //   -webkit-box-reflect: below 0 -webkit-linear-gradient(transparent, transparent 20%, rgba(255, 255, 255, 0.3));
    // }
    // padding-bottom: 10px;
    .label-icon {
      display: block;
      width: 40px;
      height: 40px;
    }
  }
  .other-label {
    transform: translateY(200%);
    opacity: 0;
    background: none;
    will-change: transform;
  }
}
</style>
