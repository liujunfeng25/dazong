<template>
  <div
    ref="spectacleRootRef"
    class="large-screen"
    :class="{ 'tianshu-spectacle-fs-active': spectacleFullscreen }"
  >
    <div class="tianshu-spectacle-bg-drift" aria-hidden="true" />
    <!-- 地图 -->
    <div
      class="tianshu-map-shell tianshu-shell-enter tianshu-shell-enter--map"
      :class="{ 'is-visible': shellEnterReady }"
    >
      <mapScene
        ref="mapSceneRef"
        :map-brightness="mapToneBrightness"
        :map-contrast="mapToneContrast"
      ></mapScene>
      <div class="tianshu-spectacle-map-beam" aria-hidden="true" />
    </div>
    <div class="tianshu-spectacle-aurora" aria-hidden="true" />
    <div class="tianshu-spectacle-floaties" aria-hidden="true" />
    <div class="tianshu-ai-bitwash" aria-hidden="true" />
    <div class="large-screen-wrap" id="large-screen">
      <m-header>
        <template #brand>
          <div class="tianshu-brand">
            <p class="tianshu-brand-eyebrow">大宗天枢</p>
            <div class="tianshu-brand-row">
              <span class="tianshu-brand-slogan tianshu-brand-slogan--left">全域监管</span>
              <span class="tianshu-brand-divider" aria-hidden="true" />
              <span class="tianshu-brand-slogan tianshu-brand-slogan--right">供应协同</span>
            </div>
          </div>
        </template>
        <!--左侧 天气 -->
        <template v-slot:left>
          <div class="m-header-weather"><span>小雨</span><span>27℃</span></div>
        </template>
        <!--右侧 日期 -->
        <template v-slot:right>
          <div class="m-header-date">
            <button
              type="button"
              class="tianshu-spectacle-fs-btn"
              :title="
                spectacleFullscreen
                  ? '退出全屏（Esc 也可退出）'
                  : '大屏模式：仅大屏内容全屏，不含主站左侧导航'
              "
              @click="toggleSpectacleFullscreen"
            >
              {{ spectacleFullscreen ? "退出全屏" : "大屏模式" }}
            </button>
            <div class="m-header-date__clock">
              <span>{{ clock.date }}</span><span>{{ clock.time }}</span>
            </div>
            <button
              v-show="mapDrillActive || selectedDistrictName"
              type="button"
              class="map-drill-back-btn map-drill-back-btn--under-clock"
              @click="resetMapDrill"
            >
              返回全市
            </button>
          </div></template
        >
      </m-header>
      <!-- 顶部菜单 -->
      <div class="top-menu">
        <mMenu :default-active="state.activeIndex" @select="handleMenuSelect">
          <mMenuItem index="1">经济概览</mMenuItem>
          <mMenuItem index="2">供应链履约</mMenuItem>
          <mMenuItem index="3">冷链运力</mMenuItem>
          <div class="top-menu-mid-space"></div>
          <mMenuItem index="4">城市画像</mMenuItem>
          <mMenuItem index="5">产业洞察</mMenuItem>
          <mMenuItem index="6">风险预警</mMenuItem>
        </mMenu>
      </div>
      <!-- 顶部统计卡片 -->
      <div
        class="top-count-card tianshu-shell-enter tianshu-shell-enter--kpi"
        :class="{ 'is-visible': shellEnterReady, 'tianshu-kpi-pulse': kpiPulseActive }"
      >
        <mCountCard v-for="(item, index) in state.totalView" :info="item" :key="index"></mCountCard>
      </div>
      <!-- 订单光柱悬停明细：固定在大屏地图区左上，避免 CSS3D 随视距过小 -->
      <div
        v-show="orderHover"
        class="tianshu-order-hover-dock"
        aria-live="polite"
      >
        <div
          class="tianshu-order-hover-dock__inner"
          :class="{ 'tianshu-order-hover-dock__inner--hq': orderHover?.isHeadquarters }"
        >
          <div class="tianshu-order-hover-dock__accent" aria-hidden="true">
            <span></span><span></span><span></span>
          </div>
          <template v-if="orderHover?.isHeadquarters">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--hq">
              {{ orderHover.headquartersTitle || "监管指挥中心" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">位置</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.address || "—" }}</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag">大宗监管 · 指挥中心</p>
          </template>
          <template v-else>
            <div class="tianshu-order-hover-dock__head">订单概览</div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">地址</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.address || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">客户</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.customer_name || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row tianshu-order-hover-dock__row--metrics">
              <span class="tianshu-order-hover-dock__label">今日</span>
              <div class="tianshu-order-hover-dock__metrics">
                <span class="tianshu-order-hover-dock__metric">{{ orderHover?.order_count ?? 0 }} 单</span>
                <span class="tianshu-order-hover-dock__metric tianshu-order-hover-dock__metric--gmv">{{
                  orderHoverGmvText
                }}</span>
              </div>
            </div>
          </template>
        </div>
      </div>
      <!-- 左边布局 图表 -->
      <div class="left-wrap">
        <div
          class="left-wrap-3d tianshu-shell-enter tianshu-shell-enter--col-left"
          :class="{ 'is-visible': shellEnterReady }"
        >
          <!-- 大宗商品销售额 -->
          <BulkCommoditySalesChart></BulkCommoditySalesChart>
          <!-- 年度经济增长点 -->
          <YearlyEconomyTrend></YearlyEconomyTrend>
          <!-- 近年经济情况 -->
          <EconomicTrendChart></EconomicTrendChart>
          <!-- 各区经济收益 -->
          <DistrictEconomicIncome></DistrictEconomicIncome>
        </div>
      </div>
      <!-- 右边布局 图表 -->
      <div class="right-wrap">
        <div
          class="right-wrap-3d tianshu-shell-enter tianshu-shell-enter--col-right"
          :class="{ 'is-visible': shellEnterReady }"
        >
          <!-- 专项资金用途 -->
          <PurposeSpecialFunds> </PurposeSpecialFunds>
          <!-- 人群消费占比 -->
          <ProportionPopulationConsumption></ProportionPopulationConsumption>
          <!-- 用电情况 -->
          <ElectricityUsage></ElectricityUsage>
          <!-- 各季度增长情况 -->
          <QuarterlyGrowthSituation></QuarterlyGrowthSituation>
        </div>
      </div>
      <!-- 底部托盘 -->
      <div class="bottom-tray">
        <!-- svg线条动画 -->
        <mSvglineAnimation
          class="bottom-svg-line-left"
          :width="721"
          :height="57"
          color="#67e8f9"
          :strokeWidth="1.5"
          :dir="[0, 1]"
          :length="50"
          path="M1 56.6105C1 31.5123 185.586 10.0503 451.904 1.35519C458.942 1.12543 465.781 4.00883 470.505 9.22964L484.991 25.2383C487.971 28.4775 492.938 30.4201 498.254 30.4201H720.142"
        ></mSvglineAnimation>
        <mSvglineAnimation
          class="bottom-svg-line-left bottom-svg-line-right"
          :width="721"
          :height="57"
          color="#67e8f9"
          :strokeWidth="1.5"
          :dir="[0, 1]"
          :length="50"
          path="M1 56.6105C1 31.5123 185.586 10.0503 451.904 1.35519C458.942 1.12543 465.781 4.00883 470.505 9.22964L484.991 25.2383C487.971 28.4775 492.938 30.4201 498.254 30.4201H720.142"
        ></mSvglineAnimation>
        <!-- 做箭头 -->
        <div class="bottom-tray-arrow">
          <img src="@/assets/images/bottom-menu-arrow-big.svg" alt="" />
          <img src="@/assets/images/bottom-menu-arrow-small.svg" alt="" />
        </div>
        <!-- 底部菜单 -->
        <div class="bottom-menu">
          <div class="bottom-menu-item is-active"><span>全景态势</span></div>
          <div class="bottom-menu-item"><span>订单光柱</span></div>
          <div class="bottom-menu-item"><span>履约热力</span></div>
          <div class="bottom-menu-item"><span>异常预警</span></div>
        </div>
        <!-- 右箭头 -->
        <div class="bottom-tray-arrow is-reverse">
          <img src="@/assets/images/bottom-menu-arrow-big.svg" alt="" />
          <img src="@/assets/images/bottom-menu-arrow-small.svg" alt="" />
        </div>
      </div>
      <!-- 实时链路：心电图与运营指挥台一致；GMV/单量由 WebSocket snapshot/batch 更新 -->
      <div
        class="tianshu-ops-console tianshu-shell-enter tianshu-shell-enter--ops"
        :class="{
          'is-visible': shellEnterReady,
          'is-ping-tick': opsConsole.beatFlash,
        }"
        aria-label="实时链路 WebSocket"
      >
        <div class="tianshu-ops-console__inner">
          <div class="tianshu-ops-console__badge">
            <div class="tianshu-ops-console__badge-line">
              <span
                class="tianshu-ops-console__dot"
                :class="{
                  'is-live': opsConsole.wsConnected,
                  'is-ping': opsConsole.pingPulse,
                }"
                :title="opsConsole.wsConnected ? 'WebSocket 已连接' : '连接断开或重连中'"
              />
              <span class="tianshu-ops-console__badge-text">实时链路</span>
              <span class="tianshu-ops-console__chip">LIVE-GMV</span>
            </div>
            <div
              class="tianshu-ops-ecg"
              :class="{
                'tianshu-ops-ecg--live': opsConsole.wsConnected,
                'tianshu-ops-ecg--beat': opsConsole.beatFlash,
              }"
              role="img"
              aria-label="实时通道心电图"
            >
              <!-- 与运营指挥台 PanelOpsDataFreshness「实时通道」一致：仅滚动波形常显；emp-bloom/beam 仅在 ping 时由 --beat 触发 -->
              <div class="tianshu-ops-ecg__glass" aria-hidden="true">
                <div class="tianshu-ops-ecg__emp-bloom" />
                <div class="tianshu-ops-ecg__emp-beam" />
                <svg
                  class="tianshu-ops-ecg__svg"
                  viewBox="0 0 80 36"
                  preserveAspectRatio="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <defs>
                    <linearGradient id="tianshuOpsEcgGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stop-color="rgba(34, 211, 238, 0.35)" />
                      <stop offset="45%" stop-color="rgba(103, 232, 249, 0.85)" />
                      <stop offset="100%" stop-color="rgba(234, 179, 8, 0.45)" />
                    </linearGradient>
                    <filter id="tianshuOpsEcgGlow" x="-20%" y="-20%" width="140%" height="140%">
                      <feGaussianBlur stdDeviation="0.8" result="b" />
                      <feMerge>
                        <feMergeNode in="b" />
                        <feMergeNode in="SourceGraphic" />
                      </feMerge>
                    </filter>
                  </defs>
                  <g v-if="opsConsole.wsConnected" class="tianshu-ops-ecg__scroll">
                    <g>
                      <animateTransform
                        attributeName="transform"
                        type="translate"
                        from="0 0"
                        to="-80 0"
                        dur="10s"
                        repeatCount="indefinite"
                      />
                      <path
                        class="tianshu-ops-ecg__wave"
                        fill="none"
                        stroke="url(#tianshuOpsEcgGrad)"
                        stroke-width="1.35"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        vector-effect="non-scaling-stroke"
                        filter="url(#tianshuOpsEcgGlow)"
                        d="M0,18 L8,18 L10,18 L12,7 L14,18 L20,18 L28,18 L30,9 L32,18 L40,18 L48,18 L50,13 L52,23 L54,18 L80,18"
                      />
                      <path
                        class="tianshu-ops-ecg__wave"
                        fill="none"
                        stroke="url(#tianshuOpsEcgGrad)"
                        stroke-width="1.35"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        vector-effect="non-scaling-stroke"
                        filter="url(#tianshuOpsEcgGlow)"
                        transform="translate(80,0)"
                        d="M0,18 L8,18 L10,18 L12,7 L14,18 L20,18 L28,18 L30,9 L32,18 L40,18 L48,18 L50,13 L52,23 L54,18 L80,18"
                      />
                      <path
                        class="tianshu-ops-ecg__wave"
                        fill="none"
                        stroke="url(#tianshuOpsEcgGrad)"
                        stroke-width="1.35"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                        vector-effect="non-scaling-stroke"
                        filter="url(#tianshuOpsEcgGlow)"
                        transform="translate(160,0)"
                        d="M0,18 L8,18 L10,18 L12,7 L14,18 L20,18 L28,18 L30,9 L32,18 L40,18 L48,18 L50,13 L52,23 L54,18 L80,18"
                      />
                    </g>
                  </g>
                  <path
                    v-else
                    class="tianshu-ops-ecg__flat"
                    fill="none"
                    stroke="rgba(148, 163, 184, 0.45)"
                    stroke-width="1.2"
                    vector-effect="non-scaling-stroke"
                    d="M0,18 L80,18"
                  />
                </svg>
              </div>
            </div>
          </div>
          <div class="tianshu-ops-console__metric">
            <span class="tianshu-ops-console__k">链路</span>
            <span class="tianshu-ops-console__v">{{ opsConsole.wsConnected ? "在线" : "重连" }}</span>
          </div>
          <div class="tianshu-ops-console__metric">
            <span class="tianshu-ops-console__k">心跳</span>
            <span class="tianshu-ops-console__v tianshu-ops-console__v--heartbeat">{{
              opsConsole.heartbeatInline
            }}</span>
          </div>
          <div class="tianshu-ops-console__metric">
            <span class="tianshu-ops-console__k">今日 GMV</span>
            <span class="tianshu-ops-console__v"
              >¥{{ opsConsole.liveGmvYuan }}<small>元</small></span
            >
          </div>
          <div class="tianshu-ops-console__metric">
            <span class="tianshu-ops-console__k">今日下单</span>
            <span class="tianshu-ops-console__v"
              >{{ opsConsole.liveOrderCount != null ? opsConsole.liveOrderCount : "—"
              }}<small>单</small></span
            >
          </div>
          <div
            class="tianshu-ops-console__viz tianshu-ops-console__viz--clickable"
            role="button"
            tabindex="0"
            title="点击查看今日订单列表"
            aria-label="打开今日订单列表"
            @click="openTodayOrdersListFromOps"
            @keydown.enter.prevent="openTodayOrdersListFromOps"
            @keydown.space.prevent="openTodayOrdersListFromOps"
          >
            <span
              v-for="(h, idx) in opsConsole.activityBars"
              :key="idx"
              class="tianshu-ops-console__bar"
              :style="{ height: `${h}%` }"
            />
          </div>
        </div>
      </div>
      <!-- 雷达 -->
      <div class="bottom-radar">
        <mRadar></mRadar>
      </div>
      <!-- 左右装饰线 -->
      <div class="large-screen-left-zsline"></div>
      <div class="large-screen-right-zsline"></div>
      <!-- 展会正式包隐藏调试条；本地 dev 或 URL ?mapTune=1 可调地图配色/挤出 -->
      <div
        v-if="tianshuShowDevTools || mapVisualTuneEligible"
        class="camera-debug-ui-host"
      >
        <div class="camera-debug-toolbar">
          <template v-if="tianshuShowDevTools">
            <button
              type="button"
              class="camera-debug-toggle"
              :class="{ 'is-active': cameraDebugOpen }"
              @click="toggleCameraDebug"
            >
              相机调试
            </button>
            <button
              type="button"
              class="camera-debug-toggle camera-debug-toggle--reset"
              @click="resetInitialCameraView"
            >
              初始视角
            </button>
            <button
              type="button"
              class="camera-debug-toggle camera-debug-toggle--tone"
              :class="{ 'is-active': mapToneDebugOpen }"
              @click="toggleMapToneDebug"
            >
              明暗调试
            </button>
          </template>
          <button
            v-if="mapVisualTuneEligible"
            type="button"
            class="camera-debug-toggle camera-debug-toggle--mapvis"
            :class="{ 'is-active': mapVisualTuneOpen }"
            @click="toggleMapVisualTune"
          >
            地图调色
          </button>
        </div>
        <div v-if="tianshuShowDevTools" v-show="cameraDebugOpen" class="camera-debug-panel">
          <div class="camera-debug-hint">
            开启后已暂停开场动画并跳到结束帧。在<strong>中间地图区域</strong>（画布）上拖拽旋转、滚轮缩放，满意后点「复制参数」。
          </div>
          <pre class="camera-debug-dump">{{ cameraDump }}</pre>
          <div class="camera-debug-actions">
            <button type="button" class="camera-debug-btn" @click="copyCameraDump">复制参数</button>
            <button type="button" class="camera-debug-btn is-ghost" @click="toggleCameraDebug">关闭</button>
          </div>
        </div>
        <div
          v-if="tianshuShowDevTools"
          v-show="mapToneDebugOpen"
          class="camera-debug-panel map-tone-debug-panel"
        >
          <div class="camera-debug-hint">
            用 CSS <code>filter</code> 调节<strong>整幅地图画布</strong>的亮度与对比度，仅作现场观感调试；满意后可把下方一行贴到
            <code>map.vue</code> 的默认 props 或样式里。
          </div>
          <div class="map-tone-row">
            <label class="map-tone-label" for="map-tone-brightness">亮度 {{ mapToneBrightness }}%</label>
            <input
              id="map-tone-brightness"
              v-model.number="mapToneBrightness"
              class="map-tone-range"
              type="range"
              min="40"
              max="220"
              step="1"
            />
          </div>
          <div class="map-tone-row">
            <label class="map-tone-label" for="map-tone-contrast">对比度 {{ mapToneContrast }}%</label>
            <input
              id="map-tone-contrast"
              v-model.number="mapToneContrast"
              class="map-tone-range"
              type="range"
              min="40"
              max="220"
              step="1"
            />
          </div>
          <pre class="camera-debug-dump map-tone-dump">{{ mapToneFilterSnippet }}</pre>
          <div class="camera-debug-actions">
            <button type="button" class="camera-debug-btn" @click="copyMapToneSnippet">复制 filter</button>
            <button type="button" class="camera-debug-btn is-ghost" @click="resetMapTone">恢复默认</button>
            <button type="button" class="camera-debug-btn is-ghost" @click="toggleMapToneDebug">关闭</button>
          </div>
        </div>
      </div>
      <div
        v-if="mapVisualTuneEligible && mapVisualTuneOpen"
        class="map-visual-tune-host"
      >
        <MapTuningPanel :get-world="getMapWorld" @close="mapVisualTuneOpen = false" />
      </div>
    </div>

    <teleport to="body">
      <div
        v-if="orderDetailOpen"
        class="tianshu-order-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tianshu-order-detail-title"
        @click.self="closeOrderDetail"
      >
        <div class="tianshu-order-panel" @click.stop>
          <header class="tianshu-order-panel__head">
            <h2 id="tianshu-order-detail-title" class="tianshu-order-panel__title">
              {{ orderDetailTitle }}
            </h2>
            <button type="button" class="tianshu-order-panel__close" @click="closeOrderDetail">×</button>
          </header>
          <p class="tianshu-order-panel__addr">{{ orderDetailSubtitle }}</p>
          <p v-if="orderDetailLoading" class="tianshu-order-panel__hint">加载中…</p>
          <p v-else-if="orderDetailError" class="tianshu-order-panel__err">{{ orderDetailError }}</p>
          <div v-else class="tianshu-order-table-wrap">
            <table class="tianshu-order-table">
              <thead>
                <tr>
                  <th class="tianshu-order-table__col-expand" scope="col"></th>
                  <th>订单号</th>
                  <th>下单时间</th>
                  <th class="tianshu-order-table__num">金额</th>
                  <th>客户</th>
                  <th v-if="orderDetailScope === 'today_all'">收货地址</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="row in orderDetailRows" :key="row.id">
                  <tr class="tianshu-order-table__main-row">
                    <td class="tianshu-order-table__expand">
                      <button
                        type="button"
                        class="tianshu-order-table__expand-btn"
                        :aria-expanded="isOrderLineExpanded(row.id)"
                        :aria-controls="`tianshu-order-lines-${row.id}`"
                        :aria-label="
                          isOrderLineExpanded(row.id) ? '收起本单商品明细' : '展开本单商品明细'
                        "
                        @click.stop="toggleOrderLineItems(row)"
                      >
                        <span class="tianshu-order-table__expand-icon" aria-hidden="true">{{
                          isOrderLineExpanded(row.id) ? "▼" : "▶"
                        }}</span>
                      </button>
                    </td>
                    <td>{{ row.order_sn || "—" }}</td>
                    <td>{{ formatOrderTime(row.add_time) }}</td>
                    <td class="tianshu-order-table__num">¥{{ formatMoney(row.total_amount) }}</td>
                    <td>{{ row.customer_name || "—" }}</td>
                    <td v-if="orderDetailScope === 'today_all'">{{ row.member_address || "—" }}</td>
                  </tr>
                  <tr
                    v-if="isOrderLineExpanded(row.id)"
                    :id="`tianshu-order-lines-${row.id}`"
                    class="tianshu-order-table__detail-row"
                  >
                    <td :colspan="orderDetailColSpan" class="tianshu-order-table__detail-cell">
                      <div class="tianshu-order-lines">
                        <p v-if="orderLineState(row.id).loading" class="tianshu-order-lines__hint">加载商品明细…</p>
                        <p v-else-if="orderLineState(row.id).error" class="tianshu-order-lines__err">
                          {{ orderLineState(row.id).error }}
                        </p>
                        <template v-else>
                          <p v-if="orderLineState(row.id).warning" class="tianshu-order-lines__warn">
                            {{ orderLineState(row.id).warning }}
                          </p>
                          <table
                            v-if="orderLineState(row.id).rows.length"
                            class="tianshu-order-lines__table"
                          >
                            <thead>
                              <tr>
                                <th scope="col">商品</th>
                                <th scope="col">规格</th>
                                <th scope="col">单位</th>
                                <th scope="col" class="tianshu-order-lines__num">数量</th>
                                <th scope="col" class="tianshu-order-lines__num">小计</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr v-for="(it, idx) in orderLineState(row.id).rows" :key="idx">
                                <td>{{ it.goods_name || "—" }}</td>
                                <td>{{ it.spec || "—" }}</td>
                                <td>{{ it.unit || "—" }}</td>
                                <td class="tianshu-order-lines__num">{{ formatLineQty(it.qty) }}</td>
                                <td class="tianshu-order-lines__num">¥{{ formatMoney(it.line_amount) }}</td>
                              </tr>
                            </tbody>
                          </table>
                          <p
                            v-else-if="!orderLineState(row.id).warning"
                            class="tianshu-order-lines__hint"
                          >
                            暂无商品行
                          </p>
                        </template>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
            <p v-if="!orderDetailRows.length" class="tianshu-order-panel__empty">{{ orderDetailEmptyText }}</p>
          </div>
        </div>
      </div>
    </teleport>

    <!-- loading：用 v-if 卸载，避免 z-index 全屏层长期压在 UI 上（仅靠 opacity:0 仍可能「看起来空」） -->
    <div class="loading" v-if="state.showLoading">
      <p class="loading-ai-caption">MULTI-MODAL FUSION · SPATIAL DIGITAL TWIN</p>
      <div class="loading-text">
        <span style="--index: 1">认</span>
        <span style="--index: 2">知</span>
        <span style="--index: 3">孪</span>
        <span style="--index: 4">生</span>
        <span style="--index: 5">唤</span>
        <span style="--index: 6">醒</span>
        <span style="--index: 7">中</span>
      </div>
      <div class="loading-progress">
        <span class="value">{{ state.progress }}</span>
        <span class="unit">%</span>
      </div>
      <div
        class="loading-bar"
        role="progressbar"
        :aria-valuenow="state.progress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div class="loading-bar__fill" :style="{ width: state.progress + '%' }" />
      </div>
    </div>
  </div>
</template>
<script setup>
import {
  shallowRef,
  ref,
  reactive,
  computed,
  provide,
  onMounted,
  onBeforeUnmount,
  nextTick,
  watch,
} from "vue"
import mapScene from "./map.vue"
import mHeader from "@/components/mHeader/index.vue"
import mCountCard from "@/components/mCountCard/index.vue"
import mMenu from "@/components/mMenu/index.vue"
import mRadar from "@/components/mRadar/index.vue"
import mMenuItem from "@/components/mMenuItem/index.vue"
import mSvglineAnimation from "@/components/mSvglineAnimation/index.vue"
import BulkCommoditySalesChart from "./components/BulkCommoditySalesChart.vue"
import YearlyEconomyTrend from "./components/YearlyEconomyTrend.vue"
import EconomicTrendChart from "./components/EconomicTrendChart.vue"
import DistrictEconomicIncome from "./components/DistrictEconomicIncome.vue"
import PurposeSpecialFunds from "./components/PurposeSpecialFunds.vue"
import ProportionPopulationConsumption from "./components/ProportionPopulationConsumption.vue"
import ElectricityUsage from "./components/ElectricityUsage.vue"
import QuarterlyGrowthSituation from "./components/QuarterlyGrowthSituation.vue"
import MapTuningPanel from "./components/MapTuningPanel.vue"

import { Assets } from "./assets.js"
import emitter from "@/utils/emitter"
import gsap from "gsap"
import autofit from "autofit.js"
import {
  fetchJson,
  todayYesterdayIso,
  TIANSHU_SELECTED_DISTRICT_KEY,
  prefetchTianshuInsightCaches,
  TIANSHU_CHART_QUERY_DISTRICT_KEY,
} from "@/api/tianshuInsights.js"
import { useTianshuOpsConsole } from "@/hooks/useTianshuOpsConsole.js"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "./composables/tianshuStaggeredPoll.js"

const KPI_TODAY = "/api/insights/business/kpi-summary?scope=today"
const COCKPIT_MAP_POINTS = "/api/insights/business/cockpit-customer-map-points"

const tianshuShowDevTools = import.meta.env.DEV

/** 生产环境可在主站 URL 加 `?mapTune=1`（iframe 内为 /tianshu/index.html?mapTune=1）打开地图调色板 */
const mapVisualTuneEligible =
  import.meta.env.DEV ||
  (typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("mapTune") === "1")

const mapVisualTuneOpen = ref(
  typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("mapTune") === "1",
)

function toggleMapVisualTune() {
  mapVisualTuneOpen.value = !mapVisualTuneOpen.value
}

/** 资源加载器（勿与 autofit 返回值共用同一 ref，否则会覆盖适配导致布局失效） */
const resourceAssets = shallowRef(null)
/** autofit 实例，需保持引用以便 resize 生效 */
const autofitInstance = shallowRef(null)
const mapSceneRef = ref(null)
/** 首屏入场：loading 结束后与地图错开淡入 */
const shellEnterReady = ref(false)
/** KPI 数值刷新时的短时高亮 */
const kpiPulseActive = ref(false)
let kpiPulseTimer = null
const cameraDebugOpen = ref(false)
const mapToneDebugOpen = ref(false)
const mapToneBrightness = ref(94)
const mapToneContrast = ref(100)

const mapToneFilterSnippet = computed(() => {
  const b = (Math.max(40, Math.min(220, Number(mapToneBrightness.value) || 100)) / 100).toFixed(2)
  const c = (Math.max(40, Math.min(220, Number(mapToneContrast.value) || 100)) / 100).toFixed(2)
  return `filter: brightness(${b}) contrast(${c});`
})
const cameraDump = ref("")
let cameraDumpRaf = null
const mapDrillActive = ref(false)
/** 与地图下钻同步（UI）：null = 全市；用于「返回全市」等与地图即时一致 */
const selectedDistrictName = ref(null)
/** 侧栏图表 API 用：在相机动画结束后才与 selectedDistrictName 对齐 */
const chartQueryDistrict = ref(null)
/** 与 map.js _drillDataSeq 对齐，丢弃过期 districtDrillData */
const districtDrillDataSeq = ref(0)
provide(TIANSHU_SELECTED_DISTRICT_KEY, selectedDistrictName)
provide(TIANSHU_CHART_QUERY_DISTRICT_KEY, chartQueryDistrict)
const spectacleRootRef = ref(null)
const spectacleFullscreen = ref(false)
const orderDetailOpen = ref(false)
const orderDetailLoading = ref(false)
const orderDetailError = ref("")
const orderDetailAddress = ref("")
const orderDetailRows = ref([])
/** address：地图光柱；today_all：实时链路打开全市今日列表 */
const orderDetailScope = ref("address")
/** 订单明细弹窗内：展开商品行的订单 id */
const orderDetailExpandedIds = ref({})
/** order_id -> { loading, error, rows, warning, fetched } */
const orderLineItemsByOrderId = reactive({})
/** 地图光柱悬停：固定区位展示，结构与原 CSS3D 卡片一致 */
const orderHover = ref(null)
const orderHoverGmvText = computed(() => {
  if (orderHover.value?.isHeadquarters) return ""
  const g = orderHover.value?.gmv
  if (g == null || !Number.isFinite(Number(g))) return "¥0"
  return `¥${Number(g).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`
})

const orderDetailTitle = computed(() =>
  orderDetailScope.value === "today_all" ? "今日订单列表" : "今日订单明细",
)
const orderDetailSubtitle = computed(() => orderDetailAddress.value || "—")
const orderDetailColSpan = computed(() => (orderDetailScope.value === "today_all" ? 6 : 5))
const orderDetailEmptyText = computed(() =>
  orderDetailScope.value === "today_all" ? "今日暂无订单记录" : "该地址今日暂无订单记录",
)
const clock = reactive({ date: "", time: "" })
let clockTimer = null

const opsConsole = useTianshuOpsConsole()

function getMapWorld() {
  const cm = mapSceneRef.value?.canvasMap
  return cm && typeof cm === "object" && "value" in cm ? cm.value : cm
}

function stopCameraDumpLoop() {
  if (cameraDumpRaf != null) {
    cancelAnimationFrame(cameraDumpRaf)
    cameraDumpRaf = null
  }
}

function startCameraDumpLoop() {
  stopCameraDumpLoop()
  const tick = () => {
    if (!cameraDebugOpen.value) return
    const w = getMapWorld()
    cameraDump.value = w?.getCameraParamsText?.() ?? ""
    cameraDumpRaf = requestAnimationFrame(tick)
  }
  cameraDumpRaf = requestAnimationFrame(tick)
}

function toggleCameraDebug() {
  cameraDebugOpen.value = !cameraDebugOpen.value
  const w = getMapWorld()
  if (cameraDebugOpen.value) {
    w?.setCameraDebugMode?.(true)
    startCameraDumpLoop()
  } else {
    w?.setCameraDebugMode?.(false)
    stopCameraDumpLoop()
  }
}

function toggleMapToneDebug() {
  mapToneDebugOpen.value = !mapToneDebugOpen.value
}

function resetMapTone() {
  mapToneBrightness.value = 94
  mapToneContrast.value = 100
}

async function copyMapToneSnippet() {
  const text = mapToneFilterSnippet.value
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    try {
      const ta = document.createElement("textarea")
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand("copy")
      document.body.removeChild(ta)
    } catch {
      /* ignore */
    }
  }
}

function onDistrictDrill(payload) {
  mapDrillActive.value = Boolean(payload?.active)
  const n = payload?.name != null ? String(payload.name).trim() : ""
  selectedDistrictName.value =
    payload?.active && n ? n : null
  if (payload?.seq != null) {
    districtDrillDataSeq.value = payload.seq
  }
}

function onDistrictDrillData(payload) {
  if (payload?.seq == null || payload.seq !== districtDrillDataSeq.value) {
    return
  }
  const n = payload?.name != null ? String(payload.name).trim() : ""
  chartQueryDistrict.value = payload?.active && n ? n : null
}

function onChartDistrictClick(payload) {
  const n = payload?.name != null ? String(payload.name).trim() : ""
  if (!n) return
  getMapWorld()?.toggleDistrictDrill?.(n)
}

function resetMapDrill() {
  getMapWorld()?.drillResetCityView?.()
}

function resetInitialCameraView() {
  getMapWorld()?.resetToInitialCameraView?.()
}

function onTianshuOrderPillarHover(payload) {
  if (!payload) {
    orderHover.value = null
    return
  }
  if (payload.isHeadquarters) {
    orderHover.value = {
      isHeadquarters: true,
      headquartersTitle: String(payload.headquartersTitle || "监管指挥中心"),
      address: String(payload.address ?? "").trim() || "—",
    }
    return
  }
  orderHover.value = {
    isHeadquarters: false,
    address: String(payload.address ?? "").trim() || "—",
    customer_name: String(payload.customer_name ?? "").trim() || "—",
    order_count: Number(payload.order_count) || 0,
    gmv: Number(payload.gmv) || 0,
  }
}

function formatMoney(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return "0"
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 2 })
}

function formatLineQty(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return "—"
  if (Math.abs(n - Math.round(n)) < 1e-6) return String(Math.round(n))
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 4 })
}

function orderLineKey(id) {
  return String(id ?? "")
}

function isOrderLineExpanded(id) {
  return Boolean(orderDetailExpandedIds.value[orderLineKey(id)])
}

function orderLineState(id) {
  return (
    orderLineItemsByOrderId[orderLineKey(id)] ?? {
      loading: false,
      error: "",
      rows: [],
      warning: "",
      fetched: false,
    }
  )
}

async function toggleOrderLineItems(row) {
  const k = orderLineKey(row.id)
  const next = { ...orderDetailExpandedIds.value, [k]: !orderDetailExpandedIds.value[k] }
  orderDetailExpandedIds.value = next
  if (!next[k]) return
  if (orderLineItemsByOrderId[k]?.fetched) return
  orderLineItemsByOrderId[k] = {
    loading: true,
    error: "",
    rows: [],
    warning: "",
    fetched: false,
  }
  try {
    const d = await fetchJson(
      `/api/insights/business/order-line-items?order_id=${encodeURIComponent(row.id)}`,
    )
    orderLineItemsByOrderId[k] = {
      loading: false,
      error: "",
      rows: Array.isArray(d?.rows) ? d.rows : [],
      warning: typeof d?.warning === "string" ? d.warning : "",
      fetched: true,
    }
  } catch (e) {
    orderLineItemsByOrderId[k] = {
      loading: false,
      error: e?.message || String(e),
      rows: [],
      warning: "",
      fetched: true,
    }
  }
}

function formatOrderTime(ts) {
  const n = Number(ts)
  if (!Number.isFinite(n)) return "—"
  const d = new Date(n * 1000)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

function closeOrderDetail() {
  orderDetailOpen.value = false
  orderDetailError.value = ""
  orderDetailRows.value = []
  orderDetailExpandedIds.value = {}
  orderDetailScope.value = "address"
  for (const key of Object.keys(orderLineItemsByOrderId)) {
    delete orderLineItemsByOrderId[key]
  }
}

function getFullscreenElement() {
  const d = document
  return (
    d.fullscreenElement ||
    d.webkitFullscreenElement ||
    d.mozFullScreenElement ||
    d.msFullscreenElement ||
    null
  )
}

function onSpectacleFullscreenChange() {
  const el = spectacleRootRef.value
  const fs = getFullscreenElement()
  const embedded = typeof window !== "undefined" && window.parent !== window
  if (!embedded) {
    spectacleFullscreen.value = Boolean(el && (fs === el || fs === document.documentElement))
  }
  scheduleTianshuViewportLayoutRefresh()
}

/** 主站嵌入：父页对 iframe 全屏后同步按钮文案 */
function onTianshuShellFullscreenMessage(ev) {
  if (ev.data?.type !== "tianshu-fullscreen-state") return
  spectacleFullscreen.value = Boolean(ev.data.value)
  scheduleTianshuViewportLayoutRefresh()
}

async function requestFullscreenEl(node) {
  if (!node) return false
  const fn =
    node.requestFullscreen ||
    node.webkitRequestFullscreen ||
    node.mozRequestFullScreen ||
    node.msRequestFullscreen
  if (!fn) return false
  await fn.call(node)
  return true
}

async function exitFullscreenDoc() {
  const d = document
  const fn =
    d.exitFullscreen ||
    d.webkitExitFullscreen ||
    d.mozCancelFullScreen ||
    d.msExitFullscreen
  if (fn) await fn.call(d)
}

async function toggleSpectacleFullscreen() {
  if (typeof window !== "undefined" && window.parent !== window) {
    try {
      window.parent.postMessage({ type: "tianshu-toggle-fullscreen" }, "*")
    } catch (e) {
      console.warn("[tianshu] 请求父页全屏失败", e)
    }
    return
  }
  const el = spectacleRootRef.value
  if (!el) return
  const fs = getFullscreenElement()
  try {
    if (!fs) {
      let ok = await requestFullscreenEl(el).catch(() => false)
      if (!ok) {
        await requestFullscreenEl(document.documentElement).catch(() => {})
      }
    } else {
      await exitFullscreenDoc().catch(() => {})
    }
  } catch (e) {
    console.warn("[tianshu] 全屏切换失败", e)
  }
}

function openTodayOrdersListFromOps() {
  orderDetailScope.value = "today_all"
  orderDetailAddress.value = "全市 · 今日"
  orderDetailOpen.value = true
  orderDetailLoading.value = true
  orderDetailError.value = ""
  orderDetailRows.value = []
  orderDetailExpandedIds.value = {}
  for (const key of Object.keys(orderLineItemsByOrderId)) {
    delete orderLineItemsByOrderId[key]
  }
  void fetchJson("/api/insights/business/today-orders-list?limit=500")
    .then((d) => {
      orderDetailRows.value = Array.isArray(d?.rows) ? d.rows : []
    })
    .catch((e) => {
      orderDetailError.value = e?.message || String(e)
    })
    .finally(() => {
      orderDetailLoading.value = false
    })
}

/** 与上次请求对比：落点一致则跳过 setOrderPillars，避免整片光柱清空+GSAP 重播造成「闪一下」 */
let lastOrderPillarsFingerprint = undefined

function fingerprintOrderMapPoints(pts) {
  if (!Array.isArray(pts) || pts.length === 0) return ""
  const keys = pts.map((p) => {
    const lng = Number(p.lng)
    const lat = Number(p.lat)
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
    const mid = Number(p.member_id) || 0
    const oc = Number(p.order_count) || 0
    const g = Math.round(Number(p.gmv) || 0)
    return `${mid}:${lng.toFixed(5)}:${lat.toFixed(5)}:${oc}:${g}`
  })
  return keys.filter(Boolean).sort().join("|")
}

async function loadTodayOrderPillars() {
  const w = getMapWorld()
  if (!w || typeof w.setOrderPillars !== "function") {
    return
  }
  try {
    const { todayIso } = todayYesterdayIso()
    const url = `${COCKPIT_MAP_POINTS}?start_date=${encodeURIComponent(todayIso)}&end_date=${encodeURIComponent(todayIso)}&limit=500`
    const d = await fetchJson(url)
    const pts = Array.isArray(d?.points) ? d.points : []
    const fp = fingerprintOrderMapPoints(pts)
    if (fp === lastOrderPillarsFingerprint) return
    lastOrderPillarsFingerprint = fp
    w.setOrderPillars(pts)
  } catch (e) {
    console.warn("[gdMap] 今日订单光柱:", e?.message || e)
    lastOrderPillarsFingerprint = undefined
    w.setOrderPillars([])
  }
}

async function onTianshuOrderPillarClick(payload) {
  if (payload?.isHeadquarters) return
  const addr = (payload?.address || "").trim()
  const mid = Number(payload?.member_id)
  const hasMember = Number.isFinite(mid) && mid > 0
  if (!addr && !hasMember) return
  orderDetailScope.value = "address"
  orderDetailAddress.value = addr || `会员 #${mid}`
  orderDetailOpen.value = true
  orderDetailLoading.value = true
  orderDetailError.value = ""
  orderDetailRows.value = []
  try {
    const { todayIso } = todayYesterdayIso()
    const q = new URLSearchParams({
      start_date: todayIso,
      end_date: todayIso,
    })
    if (addr) q.set("address", addr)
    if (hasMember) q.set("member_id", String(mid))
    const d = await fetchJson(`/api/insights/business/member-orders-in-range?${q}`)
    orderDetailRows.value = Array.isArray(d?.rows) ? d.rows : []
  } catch (e) {
    orderDetailError.value = e?.message || String(e)
  } finally {
    orderDetailLoading.value = false
  }
}

async function copyCameraDump() {
  const w = getMapWorld()
  const text = w?.getCameraParamsText?.() ?? cameraDump.value
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    try {
      const ta = document.createElement("textarea")
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand("copy")
      document.body.removeChild(ta)
    } catch {
      /* ignore */
    }
  }
}

function pad2(n) {
  return String(n).padStart(2, "0")
}

function tickClock() {
  const d = new Date()
  clock.date = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
  clock.time = `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

const state = reactive({
  showLoading: true,
  // 进度
  progress: 0,
  // 当前顶部导航索引
  activeIndex: "1",
  // 卡片统计数据
  totalView: [
    {
      icon: "xiaoshoujine",
      zh: "今日 GMV",
      en: "Today's GMV",
      value: 0,
      unit: "元",
      decimals: 2,
    },
    {
      icon: "zongxiaoliang",
      zh: "今日下单数",
      en: "Today's orders",
      value: 0,
      unit: "单",
      decimals: 0,
    },
  ],
})
let stopKpiPoll = null
let stopPillarPoll = null
/** 多 worker 时 WS Hub 与库表可能短暂不一致，短周期用 kpi-summary 校正 GMV */
let kpiDriftTimer = null
const KPI_DRIFT_CHECK_MS = 20_000
let shellChartsResizeTimer = null
/** 与上次 KPI 请求一致则跳过赋值与脉冲动画 */
let lastTodayKpiFingerprint = undefined

/** 顶部翻牌与实时链路 WebSocket（snapshot / batch）同源，避免与 HTTP 轮询显示不一致 */
watch(
  () => ({
    g: opsConsole.liveGmv.value,
    o: opsConsole.liveOrderCount.value,
    on: opsConsole.wsConnected.value,
  }),
  ({ g, o, on }) => {
    if (!on) return
    let touched = false
    if (g != null && Number.isFinite(Number(g))) {
      const v = Math.round(Number(g) * 100) / 100
      if (state.totalView[0].value !== v) {
        state.totalView[0].value = v
        touched = true
      }
    }
    if (o != null && Number.isFinite(Number(o))) {
      const n = Math.round(Number(o))
      if (state.totalView[1].value !== n) {
        state.totalView[1].value = n
        touched = true
      }
    }
    if (touched) {
      lastTodayKpiFingerprint = `${state.totalView[0].value.toFixed(2)}\0${state.totalView[1].value}`
    }
  },
  { flush: "post" },
)

/** 全屏/视口变化会连发 resize，autofit 多次改写 #large-screen 的 scale 会闪顶栏（滤镜/渐变）；合并刷新 */
let tianshuViewportLayoutTimer = null
const TIANSHU_VIEWPORT_LAYOUT_DEBOUNCE_MS = 200

function scheduleTianshuViewportLayoutRefresh() {
  if (tianshuViewportLayoutTimer) clearTimeout(tianshuViewportLayoutTimer)
  tianshuViewportLayoutTimer = setTimeout(() => {
    tianshuViewportLayoutTimer = null
    window.dispatchEvent(new Event("resize"))
    void nextTick(() => {
      try {
        emitter.$emit("tianshuChartsResize")
      } catch {
        /* ignore */
      }
    })
  }, TIANSHU_VIEWPORT_LAYOUT_DEBOUNCE_MS)
}

onMounted(() => {
  tickClock()
  clockTimer = setInterval(tickClock, 1000)
  void loadTodayKpi()
  void loadTodayOrderPillars()
  stopKpiPoll = startStaggeredPoll(TIANSHU_POLL_PERIOD_MS, TIANSHU_POLL_STAGGER.dashboardKpi, () =>
    void loadTodayKpi(),
  )
  stopPillarPoll = startStaggeredPoll(
    TIANSHU_POLL_PERIOD_MS,
    TIANSHU_POLL_STAGGER.dashboardPillars,
    () => void loadTodayOrderPillars(),
  )
  kpiDriftTimer = window.setInterval(() => void reconcileLiveKpiDriftWithHttp(), KPI_DRIFT_CHECK_MS)
  // 监听地图播放完成，执行事件
  emitter.$on("mapPlayComplete", handleMapPlayComplete)
  emitter.$on("districtDrill", onDistrictDrill)
  emitter.$on("districtDrillData", onDistrictDrillData)
  emitter.$on("tianshuChartDistrictClick", onChartDistrictClick)
  emitter.$on("tianshuOrderPillarClick", onTianshuOrderPillarClick)
  emitter.$on("tianshuOrderPillarHover", onTianshuOrderPillarHover)
  document.addEventListener("fullscreenchange", onSpectacleFullscreenChange)
  document.addEventListener("webkitfullscreenchange", onSpectacleFullscreenChange)
  window.addEventListener("message", onTianshuShellFullscreenMessage)
  autofitInstance.value = autofit.init({
    dh: 1080,
    dw: 1920,
    el: "#large-screen",
    resize: true,
    delay: 100,
  })
  initAssets()
})
onBeforeUnmount(() => {
  if (clockTimer) clearInterval(clockTimer)
  stopKpiPoll?.()
  stopKpiPoll = null
  stopPillarPoll?.()
  stopPillarPoll = null
  if (kpiDriftTimer != null) {
    clearInterval(kpiDriftTimer)
    kpiDriftTimer = null
  }
  if (kpiPulseTimer) clearTimeout(kpiPulseTimer)
  if (shellChartsResizeTimer) clearTimeout(shellChartsResizeTimer)
  if (tianshuViewportLayoutTimer) clearTimeout(tianshuViewportLayoutTimer)
  stopCameraDumpLoop()
  emitter.$off("mapPlayComplete", handleMapPlayComplete)
  emitter.$off("districtDrill", onDistrictDrill)
  emitter.$off("districtDrillData", onDistrictDrillData)
  emitter.$off("tianshuChartDistrictClick", onChartDistrictClick)
  emitter.$off("tianshuOrderPillarClick", onTianshuOrderPillarClick)
  emitter.$off("tianshuOrderPillarHover", onTianshuOrderPillarHover)
  document.removeEventListener("fullscreenchange", onSpectacleFullscreenChange)
  document.removeEventListener("webkitfullscreenchange", onSpectacleFullscreenChange)
  window.removeEventListener("message", onTianshuShellFullscreenMessage)
})

/**
 * HTTP 与 WS 单量一致但 GMV 偏差 >0.5 元时，以 kpi-summary（库表）校正 liveGmv，避免多 worker Hub 不同步。
 */
async function reconcileLiveKpiDriftWithHttp() {
  try {
    const d = await fetchJson(KPI_TODAY)
    const rawGmv = Number(d?.gmv) || 0
    const gmv = Math.round(rawGmv * 100) / 100
    const orders = Math.round(Number(d?.order_count) || 0)
    const ws = opsConsole.wsConnected.value
    const lg = opsConsole.liveGmv.value
    const lo = opsConsole.liveOrderCount.value
    if (
      !ws ||
      lg == null ||
      lo == null ||
      !Number.isFinite(Number(lg)) ||
      orders !== Number(lo) ||
      Math.abs(gmv - Number(lg)) <= 0.5
    ) {
      return
    }
    opsConsole.applyClientKpiReconcile(gmv, orders)
  } catch {
    /* ignore */
  }
}

async function loadTodayKpi() {
  try {
    const d = await fetchJson(KPI_TODAY)
    const rawGmv = Number(d?.gmv) || 0
    const gmv = Math.round(rawGmv * 100) / 100
    const orders = Math.round(Number(d?.order_count) || 0)
    const ws = opsConsole.wsConnected.value
    const lg = opsConsole.liveGmv.value
    const lo = opsConsole.liveOrderCount.value
    if (
      ws &&
      lg != null &&
      lo != null &&
      Number.isFinite(Number(lg)) &&
      orders === Number(lo) &&
      Math.abs(gmv - Number(lg)) > 0.5
    ) {
      opsConsole.applyClientKpiReconcile(gmv, orders)
    }
    /** WS 已推送过该字段时以实时链路为准，避免 60s HTTP 把翻牌打回旧数 */
    const lockGmv = ws && opsConsole.liveGmv.value != null
    const lockOrd = ws && opsConsole.liveOrderCount.value != null

    let changed = false
    if (!lockGmv && state.totalView[0].value !== gmv) {
      state.totalView[0].value = gmv
      changed = true
    }
    if (!lockOrd && state.totalView[1].value !== orders) {
      state.totalView[1].value = orders
      changed = true
    }

    const fp = `${state.totalView[0].value.toFixed(2)}\0${state.totalView[1].value}`
    if (fp === lastTodayKpiFingerprint) return
    lastTodayKpiFingerprint = fp
    if (!changed) return

    kpiPulseActive.value = false
    await nextTick()
    kpiPulseActive.value = true
    if (kpiPulseTimer) clearTimeout(kpiPulseTimer)
    kpiPulseTimer = setTimeout(() => {
      kpiPulseActive.value = false
    }, 480)
  } catch {
    /* 保持上次成功值或 0 */
  }
}
function initAssets() {
  prefetchTianshuInsightCaches()
  resourceAssets.value = new Assets()
  let params = {
    progress: 0,
  }
  resourceAssets.value.instance.on("onProgress", (path, itemsLoaded, itemsTotal) => {
    let p = Math.floor((itemsLoaded / itemsTotal) * 100)
    gsap.to(params, {
      progress: p,
      onUpdate: () => {
        state.progress = Math.floor(params.progress)
      },
    })
  })
  resourceAssets.value
    .startLoad()
    .then(async () => {
      try {
        emitter.$emit("loadMap", resourceAssets.value)
        await hideLoading()
        mapSceneRef.value?.play()
      } catch (e) {
        console.error("[gdMap] 地图初始化失败:", e)
        await hideLoading()
      }
    })
    .catch((err) => {
      console.error("[gdMap] 资源加载失败:", err)
      hideLoading()
    })
}

// 隐藏loading
async function hideLoading() {
  return new Promise((resolve, reject) => {
    let tl = gsap.timeline()
    tl.to(".loading-text span", {
      y: "200%",
      opacity: 0,
      ease: "power4.inOut",
      duration: 2,
      stagger: 0.2,
    })
    tl.to(".loading-progress", { opacity: 0, ease: "power4.inOut", duration: 2 }, "<")
    tl.to(
      ".loading",
      {
        opacity: 0,
        ease: "power4.inOut",
        onComplete: () => {
          state.showLoading = false
          void nextTick(() => {
            requestAnimationFrame(() => {
              shellEnterReady.value = true
              if (shellChartsResizeTimer) clearTimeout(shellChartsResizeTimer)
              shellChartsResizeTimer = setTimeout(() => {
                shellChartsResizeTimer = null
                emitter.$emit("tianshuChartsResize")
              }, 720)
            })
          })
          resolve()
        },
      },
      "-=1"
    )
  })
}

function handleMenuSelect(index) {
  state.activeIndex = index
}
// 地图时间线播完时触发（大屏 UI 已默认可见，此处保留占位便于以后加动效）
function handleMapPlayComplete() {
  void loadTodayOrderPillars()
}
</script>

<style lang="scss">
@import "~@/assets/style/home.scss";
/* 右上：大屏按钮叠在时钟上方，并整体上移，避免与顶栏「风险预警」等菜单横向挤占 */
/* 本文件 style 未使用 scoped，勿写 :deep（会原样进 CSS 导致规则整段失效）。 */
/* .large-screen-wrap 为 pointer-events:none，事件会穿透到下层 WebGL canvas；须让整块顶栏参与命中（仅约 90px 高，不挡地图主体） */
.large-screen .m-header {
  z-index: 24;
  pointer-events: auto;
}
/* 顶栏装饰线 SVG 后渲染、宽幅盖住右上角，默认会抢走「大屏模式」点击 */
.large-screen .m-header .m-header-line,
.large-screen .m-header .m-header-line .svg-line-animation,
.large-screen .m-header .m-header-line svg {
  pointer-events: none;
}
.large-screen .m-header .m-header-right {
  top: 26px;
  z-index: 50;
}
/* 整页 scale 突变时减轻顶栏背景/滤镜与 GPU 合成的闪烁 */
.large-screen .m-header-wrap {
  -webkit-backface-visibility: hidden;
  backface-visibility: hidden;
}
.m-header-weather,
.m-header-date {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.m-header-date__clock {
  display: flex;
  align-items: center;
  span {
    padding-right: 10px;
    color: #c4f3fe;
    font-size: 14px;
  }
}
.m-header-weather span {
  padding-right: 10px;
  color: #c4f3fe;
  font-size: 14px;
}
.tianshu-spectacle-fs-btn {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: rgba(224, 250, 255, 0.95);
  background: linear-gradient(
    135deg,
    rgba(56, 189, 248, 0.22) 0%,
    rgba(12, 48, 72, 0.55) 100%
  );
  border: 1px solid rgba(103, 232, 249, 0.45);
  box-shadow: 0 0 14px rgba(56, 189, 248, 0.15);
  cursor: pointer;
  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}
.tianshu-spectacle-fs-btn:hover {
  border-color: rgba(186, 245, 255, 0.65);
  box-shadow: 0 0 20px rgba(103, 232, 249, 0.22);
}
.tianshu-spectacle-fs-btn:focus-visible {
  outline: 2px solid rgba(103, 232, 249, 0.65);
  outline-offset: 2px;
}

.tianshu-brand {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  pointer-events: none;
  gap: 6px;
}
.tianshu-brand-eyebrow {
  position: relative;
  z-index: 1;
  margin: 0;
  padding: 0;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.48em;
  line-height: 1.2;
  color: rgba(148, 220, 248, 0.62);
  text-transform: none;
  text-shadow: 0 0 18px rgba(56, 189, 248, 0.2);
  animation: tianshuBrandEyebrowGlow 6s ease-in-out infinite;
}
.tianshu-brand-row {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 20px;
}
.tianshu-brand-divider {
  flex-shrink: 0;
  width: 1px;
  height: 28px;
  border-radius: 1px;
  background: linear-gradient(
    180deg,
    rgba(48, 220, 255, 0) 0%,
    rgba(120, 240, 255, 0.72) 42%,
    rgba(56, 189, 248, 0.5) 58%,
    rgba(48, 220, 255, 0) 100%
  );
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.22);
}
.tianshu-brand-slogan {
  font-size: 29px;
  font-weight: 700;
  letter-spacing: 0.15em;
  line-height: 1.1;
  white-space: nowrap;
  background: linear-gradient(
    100deg,
    rgba(200, 245, 255, 0.92) 0%,
    rgba(255, 255, 255, 1) 22%,
    rgba(103, 232, 249, 0.98) 48%,
    rgba(186, 230, 255, 0.95) 72%,
    rgba(220, 250, 255, 0.92) 100%
  );
  background-size: 220% auto;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(0 2px 14px rgba(8, 24, 42, 0.9)) drop-shadow(0 0 28px rgba(56, 189, 248, 0.2));
  font-family: "YouSheBiaoTiHei", "PingFang SC", "Microsoft YaHei", sans-serif;
  animation: tianshuBrandShimmer 7.5s ease-in-out infinite;
}
@keyframes tianshuBrandShimmer {
  0%,
  100% {
    background-position: 0% center;
    filter: drop-shadow(0 2px 14px rgba(8, 24, 42, 0.9)) drop-shadow(0 0 22px rgba(56, 189, 248, 0.16));
  }
  50% {
    background-position: 100% center;
    filter: drop-shadow(0 2px 14px rgba(8, 24, 42, 0.9)) drop-shadow(0 0 36px rgba(103, 232, 249, 0.28));
  }
}
@keyframes tianshuBrandEyebrowGlow {
  0%,
  100% {
    color: rgba(148, 220, 248, 0.58);
    text-shadow: 0 0 14px rgba(56, 189, 248, 0.16);
  }
  50% {
    color: rgba(186, 245, 255, 0.88);
    text-shadow: 0 0 22px rgba(103, 232, 249, 0.32);
  }
}
@media (prefers-reduced-motion: reduce) {
  .tianshu-brand-slogan,
  .tianshu-brand-eyebrow {
    animation: none !important;
  }
  .tianshu-brand-slogan {
    background-position: 50% center;
  }
}
/* 全屏：与 home.scss 中 spectacle 装饰降级一致，避免顶栏渐变/滤镜动画参与拍频 */
.large-screen.tianshu-spectacle-fs-active {
  .tianshu-brand-slogan,
  .tianshu-brand-eyebrow {
    animation: none !important;
  }
  .tianshu-brand-slogan {
    background-position: 50% center;
  }
}
.tianshu-brand-slogan--left {
  padding-right: 0;
}
.tianshu-brand-slogan--right {
  padding-left: 0;
}
.top-menu {
  position: absolute;
  left: 0px;
  right: 0px;
  top: 40px;
  z-index: 3;
  display: flex;
  justify-content: center;
  .top-menu-mid-space {
    width: 800px;
  }
}
.bottom-radar {
  position: absolute;
  right: 500px;
  bottom: 100px;
  z-index: 3;
}

/* 地图区左上固定槽位：与 left-wrap(398)+边距对齐，位于 KPI 卡片下方、地图「天空」留白处 */
.tianshu-order-hover-dock {
  position: absolute;
  z-index: 11;
  left: 436px;
  top: 178px;
  width: min(440px, 36vw);
  max-height: min(280px, 32vh);
  overflow: auto;
  pointer-events: none;
  box-sizing: border-box;
}
.tianshu-order-hover-dock__inner {
  position: relative;
  padding: 16px 16px 14px;
  border-radius: 10px;
  border: 1px solid rgba(72, 180, 210, 0.5);
  background: linear-gradient(
    165deg,
    rgba(10, 28, 48, 0.94) 0%,
    rgba(6, 16, 32, 0.92) 100%
  );
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 8px 28px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}
.tianshu-order-hover-dock__accent {
  position: absolute;
  top: 10px;
  right: 12px;
  display: flex;
  gap: 5px;
  span {
    display: block;
    width: 14px;
    height: 3px;
    border-radius: 1px;
    background: linear-gradient(90deg, rgba(80, 255, 190, 0.85), rgba(120, 250, 255, 0.55));
    opacity: 0.9;
  }
}
.tianshu-order-hover-dock__head {
  margin: 0 0 12px;
  padding-right: 56px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: rgba(200, 244, 255, 0.95);
}
.tianshu-order-hover-dock__row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  line-height: 1.5;
  font-size: 14px;
  &:last-child {
    margin-bottom: 0;
  }
  &--metrics {
    align-items: flex-start;
  }
}
.tianshu-order-hover-dock__label {
  flex: 0 0 44px;
  padding-top: 2px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(140, 210, 220, 0.95);
}
.tianshu-order-hover-dock__value {
  flex: 1;
  min-width: 0;
  color: rgba(232, 248, 255, 0.96);
  word-break: break-word;
  overflow-wrap: anywhere;
}
.tianshu-order-hover-dock__metrics {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}
.tianshu-order-hover-dock__metric {
  font-size: 14px;
  color: rgba(232, 248, 255, 0.96);
  &--gmv {
    font-weight: 700;
    color: #7efbf6;
    font-size: 15px;
  }
}
.tianshu-order-hover-dock__inner--hq {
  border-color: rgba(255, 200, 120, 0.65);
  background: linear-gradient(
    165deg,
    rgba(48, 32, 14, 0.94) 0%,
    rgba(22, 14, 8, 0.93) 100%
  );
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 8px 28px rgba(0, 0, 0, 0.4),
    0 0 24px rgba(255, 160, 60, 0.12),
    inset 0 1px 0 rgba(255, 240, 200, 0.08);
}
.tianshu-order-hover-dock__head--hq {
  font-size: 17px;
  letter-spacing: 0.1em;
  color: #ffe8c4;
  text-shadow: 0 0 12px rgba(255, 180, 80, 0.35);
}
.tianshu-order-hover-dock__hq-tag {
  margin: 10px 0 0;
  font-size: 13px;
  color: rgba(255, 210, 150, 0.88);
  letter-spacing: 0.06em;
}

.tianshu-order-overlay {
  position: fixed;
  inset: 0;
  z-index: 100000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(4, 12, 22, 0.72);
  backdrop-filter: blur(6px);
}
.tianshu-order-panel {
  width: min(720px, 92vw);
  max-height: min(78vh, 640px);
  overflow: auto;
  padding: 18px 20px 20px;
  border-radius: 12px;
  border: 1px solid rgba(96, 200, 255, 0.45);
  background: linear-gradient(
    165deg,
    rgba(14, 36, 56, 0.96) 0%,
    rgba(8, 20, 34, 0.94) 100%
  );
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 12px 40px rgba(0, 0, 0, 0.45);
  color: #e8f6ff;
}
.tianshu-order-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.tianshu-order-panel__title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #f0fbff;
}
.tianshu-order-panel__close {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
  color: #b8e8ff;
  background: rgba(32, 72, 96, 0.5);
}
.tianshu-order-panel__close:hover {
  color: #fff;
  background: rgba(48, 120, 160, 0.55);
}
.tianshu-order-panel__addr {
  margin: 0 0 12px;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(196, 243, 254, 0.88);
  word-break: break-word;
  overflow-wrap: anywhere;
}
.tianshu-order-panel__hint,
.tianshu-order-panel__empty {
  margin: 12px 0 0;
  font-size: 13px;
  color: rgba(180, 220, 240, 0.75);
}
.tianshu-order-panel__err {
  margin: 12px 0 0;
  font-size: 13px;
  color: #fca5a5;
}
.tianshu-order-table-wrap {
  margin-top: 4px;
}
.tianshu-order-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}
.tianshu-order-table th,
.tianshu-order-table td {
  padding: 8px 10px;
  text-align: left;
  border-bottom: 1px solid rgba(72, 140, 180, 0.25);
  vertical-align: top;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.tianshu-order-table__col-expand,
.tianshu-order-table__expand {
  width: 36px;
  padding-left: 4px;
  padding-right: 4px;
  text-align: center;
  vertical-align: middle;
}
.tianshu-order-table__expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  margin: 0;
  padding: 0;
  border: 1px solid rgba(96, 200, 255, 0.35);
  border-radius: 6px;
  background: rgba(12, 36, 56, 0.85);
  color: rgba(148, 230, 255, 0.95);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
}
.tianshu-order-table__expand-btn:hover {
  border-color: rgba(126, 240, 255, 0.55);
  color: #ffffff;
}
.tianshu-order-table__main-row td:nth-child(2),
.tianshu-order-table thead th:nth-child(2) {
  width: 18%;
}
.tianshu-order-table__main-row td:nth-child(3),
.tianshu-order-table thead th:nth-child(3) {
  width: 26%;
}
.tianshu-order-table__main-row td:nth-child(4),
.tianshu-order-table thead th:nth-child(4) {
  width: 16%;
}
.tianshu-order-table__main-row td:nth-child(5),
.tianshu-order-table thead th:nth-child(5) {
  width: auto;
}
.tianshu-order-table__detail-row td {
  border-bottom: 1px solid rgba(72, 140, 180, 0.35);
  padding-top: 0;
  background: rgba(6, 18, 32, 0.55);
}
.tianshu-order-table__detail-cell {
  padding: 0 10px 10px 42px;
}
.tianshu-order-lines__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  margin-top: 8px;
}
.tianshu-order-lines__table th,
.tianshu-order-lines__table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid rgba(72, 140, 180, 0.2);
  word-break: break-word;
}
.tianshu-order-lines__table th {
  color: rgba(130, 200, 230, 0.8);
  font-weight: 600;
}
.tianshu-order-lines__num {
  text-align: right;
  white-space: nowrap;
  width: 22%;
}
.tianshu-order-lines__hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: rgba(180, 220, 240, 0.7);
}
.tianshu-order-lines__err {
  margin: 8px 0 0;
  font-size: 12px;
  color: #fca5a5;
}
.tianshu-order-lines__warn {
  margin: 8px 0 0;
  font-size: 11px;
  color: rgba(250, 204, 21, 0.85);
  line-height: 1.4;
}
.tianshu-order-table th {
  color: rgba(148, 210, 240, 0.85);
  font-weight: 600;
}
.tianshu-order-table__num {
  text-align: right;
  white-space: nowrap;
}

.map-drill-back-btn {
  pointer-events: auto;
  padding: 12px 22px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #f0fbff;
  cursor: pointer;
  border-radius: 10px;
  border: 1px solid rgba(103, 232, 249, 0.55);
  background: linear-gradient(
    165deg,
    rgba(22, 78, 108, 0.94) 0%,
    rgba(8, 28, 48, 0.92) 55%,
    rgba(6, 18, 34, 0.9) 100%
  );
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 0 28px rgba(56, 189, 248, 0.28),
    0 10px 28px rgba(0, 0, 0, 0.45);
  text-shadow: 0 0 12px rgba(103, 232, 249, 0.35);
  transition:
    border-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
  &:hover {
    border-color: rgba(165, 243, 252, 0.75);
    color: #ffffff;
    box-shadow:
      0 0 0 1px rgba(0, 0, 0, 0.35),
      0 0 36px rgba(56, 189, 248, 0.4),
      0 12px 32px rgba(0, 0, 0, 0.5);
  }
}

/* 与「大屏模式」同列，置于时钟下方，避免与全屏按钮重叠 */
.map-drill-back-btn--under-clock {
  align-self: flex-end;
  margin-top: 2px;
  padding: 8px 16px;
  font-size: 13px;
  letter-spacing: 0.06em;
}

.camera-debug-ui-host {
  position: fixed;
  left: 50%;
  bottom: 108px;
  transform: translateX(-50%);
  z-index: 99999;
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.map-visual-tune-host {
  position: fixed;
  right: 12px;
  bottom: 200px;
  z-index: 100000;
  pointer-events: auto;
  max-width: min(440px, calc(100vw - 24px));
}

.camera-debug-toolbar {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
}

.camera-debug-toggle {
  position: relative;
  z-index: 1;
  pointer-events: auto;
  padding: 10px 16px;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #06202c;
  cursor: pointer;
  border-radius: 8px;
  border: 2px solid rgba(255, 220, 80, 0.95);
  background: linear-gradient(180deg, #ffe566 0%, #ffc53d 100%);
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.35),
    0 6px 20px rgba(0, 0, 0, 0.4);
  &:hover {
    filter: brightness(1.05);
    border-color: #fff8c2;
    color: #041018;
  }
  &.is-active {
    background: linear-gradient(180deg, #7ee0ff 0%, #3eb8e8 100%);
    border-color: rgba(255, 255, 255, 0.85);
    color: #06202c;
  }
  &--reset {
    border-color: rgba(120, 230, 255, 0.75);
    background: linear-gradient(180deg, #5ad4f0 0%, #2a9ec4 100%);
    color: #041820;
    &:hover {
      border-color: rgba(200, 248, 255, 0.95);
      color: #021018;
    }
  }
  &--tone {
    border-color: rgba(180, 200, 255, 0.85);
    background: linear-gradient(180deg, #a8b8f0 0%, #6b8ad8 100%);
    color: #0a1020;
    &:hover {
      border-color: rgba(230, 236, 255, 0.95);
      color: #050810;
    }
  }
}

.map-tone-debug-panel {
  width: min(440px, 42vw);
}

.map-tone-row {
  margin-bottom: 12px;
}

.map-tone-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: rgba(190, 230, 255, 0.92);
}

.map-tone-range {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  accent-color: #5ad4f0;
  cursor: pointer;
}

.map-tone-dump {
  max-height: 72px;
  margin-top: 4px;
}

.camera-debug-panel {
  position: relative;
  z-index: 1;
  width: min(400px, 36vw);
  pointer-events: auto;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(96, 200, 255, 0.4);
  background: rgba(5, 15, 35, 0.92);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  font-size: 12px;
  color: #b8e8ff;
}

.camera-debug-hint {
  margin-bottom: 10px;
  line-height: 1.5;
  color: rgba(196, 236, 255, 0.88);
  code {
    font-size: 11px;
    color: #7df9ff;
  }
}

.camera-debug-dump {
  margin: 0 0 10px;
  padding: 10px;
  max-height: 200px;
  overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  color: #d5f4ff;
  background: rgba(0, 0, 0, 0.35);
  border-radius: 6px;
  border: 1px solid rgba(80, 160, 200, 0.25);
  white-space: pre-wrap;
  word-break: break-all;
}

.camera-debug-actions {
  display: flex;
  gap: 10px;
}

.camera-debug-btn {
  flex: 1;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border-radius: 6px;
  border: 1px solid rgba(96, 200, 255, 0.5);
  color: #06202c;
  background: linear-gradient(180deg, #9ef0ff 0%, #5cc8e8 100%);
  &:hover {
    filter: brightness(1.06);
  }
  &.is-ghost {
    flex: 0 0 auto;
    color: #c4f3fe;
    background: transparent;
    border-color: rgba(120, 200, 255, 0.35);
  }
}
.main-btn-group {
  display: flex;
  left: 50%;
  transform: translateX(-50%);
  bottom: 10px;
  z-index: 999;
  &.disabled {
    pointer-events: none;
  }
  .btn {
    margin-right: 10px;
  }
}
.bottom-svg-line-left,
.bottom-svg-line-right {
  position: absolute;
  right: 50%;
  width: 721px;
  height: 57px;
  margin-right: -5px;
  bottom: -21px;
}
.bottom-svg-line-right {
  transform: scaleX(-1);
  left: 50%;
  right: inherit;
  margin-right: inherit;
  margin-left: -5px;
}
/* 默认即显示大屏（不再依赖 GSAP 从 opacity:0 入场，避免部分环境下一直不可见） */
</style>
