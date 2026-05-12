<template>
  <view class="page">
    <view class="bg-glow" aria-hidden="true" />
    <view class="bg-grid" aria-hidden="true" />

    <view class="center-wrap">
      <view class="card">
        <view class="card-head">
          <view class="logo-mark">
            <text class="logo-char">收</text>
          </view>
          <text class="brand">大综 · 智能收货</text>
          <text class="sub">甲方现场终端 · 对接 client 账号</text>
          <view class="head-line" />
        </view>

        <view class="field">
          <text class="label">用户名</text>
          <view class="input-shell">
            <input v-model="username" class="input" placeholder="请输入 client 端账号" placeholder-class="ph" />
          </view>
        </view>
        <view class="field">
          <text class="label">密码</text>
          <view class="input-shell">
            <input v-model="password" class="input" password placeholder="请输入密码" placeholder-class="ph" />
          </view>
        </view>

        <button class="btn primary" :loading="loading" @click="onLogin">登 录</button>
        <button class="btn ghost" @click="demoEnter">演示进入（不调接口）</button>

        <text class="foot-hint">首次使用请确认网络与服务器地址配置正确</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { request, setToken } from "../../utils/request";

const username = ref("");
const password = ref("");
const loading = ref(false);

async function onLogin() {
  if (!username.value || !password.value) {
    uni.showToast({ title: "请填写账号密码", icon: "none" });
    return;
  }
  loading.value = true;
  try {
    const data = await request<{ token: string }>("/auth/login", {
      method: "POST",
      data: {
        username: username.value,
        password: password.value,
      },
    });
    const token = data.token;
    if (!token) {
      throw new Error("无 token");
    }
    setToken(token);
    uni.showToast({ title: "登录成功", icon: "success" });
    uni.reLaunch({ url: "/pages/dashboard/dashboard" });
  } catch {
    uni.showModal({
      title: "登录失败",
      content: "请检查网络与 API_BASE，或使用「演示进入」查看界面流程。",
      showCancel: false,
    });
  } finally {
    loading.value = false;
  }
}

function demoEnter() {
  setToken("demo");
  uni.reLaunch({ url: "/pages/dashboard/dashboard" });
}
</script>

<style scoped lang="scss">
@import "@/uni.scss";

.page {
  position: relative;
  min-height: 100vh;
  width: 100%;
  overflow: hidden;
  box-sizing: border-box;
  padding: calc(env(safe-area-inset-top) + 32rpx) 48rpx calc(env(safe-area-inset-bottom) + 32rpx);
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, #cfe8d8 0%, #e2f0e8 35%, #f0f6f2 65%, #f8faf9 100%);
}

.bg-glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 90% 60% at 50% -10%, rgba(27, 94, 58, 0.18) 0%, transparent 55%),
    radial-gradient(ellipse 60% 50% at 105% 110%, rgba(0, 166, 90, 0.08) 0%, transparent 50%);
}

.bg-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.25;
  background-image:
    linear-gradient(rgba(27, 94, 58, 0.06) 1rpx, transparent 1rpx),
    linear-gradient(90deg, rgba(27, 94, 58, 0.06) 1rpx, transparent 1rpx);
  background-size: 56rpx 56rpx;
}

.center-wrap {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 640rpx;
}

.card {
  background: rgba(255, 255, 255, 0.95);
  border-radius: 32rpx;
  padding: 56rpx 48rpx 44rpx;
  box-shadow: 0 4rpx 24rpx rgba(13, 43, 29, 0.07), 0 24rpx 64rpx rgba(27, 94, 58, 0.10);
  border: 1rpx solid rgba(255, 255, 255, 0.9);
}

.card-head {
  text-align: center;
  margin-bottom: 48rpx;
}

.logo-mark {
  width: 96rpx;
  height: 96rpx;
  margin: 0 auto 28rpx;
  border-radius: 28rpx;
  background: linear-gradient(145deg, #27794d 0%, #1b5e3a 60%, $c-primary-dark 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 24rpx rgba(27, 94, 58, 0.30), 0 2rpx 6rpx rgba(27, 94, 58, 0.20);
}

.logo-char {
  font-size: 48rpx;
  font-weight: 800;
  color: #ffffff;
}

.brand {
  display: block;
  font-size: 40rpx;
  font-weight: 800;
  color: $c-text-h;
  letter-spacing: 3rpx;
}

.sub {
  display: block;
  margin-top: 12rpx;
  font-size: 24rpx;
  color: $c-text-m;
  line-height: 1.5;
  letter-spacing: 1rpx;
}

.head-line {
  width: 64rpx;
  height: 4rpx;
  margin: 24rpx auto 0;
  border-radius: 4rpx;
  background: linear-gradient(90deg, transparent, $c-primary, transparent);
  opacity: 0.5;
}

.field {
  margin-bottom: 28rpx;
}

.label {
  display: block;
  font-size: 24rpx;
  font-weight: 700;
  color: $c-text-b;
  margin-bottom: 12rpx;
  padding-left: 2rpx;
  letter-spacing: 1rpx;
}

.input-shell {
  border-radius: $r-btn;
  background: #f4f8f5;
  border: 2rpx solid $c-border;
}

.input {
  width: 100%;
  height: 92rpx;
  padding: 0 28rpx;
  box-sizing: border-box;
  font-size: 30rpx;
  color: $c-text-h;
}

.ph {
  color: $c-text-hint;
  font-size: 26rpx;
}

.btn {
  margin-top: 20rpx;
  border-radius: $r-btn;
  font-size: 30rpx;
  font-weight: 700;
  height: 96rpx;
  line-height: 96rpx;
}

.primary {
  margin-top: 40rpx;
  background: linear-gradient(160deg, #27794d 0%, $c-primary 100%);
  color: #fff;
  border: none;
  letter-spacing: 6rpx;
  box-shadow: 0 8rpx 24rpx rgba(27, 94, 58, 0.28), 0 2rpx 8rpx rgba(27, 94, 58, 0.16);
}

.ghost {
  background: transparent;
  color: $c-primary;
  border: 2rpx solid $c-border-med;
  font-weight: 500;
  letter-spacing: 1rpx;
}

.foot-hint {
  display: block;
  text-align: center;
  margin-top: 28rpx;
  font-size: 22rpx;
  color: $c-text-hint;
  line-height: 1.5;
}
</style>
