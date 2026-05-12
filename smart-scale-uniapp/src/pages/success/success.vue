<template>
  <view class="page">
    <text class="icon">✓</text>
    <text class="title">已提交</text>
    <text class="sub">退差/收货接口联调前，此处为占位流程结束。</text>
    <button class="btn primary" @click="backList">返回订单列表</button>
  </view>
</template>

<script setup lang="ts">
function backList() {
  uni.navigateBack({ delta: 1 });
}
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.page {
  min-height: 100vh;
  background: linear-gradient(160deg, #d4edde 0%, #e8f5ec 45%, $c-bg 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 140rpx 48rpx 80rpx;
  box-sizing: border-box;
}

.icon {
  width: 128rpx;
  height: 128rpx;
  line-height: 128rpx;
  text-align: center;
  border-radius: 64rpx;
  background: linear-gradient(145deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  font-size: 68rpx;
  margin-bottom: 36rpx;
  box-shadow: 0 12rpx 36rpx rgba(27, 94, 58, 0.28), 0 4rpx 12rpx rgba(27, 94, 58, 0.18);
}

.title {
  font-size: 44rpx;
  font-weight: 800;
  color: $c-text-h;
  letter-spacing: 2rpx;
}

.sub {
  margin: 20rpx 0 56rpx;
  font-size: 26rpx;
  color: $c-text-m;
  text-align: center;
  line-height: 1.55;
  max-width: 480rpx;
}

.btn {
  width: 100%;
  max-width: 560rpx;
  height: 96rpx;
  line-height: 96rpx;
  border-radius: $r-btn;
  font-size: 30rpx;
  font-weight: 700;
}

.primary {
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  border: none;
  letter-spacing: 4rpx;
  box-shadow: 0 8rpx 24rpx rgba(27, 94, 58, 0.26), 0 2rpx 8rpx rgba(27, 94, 58, 0.16);
}
</style>
