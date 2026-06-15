<template>
  <div
    ref="spectacleRootRef"
    class="large-screen"
    :class="{ 'tianshu-spectacle-fs-active': spectacleFullscreen }"
  >
    <div class="tianshu-spectacle-bg-drift" aria-hidden="true" />
    <!-- 模拟数据按钮（仅 DEV / VITE_DEMO_MODE 渲染；关闭页面/隐藏自动清理） -->
    <MockToggleButton :running="mockStream.running.value" @toggle="toggleMockStream" />
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
          :class="{ 'tianshu-order-hover-dock__inner--hq': orderHover?.role === 'delivery' }"
        >
          <div class="tianshu-order-hover-dock__accent" aria-hidden="true">
            <span></span><span></span><span></span>
          </div>
          <template v-if="orderHover?.role === 'risk'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--risk">
              {{ riskLevelText(orderHover?.risk_level) }}风险 · {{ riskTypeText(orderHover?.risk_type) }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">对象</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.customer_name || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">说明</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.description || "—" }}</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag tianshu-order-hover-dock__hq-tag--risk">
              {{ orderHover?.order_sn || orderHover?.address || "风险点位" }}
            </p>
          </template>
          <template v-else-if="orderHover?.role === 'fulfillment'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--fulfillment">
              {{ fulfillmentStageText(orderHover?.stage) }} · {{ orderHover?.route_no || "履约点位" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">客户</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.customer_name || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">状态</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.description || orderHover?.status || "—" }}</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag tianshu-order-hover-dock__hq-tag--fulfillment">
              {{ orderHover?.order_sn || orderHover?.address || "履约闭环" }}
            </p>
          </template>
          <template v-else-if="orderHover?.role === 'cold_chain'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--cold">
              {{ coldTypeText(orderHover?.cold_type) }} · {{ orderHover?.customer_name || "冷链点位" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">状态</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.description || orderHover?.status || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">温湿</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.temperature || "—" }}℃ · RH {{ orderHover?.humidity || "—" }}%</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag tianshu-order-hover-dock__hq-tag--cold">
              {{ orderHover?.address || "冷链运力" }}
            </p>
          </template>
          <template v-else-if="orderHover?.role === 'industry'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--industry">
              {{ orderHover?.product_name || orderHover?.customer_name || "产业品种" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">波动</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.change_pct ?? 0 }}% · 预测 {{ orderHover?.forecast_price || "—" }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">置信</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.confidence || "—" }}%</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag tianshu-order-hover-dock__hq-tag--industry">
              {{ orderHover?.description || orderHover?.category_name || "产业洞察" }}
            </p>
          </template>
          <template v-else-if="orderHover?.role === 'city_profile'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--city">
              {{ orderHover?.district_name || orderHover?.customer_name || "城市画像" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">覆盖</span>
              <span class="tianshu-order-hover-dock__value">客户 {{ orderHover?.client_count || 0 }} · 食堂 {{ orderHover?.canteen_count || 0 }}</span>
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">风险</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.risk_count || 0 }} 项 · {{ orderHover?.order_count || 0 }} 单</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag tianshu-order-hover-dock__hq-tag--city">
              {{ orderHover?.description || orderHover?.address || "区县经营画像" }}
            </p>
          </template>
          <template v-else-if="orderHover?.role === 'delivery'">
            <div class="tianshu-order-hover-dock__head tianshu-order-hover-dock__head--hq">
              {{ orderHover?.customer_name || "配送商" }}
            </div>
            <div class="tianshu-order-hover-dock__row">
              <span class="tianshu-order-hover-dock__label">位置</span>
              <span class="tianshu-order-hover-dock__value">{{ orderHover?.address || "—" }}</span>
            </div>
            <p class="tianshu-order-hover-dock__hq-tag">配送商 · 物流枢纽</p>
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
          <template v-if="activeView === 'risk-warning'">
            <div class="tianshu-risk-card tianshu-risk-card--command" @click="openRiskHubDetail">
              <div class="tianshu-risk-card__head">
                <span>风险指挥态势</span>
                <b>{{ riskMode }}</b>
              </div>
              <p class="tianshu-risk-mode-hint">{{ riskModeHint }}</p>
              <div class="tianshu-risk-mode-strip">
                <div
                  v-for="item in riskModeStats"
                  :key="item.label"
                  :class="item.tone ? `is-${item.tone}` : ''"
                >
                  <span>{{ item.label }}</span>
                  <b>{{ item.value }}</b>
                </div>
              </div>
              <div class="tianshu-risk-gauge">
                <div class="tianshu-risk-gauge__core">
                  <span>{{ riskKpis.pending_count }}</span>
                  <small>待处置</small>
                </div>
                <i style="--r: 18deg"></i>
                <i style="--r: 116deg"></i>
                <i style="--r: 242deg"></i>
              </div>
              <div class="tianshu-risk-ranks">
                <div><span>高风险</span><b>{{ riskKpis.high_count }}</b></div>
                <div><span>中风险</span><b>{{ riskKpis.medium_count }}</b></div>
                <div><span>低风险</span><b>{{ riskKpis.low_count }}</b></div>
              </div>
            </div>
            <div class="tianshu-risk-card">
              <div class="tianshu-risk-card__head"><span>风险构成</span><b>TYPE-MIX</b></div>
              <div class="tianshu-risk-bars">
                <div v-for="item in riskDistribution" :key="item.key" class="tianshu-risk-bar">
                  <div class="tianshu-risk-bar__meta">
                    <span>{{ item.label }}</span><b>{{ item.count }}</b>
                  </div>
                  <div class="tianshu-risk-bar__track">
                    <i :style="{ width: `${riskBarWidth(item.count)}%` }"></i>
                  </div>
                </div>
              </div>
            </div>
            <div class="tianshu-risk-card tianshu-risk-card--recommend">
              <div class="tianshu-risk-card__head"><span>处置建议</span><b>AI-RULE</b></div>
              <div class="tianshu-risk-actions">
                <button
                  v-for="item in riskRecommendations"
                  :key="item.title"
                  type="button"
                  @click.stop="openRiskRecommendationDetail(item)"
                >
                  <span>{{ item.title }}</span>
                  <p>{{ item.content }}</p>
                </button>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'fulfillment'">
            <div class="tianshu-fulfillment-card tianshu-fulfillment-card--command" @click="openFulfillmentHubDetail">
              <div class="tianshu-fulfillment-card__head">
                <span>履约闭环中枢</span>
                <b>{{ fulfillmentMode }}</b>
              </div>
              <p class="tianshu-fulfillment-mode-hint">{{ fulfillmentModeHint }}</p>
              <div class="tianshu-fulfillment-core">
                <div class="tianshu-fulfillment-core__ring">
                  <span>{{ fulfillmentSummary.health_score || 0 }}</span>
                  <small>履约健康分</small>
                </div>
                <div class="tianshu-fulfillment-core__metrics">
                  <div><span>今日配送</span><b>{{ fulfillmentSummary.today_orders || 0 }}</b></div>
                  <div><span>分检完成率</span><b>{{ formatPct(fulfillmentSummary.sort_rate) }}</b></div>
                  <div><span>装车完成率</span><b>{{ formatPct(fulfillmentSummary.load_rate) }}</b></div>
                  <div><span>送达率</span><b>{{ formatPct(fulfillmentSummary.arrival_rate) }}</b></div>
                </div>
              </div>
            </div>
            <div class="tianshu-fulfillment-card">
              <div class="tianshu-fulfillment-card__head"><span>履约闭环漏斗</span><b>FLOW-CHAIN</b></div>
              <div class="tianshu-fulfillment-funnel">
                <button
                  v-for="item in fulfillmentFunnel"
                  :key="item.key"
                  type="button"
                  class="tianshu-fulfillment-funnel__row"
                  @click="openFulfillmentFunnelDetail(item)"
                >
                  <span>{{ item.label }}</span>
                  <i><em :style="{ width: `${fulfillmentFunnelWidth(item)}%` }"></em></i>
                  <b>{{ item.count }}/{{ item.total }}</b>
                  <small>{{ formatPct(item.percent) }}</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card">
              <div class="tianshu-fulfillment-card__head"><span>供应商阻塞排行</span><b>BLOCK</b></div>
              <div v-if="!fulfillmentSupplierBlocks.length" class="tianshu-fulfillment-empty">暂无供应商阻塞</div>
              <div v-else class="tianshu-fulfillment-suppliers">
                <button
                  v-for="item in fulfillmentSupplierBlocks.slice(0, 5)"
                  :key="item.supplier_id"
                  type="button"
                  class="tianshu-fulfillment-supplier"
                  @click="openFulfillmentSupplierDetail(item)"
                >
                  <span>{{ item.supplier_name }}</span>
                  <b>{{ item.blocked_count }}</b>
                  <small>出库 {{ item.not_shipped }} · 分检 {{ item.not_sorted }} · 未随车 {{ item.not_loaded }}</small>
                </button>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'cold-chain'">
            <div class="tianshu-fulfillment-card tianshu-cold-card tianshu-fulfillment-card--command" @click="openColdChainHubDetail">
              <div class="tianshu-fulfillment-card__head">
                <span>冷链运力中枢</span>
                <b>{{ coldChainMode }}</b>
              </div>
              <p class="tianshu-cold-mode-hint">{{ coldChainModeHint }}</p>
              <div class="tianshu-cold-mode-strip">
                <div
                  v-for="item in coldChainModeStats"
                  :key="item.label"
                  :class="item.tone ? `is-${item.tone}` : ''"
                >
                  <span>{{ item.label }}</span>
                  <b>{{ item.value }}</b>
                </div>
              </div>
              <div class="tianshu-fulfillment-core tianshu-cold-core">
                <div class="tianshu-fulfillment-core__ring tianshu-cold-core__ring">
                  <span>{{ coldChainSummary.cold_score || 0 }}</span>
                  <small>冷链健康分</small>
                </div>
                <div class="tianshu-fulfillment-core__metrics">
                  <div><span>在线车辆</span><b>{{ coldChainSummary.online_vehicles || 0 }}/{{ coldChainSummary.vehicles || 0 }}</b></div>
                  <div><span>在线率</span><b>{{ formatPct(coldChainSummary.online_rate) }}</b></div>
                  <div><span>温控在线</span><b>{{ coldChainSummary.temperature_online || 0 }}</b></div>
                  <div><span>摄像头</span><b>{{ coldChainSummary.cameras || 0 }}</b></div>
                </div>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-cold-card">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ coldChainMode === "车辆轨迹" ? "车辆轨迹矩阵" : coldChainMode === "异常处置" ? "异常对象矩阵" : "仓温监控矩阵" }}</span>
                <b>{{ coldChainMode === "车辆轨迹" ? "TRACK" : coldChainMode === "异常处置" ? "DISPOSE" : "TEMP-GRID" }}</b>
              </div>
              <div v-if="coldChainMode === '车辆轨迹'" class="tianshu-cold-warehouse-grid">
                <button
                  v-for="item in coldChainModeVehicles.slice(0, 5)"
                  :key="`cold-vehicle-grid-${item.id}`"
                  type="button"
                  class="tianshu-cold-warehouse"
                  :class="{ 'is-alert': item.online_status !== 'online' || !item.coordinate_valid }"
                  @click="openColdVehicleDetail(item)"
                >
                  <span>{{ item.vehicle_no }}</span>
                  <b>{{ item.speed || 0 }}</b>
                  <small>{{ item.delivery_name || "配送商" }} · {{ item.reported_at || "暂无上报" }}</small>
                </button>
                <p v-if="!coldChainModeVehicles.length" class="tianshu-fulfillment-empty">暂无车辆轨迹</p>
              </div>
              <div v-else-if="coldChainMode === '异常处置'" class="tianshu-cold-warehouse-grid">
                <button
                  v-for="item in coldChainEvents.slice(0, 5)"
                  :key="`cold-event-grid-${item.id}`"
                  type="button"
                  class="tianshu-cold-warehouse is-alert"
                  @click="openColdEventDetail(item)"
                >
                  <span>{{ item.title || item.type }}</span>
                  <b>{{ item.level || "中" }}</b>
                  <small>{{ item.description || "等待处置" }}</small>
                </button>
                <p v-if="!coldChainEvents.length" class="tianshu-fulfillment-empty">暂无异常事件</p>
              </div>
              <div v-else-if="!coldChainModeWarehouses.length" class="tianshu-fulfillment-empty">暂无冷库设备</div>
              <div v-else class="tianshu-cold-warehouse-grid">
                <button
                  v-for="item in coldChainModeWarehouses.slice(0, 5)"
                  :key="item.id"
                  type="button"
                  class="tianshu-cold-warehouse"
                  :class="{ 'is-alert': coldWarehouseAlert(item) }"
                  @click="openColdWarehouseDetail(item)"
                >
                  <span>{{ item.name }}</span>
                  <b>{{ item.elitech_temperature || "—" }}℃</b>
                  <small>RH {{ item.elitech_humidity || "—" }}% · {{ item.elitech_online ? "在线" : "离线" }}</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-cold-card">
              <div class="tianshu-fulfillment-card__head"><span>温控异常</span><b>ALERT</b></div>
              <div class="tianshu-cold-alert-meter">
                <span>{{ coldChainSummary.temperature_alerts || 0 }}</span>
                <p>异常温控点</p>
                <small>离线车辆 {{ coldChainSummary.offline_vehicles || 0 }} · 无定位 {{ coldChainSummary.unlocated_vehicles || 0 }}</small>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'industry-insights'">
            <div class="tianshu-fulfillment-card tianshu-industry-card tianshu-fulfillment-card--command" @click="openIndustryHubDetail">
              <div class="tianshu-fulfillment-card__head">
                <span>产业预测中枢</span>
                <b>{{ industryMode }}</b>
              </div>
              <p class="tianshu-industry-mode-hint">{{ industryModeHint }}</p>
              <div class="tianshu-industry-mode-strip">
                <div
                  v-for="item in industryModeStats"
                  :key="item.label"
                  :class="item.tone ? `is-${item.tone}` : ''"
                >
                  <span>{{ item.label }}</span>
                  <b>{{ item.value }}</b>
                </div>
              </div>
              <div class="tianshu-industry-orbit">
                <div class="tianshu-industry-orbit__core">
                  <span>{{ industrySummary.forecast_usable || 0 }}</span>
                  <small>预测可用</small>
                </div>
                <div class="tianshu-industry-orbit__metrics">
                  <div><span>监测品类</span><b>{{ industrySummary.monitored_categories || 0 }}</b></div>
                  <div><span>波动品种</span><b>{{ industrySummary.volatile_products || 0 }}</b></div>
                  <div><span>报价商品</span><b>{{ industrySummary.quote_count || 0 }}</b></div>
                  <div><span>热销</span><b>{{ industrySummary.hot_goods || "—" }}</b></div>
                </div>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-industry-card">
              <div class="tianshu-fulfillment-card__head"><span>{{ industryPrimaryTitle }}</span><b>{{ industryMode === "价格脉冲" ? "PULSE" : "FORECAST" }}</b></div>
              <div v-if="industryError" class="tianshu-fulfillment-empty">{{ industryError }}</div>
              <div v-else-if="!industryModeForecasts.length" class="tianshu-fulfillment-empty">暂无行情预测</div>
              <div v-else class="tianshu-industry-price-list">
                <button
                  v-for="item in industryModeForecasts.slice(0, 5)"
                  :key="item.product_name"
                  type="button"
                  :class="{ 'is-up': Number(item.change_pct) >= 0, 'is-volatile': Math.abs(Number(item.change_pct) || 0) >= 5 }"
                  @click="openIndustryItemDetail(item, '价格品种')"
                >
                  <span>{{ item.product_name }}</span>
                  <b>{{ item.change_pct || 0 }}%</b>
                  <small>预测 {{ item.forecast_price || "—" }} · 置信 {{ item.confidence || "—" }}%</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-industry-card">
              <div class="tianshu-fulfillment-card__head"><span>{{ industryMode === "采购影响" ? "采购影响提示" : "平台品类结构" }}</span><b>{{ industryMode === "采购影响" ? "IMPACT" : "CATEGORY" }}</b></div>
              <div class="tianshu-fulfillment-suppliers">
                <template v-if="industryMode === '采购影响'">
                  <button
                    v-for="item in industryImpacts.slice(0, 5)"
                    :key="`${item.target}-${item.title}`"
                    type="button"
                    class="tianshu-fulfillment-supplier tianshu-industry-category"
                    @click="openIndustryItemDetail(item, '采购影响')"
                  >
                    <span>{{ item.title }}</span>
                    <b>{{ item.level || "中" }}</b>
                    <small>{{ item.impact }}</small>
                  </button>
                  <p v-if="!industryImpacts.length" class="tianshu-fulfillment-empty">暂无采购影响提示</p>
                </template>
                <template v-else>
                  <button
                    v-for="item in industryCategories.slice(0, 5)"
                    :key="item.category_name"
                    type="button"
                    class="tianshu-fulfillment-supplier tianshu-industry-category"
                    @click="openIndustryItemDetail(item, '品类')"
                  >
                    <span>{{ item.category_name }}</span>
                    <b>¥{{ compactMoney(item.total_amount) }}</b>
                    <small>{{ item.order_count || 0 }} 单 · {{ item.total_quantity || 0 }} 件</small>
                  </button>
                  <p v-if="!industryCategories.length" class="tianshu-fulfillment-empty">暂无平台品类订单</p>
                </template>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'city-profile'">
            <div class="tianshu-fulfillment-card tianshu-city-card tianshu-fulfillment-card--command" @click="openCityProfileHubDetail">
              <div class="tianshu-fulfillment-card__head">
                <span>城市覆盖中枢</span>
                <b>{{ cityProfileMode }}</b>
              </div>
              <p class="tianshu-city-mode-hint">{{ cityModeHint }}</p>
              <div class="tianshu-city-mode-strip">
                <div
                  v-for="item in cityModeStats"
                  :key="item.label"
                  :class="item.tone ? `is-${item.tone}` : ''"
                >
                  <span>{{ item.label }}</span>
                  <b>{{ item.value }}</b>
                </div>
              </div>
              <div class="tianshu-city-core">
                <div class="tianshu-city-core__ring">
                  <span>{{ cityProfileSummary.district_cover_count || 0 }}</span>
                  <small>覆盖区县</small>
                </div>
                <div class="tianshu-city-core__metrics">
                  <div><span>活跃食堂</span><b>{{ cityProfileSummary.active_canteens || 0 }}</b></div>
                  <div><span>活跃客户</span><b>{{ cityProfileSummary.active_clients || 0 }}</b></div>
                  <div><span>订单</span><b>{{ cityProfileSummary.total_orders || 0 }}</b></div>
                  <div><span>GMV</span><b>¥{{ compactMoney(cityProfileSummary.total_gmv) }}</b></div>
                </div>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-city-card">
              <div class="tianshu-fulfillment-card__head"><span>{{ cityPrimaryTitle }}</span><b>DISTRICT</b></div>
              <div v-if="cityProfileError" class="tianshu-fulfillment-empty">{{ cityProfileError }}</div>
              <div v-else-if="!cityModeDistricts.length" class="tianshu-fulfillment-empty">暂无区县画像</div>
              <div v-else class="tianshu-city-districts">
                <button
                  v-for="item in cityModeDistricts.slice(0, 6)"
                  :key="item.district_name"
                  type="button"
                  @click="openCityDistrictDetail(item)"
                >
                  <span>{{ item.district_name }}</span>
                  <i><em :style="{ width: `${Math.min(100, Math.max(10, Number(item.order_count) || 0))}%` }"></em></i>
                  <b>¥{{ compactMoney(item.gmv) }}</b>
                  <small>{{ item.order_count }} 单 · {{ item.canteen_count }} 食堂</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-city-card">
              <div class="tianshu-fulfillment-card__head"><span>{{ citySecondaryTitle }}</span><b>{{ citySecondaryCode }}</b></div>
              <div class="tianshu-city-coverage">
                <div><span>客户</span><b>{{ cityProfileSummary.active_clients || 0 }}</b></div>
                <div><span>食堂</span><b>{{ cityProfileSummary.active_canteens || 0 }}</b></div>
                <div><span>{{ cityProfileMode === "风险密度" ? "风险区" : "薄弱区" }}</span><b>{{ cityProfileMode === "风险密度" ? cityRiskDistricts.length : cityThinAreas.length }}</b></div>
              </div>
            </div>
          </template>
          <template v-else>
            <!-- 大宗商品销售额 -->
            <BulkCommoditySalesChart></BulkCommoditySalesChart>
            <!-- 年度经济增长点 -->
            <YearlyEconomyTrend></YearlyEconomyTrend>
            <!-- 近年经济情况 -->
            <EconomicTrendChart></EconomicTrendChart>
            <!-- 各区经济收益 -->
            <DistrictEconomicIncome></DistrictEconomicIncome>
          </template>
        </div>
      </div>
      <!-- 右边布局 图表 -->
      <div class="right-wrap">
        <div
          class="right-wrap-3d tianshu-shell-enter tianshu-shell-enter--col-right"
          :class="{ 'is-visible': shellEnterReady }"
        >
          <template v-if="activeView === 'risk-warning'">
            <div class="tianshu-risk-card tianshu-risk-card--list">
              <div class="tianshu-risk-card__head">
                <span>{{ riskPrimaryTitle }}</span>
                <b>{{ riskLoading ? "SYNC" : riskMode }}</b>
              </div>
              <p class="tianshu-risk-mode-hint">{{ riskModeHint }}</p>
              <div v-if="riskError" class="tianshu-risk-empty">{{ riskError }}</div>
              <div v-else-if="!riskItemsByMode.length" class="tianshu-risk-empty">今日暂无风险事件</div>
              <div v-else class="tianshu-risk-feed">
                <button
                  v-for="item in riskItemsByMode"
                  :key="item.id"
                  type="button"
                  class="tianshu-risk-feed__item"
                  :class="`is-${riskLevelClass(item.level)}`"
                  @click="openRiskItemDetail(item)"
                >
                  <div class="tianshu-risk-feed__top">
                    <span>{{ item.type }}</span>
                    <b>{{ item.level }}</b>
                  </div>
                  <p>{{ item.description || item.customer_name }}</p>
                  <div class="tianshu-risk-feed__foot">
                    <span>{{ item.order_sn || item.customer_name || "监管告警" }}</span>
                    <span>{{ formatRiskTime(item.created_at) }}</span>
                  </div>
                </button>
              </div>
            </div>
            <div class="tianshu-risk-card tianshu-risk-card--money">
              <div class="tianshu-risk-card__head"><span>{{ riskSecondaryTitle }}</span><b>{{ riskMode === "处置队列" ? "ACTION" : riskMode === "风险光柱" ? "TYPE-MIX" : "RETURN" }}</b></div>
              <div class="tianshu-risk-money">
                <template v-if="riskMode === '处置队列'">
                  <span>建议动作</span>
                  <b>{{ riskRecommendations.length }}</b>
                  <small>{{ riskRecommendations[0]?.title || "暂无处置建议" }}</small>
                </template>
                <template v-else-if="riskMode === '风险光柱'">
                  <span>风险点位</span>
                  <b>{{ riskMapPointsByMode.length }}</b>
                  <small>高风险 {{ riskKpis.high_count }} · 中风险 {{ riskKpis.medium_count }}</small>
                </template>
                <template v-else>
                  <span>退单金额</span>
                  <b>¥{{ compactMoney(riskKpis.return_amount) }}</b>
                  <small>异常订单金额 ¥{{ compactMoney(riskKpis.abnormal_amount) }}</small>
                </template>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'fulfillment'">
            <div class="tianshu-fulfillment-card tianshu-fulfillment-card--list">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ fulfillmentPrimaryTitle }}</span>
                <b>{{ fulfillmentLoading ? "SYNC" : fulfillmentMode }}</b>
              </div>
              <p class="tianshu-fulfillment-mode-hint">{{ fulfillmentModeHint }}</p>
              <div v-if="fulfillmentError" class="tianshu-fulfillment-empty">{{ fulfillmentError }}</div>
              <div v-else-if="fulfillmentMode === '订单光柱'" class="tianshu-fulfillment-trips">
                <button
                  v-for="item in fulfillmentData.orders_detail.slice(0, 7)"
                  :key="`ful-order-${item.order_id}`"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  @click="setFulfillmentDrawer({
                    title: item.order_no || '订单详情',
                    subtitle: item.client_name || item.canteen_name || '订单光柱',
                    conclusion: `该订单当前状态 ${item.status || '—'}，关联车次 ${item.route_no || '暂未绑定'}。`,
                    summaryCards: [
                      { label: '金额', value: `¥${formatMoney(item.amount)}` },
                      { label: '状态', value: item.status || '—' },
                      { label: '车次', value: item.route_no || '暂未绑定' },
                    ],
                    sections: [{ title: '订单明细', rows: fulfillmentOrderRows([item]) }],
                  })"
                >
                  <div><span>{{ item.order_no }}</span><b>{{ item.status || "—" }}</b></div>
                  <p>{{ item.client_name || item.canteen_name || "客户" }} · {{ item.delivery_name || "配送商" }}</p>
                  <small>金额 ¥{{ formatMoney(item.amount) }} · 车次 {{ item.route_no || "暂未绑定" }}</small>
                </button>
                <p v-if="!fulfillmentData.orders_detail.length" class="tianshu-fulfillment-empty">暂无订单点位</p>
              </div>
              <div v-else-if="fulfillmentMode === '履约热力'" class="tianshu-fulfillment-trips">
                <button
                  v-for="item in fulfillmentRiskEvents.slice(0, 7)"
                  :key="`ful-risk-primary-${item.id}`"
                  type="button"
                  class="tianshu-fulfillment-trip is-blocked"
                  @click="openFulfillmentRiskDetail(item)"
                >
                  <div><span>{{ item.type }}</span><b>{{ item.level || "中" }}</b></div>
                  <p>{{ item.title || item.route_no || "履约风险" }}</p>
                  <small>{{ item.description || "等待处置" }}</small>
                </button>
                <p v-if="!fulfillmentRiskEvents.length" class="tianshu-fulfillment-empty">暂无履约热力风险</p>
              </div>
              <div v-else-if="!fulfillmentModeTrips.length" class="tianshu-fulfillment-empty">今日暂无配送车次</div>
              <div v-else class="tianshu-fulfillment-trips">
                <button
                  v-for="item in fulfillmentModeTrips.slice(0, 7)"
                  :key="item.id"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  :class="fulfillmentTripClass(item)"
                  @click="openFulfillmentTripDetail(item)"
                >
                  <div><span>{{ item.route_no }}</span><b>{{ item.status }}</b></div>
                  <p>{{ item.delivery_name }} · {{ item.vehicle_no || "未定车" }} · {{ item.driver_name || "未填司机" }}</p>
                  <small>站点 {{ item.stop_count }} · 阻塞 {{ item.blocked_count }} · 未随车 {{ item.not_loaded_count }}</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ fulfillmentMode === "履约热力" ? "供应商阻塞" : fulfillmentMode === "订单光柱" ? "订单光柱摘要" : "在途订单/站点" }}</span>
                <b>{{ fulfillmentMode === "履约热力" ? "BLOCK" : fulfillmentMode === "订单光柱" ? "ORDER" : "ON-ROAD" }}</b>
              </div>
              <div class="tianshu-fulfillment-mini-list">
                <template v-if="fulfillmentMode === '履约热力'">
                  <button
                    v-for="item in fulfillmentSupplierBlocks.slice(0, 4)"
                    :key="`mode-block-${item.supplier_id}`"
                    type="button"
                    @click="openFulfillmentSupplierDetail(item)"
                  >
                    <span>{{ item.supplier_name }}</span>
                    <b>{{ item.blocked_count }}</b>
                    <small>出库 {{ item.not_shipped }} · 分检 {{ item.not_sorted }} · 未随车 {{ item.not_loaded }}</small>
                  </button>
                  <p v-if="!fulfillmentSupplierBlocks.length" class="tianshu-fulfillment-empty">暂无供应商阻塞</p>
                </template>
                <template v-else-if="fulfillmentMode === '订单光柱'">
                  <button
                    v-for="item in fulfillmentData.orders_detail.slice(0, 4)"
                    :key="`mode-order-${item.order_id}`"
                    type="button"
                    @click="setFulfillmentDrawer({
                      title: item.order_no || '订单详情',
                      subtitle: item.client_name || item.canteen_name || '订单光柱',
                      conclusion: `该订单当前状态 ${item.status || '—'}，关联车次 ${item.route_no || '暂未绑定'}。`,
                      summaryCards: [
                        { label: '金额', value: `¥${formatMoney(item.amount)}` },
                        { label: '状态', value: item.status || '—' },
                      ],
                      sections: [{ title: '订单明细', rows: fulfillmentOrderRows([item]) }],
                    })"
                  >
                    <span>{{ item.order_no }}</span>
                    <b>¥{{ compactMoney(item.amount) }}</b>
                    <small>{{ item.client_name || item.canteen_name || "客户" }} · {{ item.status || "—" }}</small>
                  </button>
                  <p v-if="!fulfillmentData.orders_detail.length" class="tianshu-fulfillment-empty">暂无订单摘要</p>
                </template>
                <button
                  v-else
                  v-for="item in fulfillmentInTransit.slice(0, 4)"
                  :key="`road-${item.id}`"
                  type="button"
                  @click="openFulfillmentTripDetail(item)"
                >
                  <span>{{ item.route_no }}</span>
                  <b>{{ item.stop_count }} 站</b>
                  <small>{{ item.vehicle_no || "未定车" }} · {{ item.departure_time || "待定" }}</small>
                </button>
                <p v-if="!fulfillmentInTransit.length" class="tianshu-fulfillment-empty">暂无在途车次</p>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ fulfillmentMode === "车次下钻" ? "车次风险事件" : "履约风险事件" }}</span>
                <b>{{ fulfillmentMode === "车次下钻" ? "TRIP-RISK" : "EXCEPTION" }}</b>
              </div>
              <div class="tianshu-fulfillment-mini-list tianshu-fulfillment-mini-list--risk">
                <button
                  v-for="item in fulfillmentRiskEvents.slice(0, 4)"
                  :key="item.id"
                  type="button"
                  @click="openFulfillmentRiskDetail(item)"
                >
                  <span>{{ item.type }}</span>
                  <b>{{ item.level || "中" }}</b>
                  <small>{{ item.description || item.title }}</small>
                </button>
                <p v-if="!fulfillmentRiskEvents.length" class="tianshu-fulfillment-empty">暂无履约异常</p>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'cold-chain'">
            <div class="tianshu-fulfillment-card tianshu-cold-card tianshu-fulfillment-card--list">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ coldChainPrimaryTitle }}</span>
                <b>{{ coldChainLoading ? "SYNC" : coldChainMode }}</b>
              </div>
              <div v-if="coldChainError" class="tianshu-fulfillment-empty">{{ coldChainError }}</div>
              <div v-else-if="coldChainMode === '仓温监控'" class="tianshu-fulfillment-trips">
                <button
                  v-for="item in coldChainModeWarehouses.slice(0, 7)"
                  :key="`cold-primary-wh-${item.id}`"
                  type="button"
                  class="tianshu-fulfillment-trip tianshu-cold-vehicle"
                  :class="{ 'is-blocked': coldWarehouseAlert(item) }"
                  @click="openColdWarehouseDetail(item)"
                >
                  <div><span>{{ item.name }}</span><b>{{ item.elitech_temperature || "—" }}℃</b></div>
                  <p>{{ item.delivery_name || "配送商" }} · {{ item.address || "地址未填" }}</p>
                  <small>RH {{ item.elitech_humidity || "—" }}% · {{ item.elitech_online ? "在线" : "离线" }} · 摄像头 {{ item.cameras?.length || 0 }}</small>
                </button>
                <p v-if="!coldChainModeWarehouses.length" class="tianshu-fulfillment-empty">暂无仓温设备</p>
              </div>
              <div v-else-if="coldChainMode === '异常处置'" class="tianshu-fulfillment-trips">
                <button
                  v-for="item in coldChainEvents.slice(0, 7)"
                  :key="`cold-primary-event-${item.id}`"
                  type="button"
                  class="tianshu-fulfillment-trip tianshu-cold-vehicle is-blocked"
                  @click="openColdEventDetail(item)"
                >
                  <div><span>{{ item.type }}</span><b>{{ item.level || "中" }}</b></div>
                  <p>{{ item.title || "异常对象" }}</p>
                  <small>{{ item.description || "等待处置" }}</small>
                </button>
                <p v-if="!coldChainEvents.length" class="tianshu-fulfillment-empty">暂无温控异常</p>
              </div>
              <div v-else-if="!coldChainModeVehicles.length" class="tianshu-fulfillment-empty">暂无冷链车辆</div>
              <div v-else class="tianshu-fulfillment-trips">
                <button
                  v-for="item in coldChainModeVehicles.slice(0, 7)"
                  :key="item.id"
                  type="button"
                  class="tianshu-fulfillment-trip tianshu-cold-vehicle"
                  :class="{ 'is-blocked': item.online_status !== 'online' || !item.coordinate_valid }"
                  @click="openColdVehicleDetail(item)"
                >
                  <div><span>{{ item.vehicle_no }}</span><b>{{ item.online_status || "offline" }}</b></div>
                  <p>{{ item.delivery_name || "配送商" }} · {{ item.driver_name || "未填司机" }}</p>
                  <small>速度 {{ item.speed || 0 }} · {{ item.reported_at || "暂无上报" }} · 摄像头 {{ item.cameras?.length || 0 }}</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-cold-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>{{ coldChainSecondaryTitle }}</span><b>{{ coldChainSecondaryCode }}</b></div>
              <div class="tianshu-fulfillment-mini-list">
                <template v-if="coldChainMode === '异常处置'">
                  <button
                    v-for="item in coldChainSecondaryItems.slice(0, 4)"
                    :key="`cold-sub-event-${item.id}`"
                    type="button"
                    @click="openColdEventDetail(item)"
                  >
                    <span>{{ item.title || item.type }}</span>
                    <b>{{ item.level || "中" }}</b>
                    <small>{{ item.description || "等待处置" }}</small>
                  </button>
                </template>
                <template v-else>
                  <button
                    v-for="item in coldChainSecondaryItems.slice(0, 4)"
                    :key="`cold-sub-${item.id}`"
                    type="button"
                    @click="coldChainMode === '车辆轨迹' ? openColdVehicleDetail(item) : openColdWarehouseDetail(item)"
                  >
                    <span>{{ coldChainMode === "车辆轨迹" ? item.vehicle_no : item.name }}</span>
                    <b>{{ coldChainMode === "车辆轨迹" ? (item.online_status || "offline") : `${item.elitech_temperature || "—"}℃` }}</b>
                    <small>{{ item.delivery_name || "配送商" }} · {{ coldChainMode === "车辆轨迹" ? (item.reported_at || "暂无上报") : (item.elitech_bound ? "已绑定" : "未绑定") }}</small>
                  </button>
                </template>
                <p v-if="!coldChainSecondaryItems.length" class="tianshu-fulfillment-empty">暂无对象</p>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-cold-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>温控异常事件</span><b>EXCEPTION</b></div>
              <div class="tianshu-fulfillment-mini-list tianshu-fulfillment-mini-list--risk">
                <button
                  v-for="item in coldChainEvents.slice(0, 4)"
                  :key="item.id"
                  type="button"
                  @click="openColdEventDetail(item)"
                >
                  <span>{{ item.type }}</span>
                  <b>{{ item.level || "中" }}</b>
                  <small>{{ item.description || item.title }}</small>
                </button>
                <p v-if="!coldChainEvents.length" class="tianshu-fulfillment-empty">暂无温控异常</p>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'industry-insights'">
            <div class="tianshu-fulfillment-card tianshu-industry-card tianshu-fulfillment-card--list">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ industryPrimaryTitle }}</span>
                <b>{{ industryLoading ? "SYNC" : industryMode }}</b>
              </div>
              <p class="tianshu-industry-mode-hint">{{ industryModeHint }}</p>
              <div v-if="industryMode === '采购影响'" class="tianshu-fulfillment-trips tianshu-industry-goods">
                <button
                  v-for="item in industryImpacts.slice(0, 7)"
                  :key="`industry-primary-impact-${item.target}-${item.title}`"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  @click="openIndustryItemDetail(item, '采购影响')"
                >
                  <div><span>{{ item.title }}</span><b>{{ item.level || "中" }}</b></div>
                  <p>{{ item.impact }}</p>
                  <small>关联品种 {{ item.target || "—" }}</small>
                </button>
                <p v-if="!industryImpacts.length" class="tianshu-fulfillment-empty">暂无采购影响提示</p>
              </div>
              <div v-else-if="industryMode === '预测曲线' || industryMode === '价格脉冲'" class="tianshu-fulfillment-trips tianshu-industry-goods">
                <button
                  v-for="item in industryModeForecasts.slice(0, 7)"
                  :key="`industry-primary-forecast-${item.product_name}`"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  :class="{ 'is-blocked': Math.abs(Number(item.change_pct) || 0) >= 5 }"
                  @click="openIndustryItemDetail(item, '价格品种')"
                >
                  <div><span>{{ item.product_name }}</span><b>{{ item.change_pct || 0 }}%</b></div>
                  <p>最新 {{ item.latest_price || "—" }} · 预测 {{ item.forecast_price || "—" }}</p>
                  <small>置信 {{ item.confidence || "—" }}% · {{ item.status || "可预测" }}</small>
                </button>
                <p v-if="!industryModeForecasts.length" class="tianshu-fulfillment-empty">暂无行情预测</p>
              </div>
              <div v-else-if="!industryModeGoods.length" class="tianshu-fulfillment-empty">暂无平台商品排行</div>
              <div v-else class="tianshu-fulfillment-trips tianshu-industry-goods">
                <button
                  v-for="item in industryModeGoods.slice(0, 7)"
                  :key="item.goods_name"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  @click="openIndustryItemDetail(item, '商品')"
                >
                  <div><span>{{ item.goods_name }}</span><b>¥{{ compactMoney(item.total_amount) }}</b></div>
                  <p>订单 {{ item.order_count || 0 }} · 销量 {{ item.total_quantity || 0 }}</p>
                  <small>用于和全国行情/供应商报价做采购影响联动</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-industry-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>{{ industrySecondaryTitle }}</span><b>{{ industrySecondaryCode }}</b></div>
              <div class="tianshu-fulfillment-mini-list tianshu-industry-impact">
                <template v-if="industryMode === '预测曲线'">
                  <button
                    v-for="item in industryData.price_series.slice(0, 4)"
                    :key="`industry-sub-series-${item.product_name}-${item.date}`"
                    type="button"
                    @click="openIndustryItemDetail(item, '行情样本')"
                  >
                    <span>{{ item.product_name }}</span>
                    <b>{{ item.avg_price || "—" }}</b>
                    <small>{{ item.category_name || "全国农产品" }} · {{ item.date }}</small>
                  </button>
                  <p v-if="!industryData.price_series.length" class="tianshu-fulfillment-empty">暂无全国行情样本</p>
                </template>
                <template v-else-if="industryMode === '采购影响'">
                  <button
                    v-for="item in industryModeGoods.slice(0, 4)"
                    :key="`industry-sub-goods-${item.goods_name}`"
                    type="button"
                    @click="openIndustryItemDetail(item, '商品')"
                  >
                    <span>{{ item.goods_name }}</span>
                    <b>¥{{ compactMoney(item.total_amount) }}</b>
                    <small>订单 {{ item.order_count || 0 }} · 销量 {{ item.total_quantity || 0 }}</small>
                  </button>
                  <p v-if="!industryModeGoods.length" class="tianshu-fulfillment-empty">暂无关联业务商品</p>
                </template>
                <template v-else>
                  <button
                    v-for="item in industryImpacts.slice(0, 4)"
                    :key="`${item.target}-${item.title}`"
                    type="button"
                    @click="openIndustryItemDetail(item, '采购影响')"
                  >
                    <span>{{ item.title }}</span>
                    <b>{{ item.level || "中" }}</b>
                    <small>{{ item.impact }}</small>
                  </button>
                  <p v-if="!industryImpacts.length" class="tianshu-fulfillment-empty">暂无采购影响提示</p>
                </template>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-industry-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>全国行情样本</span><b>NATION</b></div>
              <div class="tianshu-fulfillment-mini-list">
                <button
                  v-for="item in industryData.price_series.slice(0, 4)"
                  :key="`${item.product_name}-${item.date}`"
                  type="button"
                  @click="openIndustryItemDetail(item, '行情样本')"
                >
                  <span>{{ item.product_name }}</span>
                  <b>{{ item.avg_price || "—" }}</b>
                  <small>{{ item.category_name || "全国农产品" }} · {{ item.date }}</small>
                </button>
                <p v-if="!industryData.price_series.length" class="tianshu-fulfillment-empty">暂无全国行情样本</p>
              </div>
            </div>
          </template>
          <template v-else-if="activeView === 'city-profile'">
            <div class="tianshu-fulfillment-card tianshu-city-card tianshu-fulfillment-card--list">
              <div class="tianshu-fulfillment-card__head">
                <span>{{ cityPrimaryTitle }}</span>
                <b>{{ cityProfileLoading ? "SYNC" : cityProfileMode }}</b>
              </div>
              <p class="tianshu-city-mode-hint">{{ cityModeHint }}</p>
              <div v-if="!cityModeDistricts.length" class="tianshu-fulfillment-empty">暂无区域履约画像</div>
              <div v-else class="tianshu-fulfillment-trips tianshu-city-list">
                <button
                  v-for="item in cityModeDistricts.slice(0, 7)"
                  :key="item.district_name"
                  type="button"
                  class="tianshu-fulfillment-trip"
                  @click="openCityDistrictDetail(item)"
                >
                  <div>
                    <span>{{ item.district_name }}</span>
                    <b>{{ cityProfileMode === "风险密度" ? `${item.risk_count || 0}险` : cityProfileMode === "客户覆盖" ? `${item.client_count || 0}客` : `${item.growth_pct || 0}%` }}</b>
                  </div>
                  <p>订单 {{ item.order_count || 0 }} · 车次 {{ item.fulfillment_count || 0 }} · GMV ¥{{ compactMoney(item.gmv) }}</p>
                  <small>客户 {{ item.client_count || 0 }} · 食堂 {{ item.canteen_count || 0 }}</small>
                </button>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-city-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>{{ citySecondaryTitle }}</span><b>{{ citySecondaryCode }}</b></div>
              <div class="tianshu-fulfillment-mini-list tianshu-fulfillment-mini-list--risk">
                <button
                  v-for="item in citySecondaryItems.slice(0, 4)"
                  :key="`city-sub-${item.district_name}`"
                  type="button"
                  @click="openCityDistrictDetail(item)"
                >
                  <span>{{ item.district_name }}</span>
                  <b>{{ cityProfileMode === "客户覆盖" ? `${item.client_count || 0}` : cityProfileMode === "区县热力" ? `${item.growth_pct || 0}%` : item.risk_count || 0 }}</b>
                  <small>订单 {{ item.order_count || 0 }} · 食堂 {{ item.canteen_count || 0 }} · GMV ¥{{ compactMoney(item.gmv) }}</small>
                </button>
                <p v-if="!citySecondaryItems.length" class="tianshu-fulfillment-empty">暂无区域对象</p>
              </div>
            </div>
            <div class="tianshu-fulfillment-card tianshu-city-card tianshu-fulfillment-card--split">
              <div class="tianshu-fulfillment-card__head"><span>增长/薄弱区建议</span><b>ACTION</b></div>
              <div class="tianshu-fulfillment-mini-list">
                <button
                  v-for="item in cityThinAreas.slice(0, 4)"
                  :key="`thin-${item.district_name}`"
                  type="button"
                  @click="openCityDistrictDetail(item)"
                >
                  <span>{{ item.district_name }}</span>
                  <b>{{ item.client_count || 0 }} 客户</b>
                  <small>覆盖薄弱，建议拓展食堂点位并校验履约频次</small>
                </button>
                <p v-if="!cityThinAreas.length" class="tianshu-fulfillment-empty">暂无薄弱区建议</p>
              </div>
            </div>
          </template>
          <template v-else>
            <!-- 专项资金用途 -->
            <PurposeSpecialFunds> </PurposeSpecialFunds>
            <!-- 人群消费占比 -->
            <ProportionPopulationConsumption></ProportionPopulationConsumption>
            <!-- 用电情况 -->
            <ElectricityUsage></ElectricityUsage>
            <!-- 各季度增长情况 -->
            <QuarterlyGrowthSituation></QuarterlyGrowthSituation>
          </template>
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
        <div ref="bottomMenuRef" class="bottom-menu" @click="onBottomTrayContainerClick">
          <div
            v-for="item in bottomTrayItems"
            :key="item"
            role="button"
            tabindex="0"
            class="bottom-menu-item"
            :data-bottom-tray-item="item"
            :class="{ 'is-active': item === bottomTrayActive }"
            @click="onBottomTraySelect(item)"
            @keydown.enter.prevent="onBottomTraySelect(item)"
            @keydown.space.prevent="onBottomTraySelect(item)"
          >
            <span>{{ item }}</span>
          </div>
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
              >¥{{ opsLiveGmvYuan }}<small>元</small></span
            >
          </div>
          <div class="tianshu-ops-console__metric">
            <span class="tianshu-ops-console__k">今日下单</span>
            <span class="tianshu-ops-console__v"
              >{{ opsLiveOrderCountText }}<small>单</small></span
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

    <teleport to="body">
      <div
        v-if="fulfillmentDrawerOpen"
        class="tianshu-fulfillment-drawer-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tianshu-fulfillment-drawer-title"
        @click.self="closeFulfillmentDrawer"
      >
        <aside class="tianshu-fulfillment-drawer" @click.stop>
          <header class="tianshu-fulfillment-drawer__head">
            <div>
              <p>SUPPLY CHAIN DRILLDOWN</p>
              <h2 id="tianshu-fulfillment-drawer-title">{{ fulfillmentDrawerState.title }}</h2>
              <span>{{ fulfillmentDrawerState.subtitle }}</span>
            </div>
            <button type="button" @click="closeFulfillmentDrawer">×</button>
          </header>
          <div
            v-if="drawerModeItems.length"
            class="tianshu-fulfillment-drawer__modes"
            aria-label="大屏子模式切换"
          >
            <button
              v-for="item in drawerModeItems"
              :key="`drawer-mode-${item}`"
              type="button"
              :class="{ 'is-active': item === bottomTrayActive }"
              @click.stop="onBottomTraySelect(item)"
            >
              {{ item }}
            </button>
          </div>
          <div class="tianshu-fulfillment-drawer__scan" aria-hidden="true" />
          <p v-if="fulfillmentDrawerState.conclusion" class="tianshu-fulfillment-drawer__conclusion">
            {{ fulfillmentDrawerState.conclusion }}
          </p>
          <div v-if="fulfillmentDrawerState.summaryCards.length" class="tianshu-fulfillment-drawer__cards">
            <div
              v-for="card in fulfillmentDrawerState.summaryCards"
              :key="card.label"
              class="tianshu-fulfillment-drawer__card"
              :class="card.tone ? `is-${card.tone}` : ''"
            >
              <span>{{ card.label }}</span>
              <b>{{ card.value }}</b>
            </div>
          </div>
          <section
            v-if="fulfillmentDrawerState.deviceTarget"
            class="tianshu-fulfillment-drawer__section tianshu-device-link"
          >
            <div class="tianshu-device-link__head">
              <h3>设备链路</h3>
              <span v-if="deviceBindingState.loading">同步绑定...</span>
              <span v-else-if="deviceBindingState.error">{{ deviceBindingState.error }}</span>
              <span v-else>配送商端绑定 · 监管只读</span>
            </div>
            <div v-if="deviceBindingState.data" class="tianshu-device-link__cards">
              <div
                v-for="card in deviceBindingSummary(deviceBindingState.data)"
                :key="`device-card-${card.label}`"
                class="tianshu-device-link__card"
                :class="card.tone ? `is-${card.tone}` : ''"
              >
                <span>{{ card.label }}</span>
                <b>{{ card.value }}</b>
              </div>
            </div>
            <div v-if="deviceBindingState.data" class="tianshu-fulfillment-drawer__rows tianshu-device-link__rows">
              <div
                v-for="(row, rowIdx) in deviceBindingRows"
                :key="`device-binding-row-${rowIdx}`"
                class="tianshu-fulfillment-drawer__row"
              >
                <div
                  v-for="(value, key) in row"
                  :key="key"
                  class="tianshu-fulfillment-drawer__cell"
                >
                  <span>{{ key }}</span>
                  <b>{{ value || "—" }}</b>
                </div>
              </div>
            </div>
            <div v-if="deviceBindingState.data?.beidou_device" class="tianshu-device-link__devices">
              <button type="button" class="tianshu-device-chip is-beidou" @click="openBeidouTrackPanel">
                <span>北斗轨迹</span>
                <b>{{ deviceName(deviceBindingState.data.beidou_device) }}</b>
                <small>{{ deviceOnlineText(deviceBindingState.data.beidou_device.online_status) }}</small>
              </button>
            </div>
            <div v-if="deviceBindingState.data?.elitech?.elitech_bound" class="tianshu-device-link__devices">
              <button type="button" class="tianshu-device-chip is-elitech" @click="openElitechCurvePanel">
                <span>冷云曲线</span>
                <b>{{ deviceBindingState.data.elitech.elitech_device_name || deviceBindingState.data.elitech.elitech_sn }}</b>
                <small>{{ deviceBindingState.data.elitech.elitech_temperature || "—" }}℃ · RH {{ deviceBindingState.data.elitech.elitech_humidity || "—" }}%</small>
              </button>
            </div>
            <div v-if="deviceBindingState.data?.cameras?.length" class="tianshu-device-link__devices">
              <button
                v-for="camera in deviceBindingState.data.cameras"
                :key="`device-camera-${camera.id}`"
                type="button"
                class="tianshu-device-chip is-camera"
                @click="openCameraDevicePanel(camera)"
              >
                <span>摄像头直播</span>
                <b>{{ deviceName(camera) }}</b>
                <small>{{ deviceOnlineText(camera.online_status) }}</small>
              </button>
            </div>
            <p v-if="!deviceBindingState.loading && !deviceBindingState.error && !deviceBindingState.data" class="tianshu-fulfillment-empty">
              暂无设备绑定
            </p>
          </section>
          <section
            v-for="section in fulfillmentDrawerState.sections"
            :key="section.title"
            class="tianshu-fulfillment-drawer__section"
          >
            <h3>{{ section.title }}</h3>
            <div v-if="section.rows?.length" class="tianshu-fulfillment-drawer__rows">
              <div
                v-for="(row, rowIdx) in section.rows"
                :key="rowIdx"
                class="tianshu-fulfillment-drawer__row"
              >
                <div
                  v-for="(value, key) in row"
                  :key="key"
                  class="tianshu-fulfillment-drawer__cell"
                >
                  <span>{{ key }}</span>
                  <b>{{ value || "—" }}</b>
                </div>
              </div>
            </div>
            <p v-else class="tianshu-fulfillment-empty">暂无明细</p>
          </section>
        </aside>
      </div>
    </teleport>

    <teleport to="body">
      <div
        v-if="deviceOverlayState.open"
        class="tianshu-device-overlay"
        role="dialog"
        aria-modal="true"
        @click.self="closeDeviceOverlay"
      >
        <aside class="tianshu-device-panel" @click.stop>
          <header class="tianshu-device-panel__head">
            <div>
              <p>{{ deviceOverlayState.type === "camera" ? "YS7 LIVE" : deviceOverlayState.type === "beidou" ? "BEIDOU TRACK" : "ELITECH CLOUD" }}</p>
              <h2>{{ deviceOverlayState.title }}</h2>
              <span>{{ deviceOverlayState.subtitle }}</span>
            </div>
            <button type="button" @click="closeDeviceOverlay">×</button>
          </header>
          <div class="tianshu-fulfillment-drawer__scan" aria-hidden="true" />
          <p v-if="deviceOverlayState.loading" class="tianshu-fulfillment-empty">正在同步设备数据...</p>
          <p v-else-if="deviceOverlayState.error" class="tianshu-device-panel__error">{{ deviceOverlayState.error }}</p>
          <template v-else>
            <div v-if="deviceOverlayState.type === 'camera'" class="tianshu-device-live">
              <div class="tianshu-device-live__screen">
                <video
                  v-if="deviceOverlayState.data?.live?.ys7_play_mode === 'hls'"
                  :src="deviceOverlayState.data.live.hls"
                  controls
                  autoplay
                  muted
                />
                <div v-else>
                  <b>直播地址已获取</b>
                  <span>EZUIKit 播放地址需由前端播放器 SDK 接管</span>
                </div>
              </div>
              <div class="tianshu-device-panel__kv">
                <span>模式</span><b>{{ deviceOverlayState.data?.live?.ys7_play_mode || "—" }}</b>
                <span>地址</span><b>{{ deviceOverlayState.data?.live?.hls || "—" }}</b>
                <span>云台</span><b>{{ deviceOverlayState.data?.live?.ys7_supports_ptz ? "支持" : "不支持/未知" }}</b>
              </div>
            </div>
            <div v-else-if="deviceOverlayState.type === 'beidou'" class="tianshu-device-track">
              <div class="tianshu-device-track__map">
                <span
                  v-for="(point, idx) in deviceTrackPreviewPoints"
                  :key="`track-point-${idx}`"
                  :style="{ left: `${point.x}%`, top: `${point.y}%` }"
                />
              </div>
              <div class="tianshu-device-panel__kv">
                <span>轨迹点</span><b>{{ deviceTrackRawPoints.length }}</b>
                <span>时间窗</span><b>最近 2 小时</b>
                <span>状态</span><b>{{ deviceTrackRawPoints.length ? "已返回轨迹" : "暂无轨迹点" }}</b>
              </div>
            </div>
            <div v-else class="tianshu-device-curve">
              <div class="tianshu-device-curve__chart">
                <i
                  v-for="(point, idx) in deviceCurvePreviewPoints"
                  :key="`curve-temp-${idx}`"
                  :style="{ left: `${point.x}%`, bottom: `${point.tempY}%` }"
                />
                <em
                  v-for="(point, idx) in deviceCurvePreviewPoints"
                  :key="`curve-hum-${idx}`"
                  :style="{ left: `${point.x}%`, bottom: `${point.humY}%` }"
                />
              </div>
              <div class="tianshu-device-panel__kv">
                <span>SN</span><b>{{ deviceOverlayState.data?.sn || "—" }}</b>
                <span>温度点</span><b>{{ deviceCurveRaw.temperatureList?.length || 0 }}</b>
                <span>湿度点</span><b>{{ deviceCurveRaw.humidityList?.length || 0 }}</b>
              </div>
            </div>
          </template>
        </aside>
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
  isTianshuAuthMissingError,
  todayYesterdayIso,
  TIANSHU_SELECTED_DISTRICT_KEY,
  prefetchTianshuInsightCaches,
  TIANSHU_CHART_QUERY_DISTRICT_KEY,
} from "@/api/tianshuInsights.js"
import { useTianshuOpsConsole } from "@/hooks/useTianshuOpsConsole.js"
import { useTianshuMockStream } from "@/hooks/useTianshuMockStream.js"
import MockToggleButton from "./MockToggleButton.vue"
import {
  startStaggeredPoll,
  TIANSHU_POLL_PERIOD_MS,
  TIANSHU_POLL_STAGGER,
} from "./composables/tianshuStaggeredPoll.js"

const KPI_TODAY = "/api/insights/business/kpi-summary?scope=today"
const COCKPIT_MAP_POINTS = "/api/insights/business/cockpit-customer-map-points"
const COCKPIT_FLYLINES = "/api/insights/business/cockpit-flylines"
const RISK_WARNING_OVERVIEW = "/api/insights/business/risk-warning-overview"
const FULFILLMENT_OVERVIEW = "/api/insights/business/fulfillment-overview"
const COLD_CHAIN_OVERVIEW = "/api/insights/business/cold-chain-overview"
const INDUSTRY_INSIGHTS_OVERVIEW = "/api/insights/business/industry-insights-overview"
const CITY_PROFILE_OVERVIEW = "/api/insights/business/city-profile-overview"
const DEVICE_BINDINGS = "/api/insights/business/device-bindings"
const DEVICE_BINDING_TIMEOUT_MS = 8000
const DEVICE_LINK_TIMEOUT_MS = 10000
const VIEW_OVERVIEW = "overview"
const VIEW_RISK_WARNING = "risk-warning"
const VIEW_FULFILLMENT = "fulfillment"
const VIEW_COLD_CHAIN = "cold-chain"
const VIEW_CITY_PROFILE = "city-profile"
const VIEW_INDUSTRY_INSIGHTS = "industry-insights"

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
const bottomMenuRef = ref(null)
/** 首屏入场：loading 结束后与地图错开淡入 */
const shellEnterReady = ref(false)
const activeView = ref(VIEW_OVERVIEW)
const DIRECTOR_STEPS = [
  { view: VIEW_OVERVIEW, menuIndex: "1", title: "经济概览", mode: "订单光柱", open: "overview" },
  { view: VIEW_FULFILLMENT, menuIndex: "2", title: "供应链履约", mode: "车次下钻", open: "fulfillment" },
  { view: VIEW_COLD_CHAIN, menuIndex: "3", title: "冷链运力", mode: "异常处置", open: "cold" },
  { view: VIEW_CITY_PROFILE, menuIndex: "4", title: "城市画像", mode: "风险密度", open: "city" },
  { view: VIEW_INDUSTRY_INSIGHTS, menuIndex: "5", title: "产业洞察", mode: "采购影响", open: "industry" },
  { view: VIEW_RISK_WARNING, menuIndex: "6", title: "风险预警", mode: "处置队列", open: "risk" },
]
const directorState = reactive({
  running: false,
  stepIndex: -1,
  phase: "待机",
})
let directorRunId = 0
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
  const g = orderHover.value?.gmv
  if (g == null || !Number.isFinite(Number(g))) return "¥0"
  return `¥${Number(g).toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`
})

const riskLoading = ref(false)
const riskError = ref("")
const riskData = reactive({
  date: "",
  kpis: {},
  risk_distribution: [],
  risk_points: [],
  latest_items: [],
  recommendations: [],
})
const RISK_MOCK_POINTS = [
  {
    role: "risk",
    risk_type: "return",
    risk_level: "high",
    address: "北京市朝阳区第一实验中学食堂",
    customer_name: "朝阳区第一实验中学",
    order_count: 1,
    gmv: 18420,
    lng: 116.486,
    lat: 39.921,
    order_id: 930001,
    order_sn: "OD-RISK-930001",
    description: "高金额退单待复核，需核对收货差异与账单冲销",
    created_at: 0,
  },
  {
    role: "risk",
    risk_type: "abnormal_order",
    risk_level: "medium",
    address: "北京市海淀区师大附中食堂",
    customer_name: "海淀区师大附中",
    order_count: 1,
    gmv: 8650,
    lng: 116.298,
    lat: 39.959,
    order_id: 930002,
    order_sn: "OD-RISK-930002",
    description: "异常订单未闭环，配送节点超过预警阈值",
    created_at: 0,
  },
  {
    role: "risk",
    risk_type: "alert",
    risk_level: "high",
    address: "北京市通州区城市副中心食堂",
    customer_name: "通州区城市副中心",
    order_count: 1,
    gmv: 0,
    lng: 116.656,
    lat: 39.91,
    order_id: 930003,
    order_sn: "ALERT-RISK-930003",
    description: "冷链温控告警持续 18 分钟，建议立即联系配送商复核",
    created_at: 0,
  },
  {
    role: "risk",
    risk_type: "abnormal_order",
    risk_level: "medium",
    address: "北京市大兴区开发区中心食堂",
    customer_name: "大兴区开发区中心食堂",
    order_count: 1,
    gmv: 12380,
    lng: 116.341,
    lat: 39.726,
    order_id: 930004,
    order_sn: "OD-RISK-930004",
    description: "补单链路待确认，存在重复配送风险",
    created_at: 0,
  },
  {
    role: "risk",
    risk_type: "return",
    risk_level: "high",
    address: "雄安新区容城县示范学校食堂",
    customer_name: "雄安容城示范学校",
    order_count: 1,
    gmv: 15260,
    lng: 115.873,
    lat: 39.052,
    order_id: 930005,
    order_sn: "OD-RISK-930005",
    description: "退单金额异常集中，需复核供应商批次与质检报告",
    created_at: 0,
  },
]
const riskKpis = computed(() => ({
  open_alerts: Number(riskData.kpis?.open_alerts) || 0,
  abnormal_orders: Number(riskData.kpis?.abnormal_orders) || 0,
  return_amount: Number(riskData.kpis?.return_amount) || 0,
  pending_count: Number(riskData.kpis?.pending_count) || 0,
  high_count: Number(riskData.kpis?.high_count) || 0,
  medium_count: Number(riskData.kpis?.medium_count) || 0,
  low_count: Number(riskData.kpis?.low_count) || 0,
  abnormal_amount: Number(riskData.kpis?.abnormal_amount) || 0,
}))
const riskDistribution = computed(() =>
  Array.isArray(riskData.risk_distribution) ? riskData.risk_distribution : [],
)
const riskLatestItems = computed(() =>
  Array.isArray(riskData.latest_items) ? riskData.latest_items : [],
)
const riskRecommendations = computed(() =>
  Array.isArray(riskData.recommendations) ? riskData.recommendations : [],
)
const riskDistributionMax = computed(() =>
  Math.max(1, ...riskDistribution.value.map((x) => Number(x.count) || 0)),
)
const riskMode = computed(() => activeSubModeByView[VIEW_RISK_WARNING] || "风险态势")
const riskPoints = computed(() => Array.isArray(riskData.risk_points) ? riskData.risk_points : [])
const riskMapPointsByMode = computed(() => {
  const pts = riskPoints.value
  if (riskMode.value === "风险光柱") return pts
  if (riskMode.value === "处置队列") {
    return pts.filter((p) => riskLevelText(p.risk_level) === "高" || String(p.description || "").includes("待"))
  }
  if (riskMode.value === "异常预警") {
    return pts.filter((p) => ["abnormal_order", "alert"].includes(String(p.risk_type || "").toLowerCase()))
  }
  return pts
})
const riskItemsByMode = computed(() => {
  if (riskMode.value === "处置队列") {
    return riskLatestItems.value.filter((item) => riskLevelText(item.level) === "高" || String(item.status || item.description || "").includes("待"))
  }
  if (riskMode.value === "异常预警") {
    return riskLatestItems.value.filter((item) => String(item.type || "").includes("异常") || String(item.type || "").includes("告警"))
  }
  return riskLatestItems.value
})
const riskModeStats = computed(() => {
  const k = riskKpis.value
  if (riskMode.value === "风险光柱") {
    return [
      { label: "风险点位", value: riskPoints.value.length, tone: "warn" },
      { label: "高风险", value: k.high_count, tone: k.high_count ? "danger" : "good" },
      { label: "中风险", value: k.medium_count, tone: k.medium_count ? "warn" : "good" },
    ]
  }
  if (riskMode.value === "处置队列") {
    return [
      { label: "待处置", value: k.pending_count, tone: k.pending_count ? "danger" : "good" },
      { label: "开放告警", value: k.open_alerts, tone: k.open_alerts ? "warn" : "good" },
      { label: "建议数", value: riskRecommendations.value.length, tone: "good" },
    ]
  }
  if (riskMode.value === "异常预警") {
    return [
      { label: "异常订单", value: k.abnormal_orders, tone: k.abnormal_orders ? "danger" : "good" },
      { label: "异常金额", value: `¥${compactMoney(k.abnormal_amount)}`, tone: k.abnormal_amount ? "warn" : "good" },
      { label: "退单金额", value: `¥${compactMoney(k.return_amount)}`, tone: k.return_amount ? "warn" : "good" },
    ]
  }
  return [
    { label: "待处置", value: k.pending_count, tone: k.pending_count ? "warn" : "good" },
    { label: "开放告警", value: k.open_alerts, tone: k.open_alerts ? "warn" : "good" },
    { label: "高风险", value: k.high_count, tone: k.high_count ? "danger" : "good" },
  ]
})
const riskPrimaryTitle = computed(() => {
  if (riskMode.value === "风险光柱") return "风险光柱点位"
  if (riskMode.value === "处置队列") return "处置优先队列"
  if (riskMode.value === "异常预警") return "异常预警队列"
  return "实时风险队列"
})
const riskSecondaryTitle = computed(() => {
  if (riskMode.value === "风险光柱") return "风险构成"
  if (riskMode.value === "处置队列") return "处置建议"
  if (riskMode.value === "异常预警") return "异常资金风险"
  return "资金风险"
})
const riskModeHint = computed(() => {
  if (riskMode.value === "风险光柱") return "地图展示所有风险光柱，突出点位等级、金额和业务对象"
  if (riskMode.value === "处置队列") return "优先展示高风险与待处置对象，适合调度现场闭环"
  if (riskMode.value === "异常预警") return "聚焦异常订单、开放告警、退单金额和补单风险"
  return "风险构成、风险点位、处置建议和实时队列统一态势"
})
const fulfillmentLoading = ref(false)
const fulfillmentError = ref("")
const fulfillmentDrawerOpen = ref(false)
const fulfillmentDrawerState = reactive({
  title: "",
  subtitle: "",
  conclusion: "",
  summaryCards: [],
  sections: [],
  deviceTarget: null,
})
const deviceBindingState = reactive({
  loading: false,
  error: "",
  data: null,
})
const deviceOverlayState = reactive({
  open: false,
  loading: false,
  type: "",
  title: "",
  subtitle: "",
  error: "",
  data: null,
})
const fulfillmentData = reactive({
  date: "",
  data_mode: "",
  summary: {},
  funnel: [],
  supplier_blocks: [],
  trips: [],
  in_transit: [],
  risk_events: [],
  map_points: [],
  orders_detail: [],
  allocations_detail: [],
})
const FULFILLMENT_MOCK_POINTS = [
  {
    role: "fulfillment",
    stage: "in_transit",
    address: "北京市朝阳区第一实验中学食堂",
    customer_name: "朝阳区第一实验中学",
    order_count: 1,
    gmv: 28600,
    lng: 116.486,
    lat: 39.921,
    order_id: 810001,
    order_sn: "OD-FUL-810001",
    trip_id: 7101,
    route_no: "京配-朝阳-01",
    status: "运输中",
    description: "京配-朝阳-01 · 第 2 站 · 预计 10:20 到达",
  },
  {
    role: "fulfillment",
    stage: "blocked",
    address: "北京市海淀区师大附中食堂",
    customer_name: "海淀区师大附中",
    order_count: 1,
    gmv: 19880,
    lng: 116.298,
    lat: 39.959,
    order_id: 810002,
    order_sn: "OD-FUL-810002",
    trip_id: 7102,
    route_no: "京配-海淀-02",
    status: "有阻塞",
    description: "京配-海淀-02 · 供应商未出库 3 条",
  },
  {
    role: "fulfillment",
    stage: "normal",
    address: "北京市通州区城市副中心食堂",
    customer_name: "通州区城市副中心",
    order_count: 1,
    gmv: 33600,
    lng: 116.656,
    lat: 39.91,
    order_id: 810003,
    order_sn: "OD-FUL-810003",
    trip_id: 7103,
    route_no: "京配-通州-03",
    status: "待发车",
    description: "京配-通州-03 · 已装车待发",
  },
  {
    role: "fulfillment",
    stage: "in_transit",
    address: "北京市大兴区开发区中心食堂",
    customer_name: "大兴开发区中心食堂",
    order_count: 1,
    gmv: 24650,
    lng: 116.341,
    lat: 39.726,
    order_id: 810004,
    order_sn: "OD-FUL-810004",
    trip_id: 7104,
    route_no: "京配-大兴-04",
    status: "运输中",
    description: "京配-大兴-04 · 冷链轨迹正常",
  },
]
const fulfillmentSummary = computed(() => fulfillmentData.summary || {})
const fulfillmentFunnel = computed(() => Array.isArray(fulfillmentData.funnel) ? fulfillmentData.funnel : [])
const fulfillmentSupplierBlocks = computed(() =>
  Array.isArray(fulfillmentData.supplier_blocks) ? fulfillmentData.supplier_blocks : [],
)
const fulfillmentTrips = computed(() => Array.isArray(fulfillmentData.trips) ? fulfillmentData.trips : [])
const fulfillmentInTransit = computed(() =>
  Array.isArray(fulfillmentData.in_transit) ? fulfillmentData.in_transit : [],
)
const fulfillmentRiskEvents = computed(() =>
  Array.isArray(fulfillmentData.risk_events) ? fulfillmentData.risk_events : [],
)
const fulfillmentFunnelMax = computed(() =>
  Math.max(1, ...fulfillmentFunnel.value.map((x) => Number(x.total || x.count) || 0)),
)
const fulfillmentBottomItems = ["履约闭环", "订单光柱", "履约热力", "车次下钻"]
const coldChainLoading = ref(false)
const coldChainError = ref("")
const coldChainData = reactive({
  date: "",
  data_mode: "",
  summary: {},
  vehicles: [],
  warehouses: [],
  events: [],
  map_points: [],
})
const COLD_CHAIN_MOCK_POINTS = [
  {
    role: "cold_chain",
    cold_type: "vehicle",
    stage: "moving",
    lng: 116.486,
    lat: 39.921,
    vehicle_id: 9101,
    customer_name: "京A·C8101",
    address: "朝阳冷链配送中心",
    description: "京A·C8101 · online · 刚刚",
    order_count: 1,
    gmv: 1,
    temperature: "3.8",
    humidity: "62",
    status: "online",
  },
  {
    role: "cold_chain",
    cold_type: "vehicle",
    stage: "alert",
    lng: 116.298,
    lat: 39.959,
    vehicle_id: 9102,
    customer_name: "京N·C9202",
    address: "海淀冷链配送中心",
    description: "京N·C9202 · offline · 18 分钟前",
    order_count: 1,
    gmv: 1,
    temperature: "9.6",
    humidity: "71",
    status: "offline",
  },
  {
    role: "cold_chain",
    cold_type: "warehouse",
    stage: "warehouse",
    lng: 116.455,
    lat: 39.905,
    warehouse_id: 9201,
    customer_name: "朝阳一号冷库",
    address: "北京市朝阳区冷链仓",
    description: "朝阳一号冷库 · 3.2℃ · RH 61%",
    order_count: 1,
    gmv: 1,
    temperature: "3.2",
    humidity: "61",
    status: "online",
  },
  {
    role: "cold_chain",
    cold_type: "warehouse",
    stage: "alert",
    lng: 116.315,
    lat: 39.962,
    warehouse_id: 9202,
    customer_name: "海淀校园冷库",
    address: "北京市海淀区冷链仓",
    description: "海淀校园冷库 · 10.4℃ · RH 78%",
    order_count: 1,
    gmv: 1,
    temperature: "10.4",
    humidity: "78",
    status: "online",
  },
]
const coldChainSummary = computed(() => coldChainData.summary || {})
const coldChainVehicles = computed(() => Array.isArray(coldChainData.vehicles) ? coldChainData.vehicles : [])
const coldChainWarehouses = computed(() => Array.isArray(coldChainData.warehouses) ? coldChainData.warehouses : [])
const coldChainEvents = computed(() => Array.isArray(coldChainData.events) ? coldChainData.events : [])
const coldChainBottomItems = ["冷链态势", "车辆轨迹", "仓温监控", "异常处置"]
const activeSubModeByView = reactive({
  [VIEW_OVERVIEW]: "全景态势",
  [VIEW_FULFILLMENT]: "履约闭环",
  [VIEW_COLD_CHAIN]: "冷链态势",
  [VIEW_CITY_PROFILE]: "城市画像",
  [VIEW_INDUSTRY_INSIGHTS]: "产业态势",
  [VIEW_RISK_WARNING]: "风险态势",
})
const fulfillmentMode = computed(() => activeSubModeByView[VIEW_FULFILLMENT] || "履约闭环")
const fulfillmentMapPointsByMode = computed(() => {
  const pts = Array.isArray(fulfillmentData.map_points) ? fulfillmentData.map_points : []
  if (fulfillmentMode.value === "履约热力") {
    return pts.filter((p) => {
      const stage = String(p.stage || "").toLowerCase()
      const status = String(p.status || "")
      return stage === "blocked" || status.includes("阻塞") || status.includes("异常") || status.includes("未")
    })
  }
  if (fulfillmentMode.value === "车次下钻") {
    return pts.filter((p) => p.trip_id != null && p.trip_id !== "")
  }
  return pts
})
const fulfillmentModeTrips = computed(() => {
  if (fulfillmentMode.value === "履约热力") {
    return fulfillmentTrips.value.filter((item) => fulfillmentTripClass(item) === "is-blocked" || Number(item.risk_count || item.blocked_count || item.not_loaded_count) > 0)
  }
  if (fulfillmentMode.value === "车次下钻") {
    return fulfillmentTrips.value
  }
  return fulfillmentTrips.value
})
const fulfillmentPrimaryTitle = computed(() => {
  if (fulfillmentMode.value === "订单光柱") return "订单/站点光柱"
  if (fulfillmentMode.value === "履约热力") return "履约阻塞热力"
  if (fulfillmentMode.value === "车次下钻") return "车次下钻队列"
  return "实时车次队列"
})
const fulfillmentModeHint = computed(() => {
  if (fulfillmentMode.value === "订单光柱") return "地图聚焦订单与站点履约覆盖，适合看区域分布"
  if (fulfillmentMode.value === "履约热力") return "地图只突出阻塞、未出库、未分检、未随车等压力点"
  if (fulfillmentMode.value === "车次下钻") return "地图聚焦已绑定车次点位，右侧强化调度队列"
  return "订单、车次、漏斗、阻塞和风险全量闭环展示"
})
const coldChainMode = computed(() => activeSubModeByView[VIEW_COLD_CHAIN] || "冷链态势")
const coldChainMapPointsByMode = computed(() => {
  const pts = Array.isArray(coldChainData.map_points) ? coldChainData.map_points : []
  if (coldChainMode.value === "车辆轨迹") {
    return pts.filter((p) => String(p.cold_type || "").toLowerCase() === "vehicle")
  }
  if (coldChainMode.value === "仓温监控") {
    return pts.filter((p) => String(p.cold_type || "").toLowerCase() === "warehouse")
  }
  if (coldChainMode.value === "异常处置") {
    return pts.filter((p) => String(p.stage || "").toLowerCase() === "alert")
  }
  return pts
})
const coldChainModeVehicles = computed(() => {
  if (coldChainMode.value === "异常处置") {
    return coldChainVehicles.value.filter((item) => item.online_status !== "online" || !item.coordinate_valid)
  }
  return coldChainVehicles.value
})
const coldChainModeWarehouses = computed(() => {
  if (coldChainMode.value === "异常处置") {
    return coldChainWarehouses.value.filter((item) => coldWarehouseAlert(item))
  }
  return coldChainWarehouses.value
})
const coldChainAbnormalVehicles = computed(() =>
  coldChainVehicles.value.filter((item) => item.online_status !== "online" || !item.coordinate_valid),
)
const coldChainAbnormalWarehouses = computed(() =>
  coldChainWarehouses.value.filter((item) => coldWarehouseAlert(item)),
)
const coldChainModeStats = computed(() => {
  const s = coldChainSummary.value
  if (coldChainMode.value === "车辆轨迹") {
    return [
      { label: "在线车辆", value: `${s.online_vehicles || 0}/${s.vehicles || 0}`, tone: "good" },
      { label: "轨迹异常", value: coldChainAbnormalVehicles.value.length, tone: coldChainAbnormalVehicles.value.length ? "warn" : "good" },
      { label: "无定位", value: s.unlocated_vehicles || 0, tone: s.unlocated_vehicles ? "danger" : "good" },
    ]
  }
  if (coldChainMode.value === "仓温监控") {
    return [
      { label: "冷库数", value: s.warehouses || 0, tone: "good" },
      { label: "温控在线", value: s.temperature_online || 0, tone: "good" },
      { label: "仓温异常", value: coldChainAbnormalWarehouses.value.length, tone: coldChainAbnormalWarehouses.value.length ? "danger" : "good" },
    ]
  }
  if (coldChainMode.value === "异常处置") {
    return [
      { label: "异常事件", value: coldChainEvents.value.length, tone: coldChainEvents.value.length ? "danger" : "good" },
      { label: "异常车辆", value: coldChainAbnormalVehicles.value.length, tone: coldChainAbnormalVehicles.value.length ? "warn" : "good" },
      { label: "异常冷库", value: coldChainAbnormalWarehouses.value.length, tone: coldChainAbnormalWarehouses.value.length ? "danger" : "good" },
    ]
  }
  return [
    { label: "车辆", value: s.vehicles || 0, tone: "good" },
    { label: "冷库", value: s.warehouses || 0, tone: "good" },
    { label: "异常", value: s.temperature_alerts || 0, tone: s.temperature_alerts ? "warn" : "good" },
  ]
})
const coldChainPrimaryTitle = computed(() => {
  if (coldChainMode.value === "车辆轨迹") return "车辆轨迹队列"
  if (coldChainMode.value === "仓温监控") return "仓库温控队列"
  if (coldChainMode.value === "异常处置") return "异常处置队列"
  return "冷链车辆队列"
})
const coldChainSecondaryTitle = computed(() => {
  if (coldChainMode.value === "车辆轨迹") return "轨迹异常提示"
  if (coldChainMode.value === "仓温监控") return "温湿度异常冷库"
  if (coldChainMode.value === "异常处置") return "待处置对象"
  return "冷库设备队列"
})
const coldChainSecondaryCode = computed(() => {
  if (coldChainMode.value === "车辆轨迹") return "TRACK-RISK"
  if (coldChainMode.value === "仓温监控") return "TEMP-RISK"
  if (coldChainMode.value === "异常处置") return "DISPATCH"
  return "WAREHOUSE"
})
const coldChainSecondaryItems = computed(() => {
  if (coldChainMode.value === "车辆轨迹") return coldChainAbnormalVehicles.value
  if (coldChainMode.value === "仓温监控") return coldChainAbnormalWarehouses.value
  if (coldChainMode.value === "异常处置") return coldChainEvents.value
  return coldChainWarehouses.value
})
const coldChainModeHint = computed(() => {
  if (coldChainMode.value === "车辆轨迹") return "地图仅显示冷链车辆光柱与调度飞线"
  if (coldChainMode.value === "仓温监控") return "地图聚焦冷库/仓库温湿度点位"
  if (coldChainMode.value === "异常处置") return "地图只保留温控异常、离线和无定位对象"
  return "车辆、仓库、异常点位全量展示"
})
const industryLoading = ref(false)
const industryError = ref("")
const industryData = reactive({
  date: "",
  data_mode: "",
  summary: {},
  category_mix: [],
  goods_rank: [],
  forecast_items: [],
  price_series: [],
  impact_items: [],
  map_points: [],
})
const industrySummary = computed(() => industryData.summary || {})
const industryCategories = computed(() => Array.isArray(industryData.category_mix) ? industryData.category_mix : [])
const industryGoods = computed(() => Array.isArray(industryData.goods_rank) ? industryData.goods_rank : [])
const industryForecasts = computed(() => Array.isArray(industryData.forecast_items) ? industryData.forecast_items : [])
const industryImpacts = computed(() => Array.isArray(industryData.impact_items) ? industryData.impact_items : [])
const industryBottomItems = ["产业态势", "价格脉冲", "预测曲线", "采购影响"]
const industryMode = computed(() => activeSubModeByView[VIEW_INDUSTRY_INSIGHTS] || "产业态势")
const industryVolatileForecasts = computed(() =>
  industryForecasts.value.filter((item) => Math.abs(Number(item.change_pct) || 0) >= 5),
)
const industryModeForecasts = computed(() => {
  if (industryMode.value === "价格脉冲") return industryVolatileForecasts.value.length ? industryVolatileForecasts.value : industryForecasts.value
  if (industryMode.value === "采购影响") {
    const targets = new Set(industryImpacts.value.map((item) => item.target))
    return industryForecasts.value.filter((item) => targets.has(item.product_name))
  }
  return industryForecasts.value
})
const industryModeGoods = computed(() => {
  if (industryMode.value === "采购影响") {
    const targets = new Set(industryImpacts.value.map((item) => item.target))
    return industryGoods.value.filter((item) => targets.has(item.goods_name) || [...targets].some((target) => item.goods_name?.includes(target)))
  }
  if (industryMode.value === "价格脉冲") {
    const volatile = new Set(industryVolatileForecasts.value.map((item) => item.product_name))
    return industryGoods.value.filter((item) => volatile.has(item.goods_name) || Math.abs(Number(item.change_pct) || 0) >= 5)
  }
  return industryGoods.value
})
const industryMapPointsByMode = computed(() => {
  const pts = Array.isArray(industryData.map_points) ? industryData.map_points : []
  if (industryMode.value === "价格脉冲") {
    return pts.filter((p) => String(p.stage || "").toLowerCase() === "volatile" || Math.abs(Number(p.change_pct) || 0) >= 5)
  }
  if (industryMode.value === "预测曲线") {
    return pts.filter((p) => String(p.industry_type || "").toLowerCase() === "forecast" || p.forecast_price != null)
  }
  if (industryMode.value === "采购影响") {
    const targets = new Set(industryImpacts.value.map((item) => item.target))
    return pts.filter((p) => targets.has(p.product_name) || targets.has(p.customer_name))
  }
  return pts
})
const industryModeStats = computed(() => {
  const s = industrySummary.value
  if (industryMode.value === "价格脉冲") {
    return [
      { label: "波动品种", value: s.volatile_products || industryVolatileForecasts.value.length, tone: "warn" },
      { label: "最高波动", value: `${Math.max(0, ...industryForecasts.value.map((item) => Math.abs(Number(item.change_pct) || 0))).toFixed(1)}%`, tone: "danger" },
      { label: "监测品类", value: s.monitored_categories || industryCategories.value.length, tone: "good" },
    ]
  }
  if (industryMode.value === "预测曲线") {
    return [
      { label: "预测可用", value: s.forecast_usable || industryForecasts.value.length, tone: "good" },
      { label: "行情样本", value: industryData.price_series.length, tone: "good" },
      { label: "平均置信", value: `${industryAvgConfidence.value}%`, tone: "good" },
    ]
  }
  if (industryMode.value === "采购影响") {
    return [
      { label: "影响提示", value: industryImpacts.value.length, tone: industryImpacts.value.length ? "warn" : "good" },
      { label: "关联商品", value: industryModeGoods.value.length || industryGoods.value.length, tone: "good" },
      { label: "报价商品", value: s.quote_count || 0, tone: "good" },
    ]
  }
  return [
    { label: "监测品类", value: s.monitored_categories || industryCategories.value.length, tone: "good" },
    { label: "预测可用", value: s.forecast_usable || industryForecasts.value.length, tone: "good" },
    { label: "热销", value: s.hot_goods || "—", tone: "good" },
  ]
})
const industryAvgConfidence = computed(() => {
  const vals = industryForecasts.value.map((item) => Number(item.confidence)).filter(Number.isFinite)
  if (!vals.length) return 0
  return Math.round(vals.reduce((sum, n) => sum + n, 0) / vals.length)
})
const industryPrimaryTitle = computed(() => {
  if (industryMode.value === "价格脉冲") return "价格脉冲品种"
  if (industryMode.value === "预测曲线") return "重点品种预测"
  if (industryMode.value === "采购影响") return "采购影响清单"
  return "平台热销商品"
})
const industrySecondaryTitle = computed(() => {
  if (industryMode.value === "价格脉冲") return "波动影响"
  if (industryMode.value === "预测曲线") return "全国行情样本"
  if (industryMode.value === "采购影响") return "关联业务商品"
  return "价格波动影响"
})
const industrySecondaryCode = computed(() => {
  if (industryMode.value === "价格脉冲") return "PULSE"
  if (industryMode.value === "预测曲线") return "NATION"
  if (industryMode.value === "采购影响") return "BUSINESS"
  return "IMPACT"
})
const industryModeHint = computed(() => {
  if (industryMode.value === "价格脉冲") return "地图聚焦涨跌幅超过阈值的品种，识别采购成本波动来源"
  if (industryMode.value === "预测曲线") return "地图和面板聚焦预测可用品种、置信度和全国行情样本"
  if (industryMode.value === "采购影响") return "把价格波动接回平台订单、热销商品和供应商报价影响"
  return "全国行情、价格预测、平台品类和商品排行统一联动"
})
const cityProfileLoading = ref(false)
const cityProfileError = ref("")
const cityProfileData = reactive({
  date: "",
  data_mode: "",
  summary: {},
  district_profiles: [],
  growth_districts: [],
  risk_districts: [],
  thin_areas: [],
  map_points: [],
})
const cityProfileSummary = computed(() => cityProfileData.summary || {})
const cityDistricts = computed(() => Array.isArray(cityProfileData.district_profiles) ? cityProfileData.district_profiles : [])
const cityGrowthDistricts = computed(() => Array.isArray(cityProfileData.growth_districts) ? cityProfileData.growth_districts : [])
const cityRiskDistricts = computed(() => Array.isArray(cityProfileData.risk_districts) ? cityProfileData.risk_districts : [])
const cityThinAreas = computed(() => Array.isArray(cityProfileData.thin_areas) ? cityProfileData.thin_areas : [])
const cityBottomItems = ["城市画像", "区县热力", "客户覆盖", "风险密度"]
const cityProfileMode = computed(() => activeSubModeByView[VIEW_CITY_PROFILE] || "城市画像")
const cityModeDistricts = computed(() => {
  if (cityProfileMode.value === "区县热力") {
    return [...cityDistricts.value].sort((a, b) => (Number(b.gmv) || 0) - (Number(a.gmv) || 0))
  }
  if (cityProfileMode.value === "客户覆盖") {
    return cityThinAreas.value.length ? cityThinAreas.value : [...cityDistricts.value].sort((a, b) => (Number(a.client_count) || 0) - (Number(b.client_count) || 0))
  }
  if (cityProfileMode.value === "风险密度") {
    return cityRiskDistricts.value.length ? cityRiskDistricts.value : cityDistricts.value.filter((item) => Number(item.risk_count) > 0)
  }
  return cityDistricts.value
})
const cityMapPointsByMode = computed(() => {
  const pts = Array.isArray(cityProfileData.map_points) ? cityProfileData.map_points : []
  if (cityProfileMode.value === "风险密度") {
    return pts.filter((p) => String(p.stage || "").toLowerCase() === "risk" || Number(p.risk_count) > 0)
  }
  if (cityProfileMode.value === "客户覆盖") {
    const thinNames = new Set(cityThinAreas.value.map((item) => item.district_name))
    return pts.filter((p) => thinNames.has(p.district_name) || Number(p.client_count || p.canteen_count) > 0)
  }
  return pts
})
const cityModeStats = computed(() => {
  const s = cityProfileSummary.value
  if (cityProfileMode.value === "区县热力") {
    return [
      { label: "覆盖区县", value: s.district_cover_count || cityDistricts.value.length, tone: "good" },
      { label: "订单", value: s.total_orders || 0, tone: "good" },
      { label: "GMV", value: `¥${compactMoney(s.total_gmv)}`, tone: "good" },
    ]
  }
  if (cityProfileMode.value === "客户覆盖") {
    return [
      { label: "活跃客户", value: s.active_clients || 0, tone: "good" },
      { label: "食堂", value: s.active_canteens || 0, tone: "good" },
      { label: "薄弱区", value: cityThinAreas.value.length, tone: cityThinAreas.value.length ? "warn" : "good" },
    ]
  }
  if (cityProfileMode.value === "风险密度") {
    return [
      { label: "风险事件", value: s.risk_events || 0, tone: s.risk_events ? "danger" : "good" },
      { label: "风险区县", value: cityRiskDistricts.value.length, tone: cityRiskDistricts.value.length ? "warn" : "good" },
      { label: "最高风险", value: Math.max(0, ...cityRiskDistricts.value.map((item) => Number(item.risk_count) || 0)), tone: "danger" },
    ]
  }
  return [
    { label: "覆盖区县", value: s.district_cover_count || cityDistricts.value.length, tone: "good" },
    { label: "活跃食堂", value: s.active_canteens || 0, tone: "good" },
    { label: "风险", value: s.risk_events || 0, tone: s.risk_events ? "warn" : "good" },
  ]
})
const cityPrimaryTitle = computed(() => {
  if (cityProfileMode.value === "区县热力") return "区县经营热力"
  if (cityProfileMode.value === "客户覆盖") return "客户/食堂覆盖"
  if (cityProfileMode.value === "风险密度") return "区域风险密度"
  return "区域履约表现"
})
const citySecondaryTitle = computed(() => {
  if (cityProfileMode.value === "区县热力") return "增长区县"
  if (cityProfileMode.value === "客户覆盖") return "覆盖薄弱区"
  if (cityProfileMode.value === "风险密度") return "高风险区县"
  return "区域风险密度"
})
const citySecondaryCode = computed(() => {
  if (cityProfileMode.value === "区县热力") return "GROWTH"
  if (cityProfileMode.value === "客户覆盖") return "THIN"
  if (cityProfileMode.value === "风险密度") return "RISK"
  return "RISK"
})
const citySecondaryItems = computed(() => {
  if (cityProfileMode.value === "区县热力") return cityGrowthDistricts.value
  if (cityProfileMode.value === "客户覆盖") return cityThinAreas.value
  if (cityProfileMode.value === "风险密度") return cityRiskDistricts.value
  return cityRiskDistricts.value
})
const cityModeHint = computed(() => {
  if (cityProfileMode.value === "区县热力") return "地图聚焦区县 GMV、订单和经营强度，适合看城市热区"
  if (cityProfileMode.value === "客户覆盖") return "地图突出客户/食堂覆盖和薄弱区，适合制定拓展计划"
  if (cityProfileMode.value === "风险密度") return "地图只突出风险区县、异常密度和履约压力"
  return "全市区县经营、客户覆盖、履约表现和风险密度统一画像"
})
const bottomTrayItems = computed(() =>
  activeView.value === VIEW_COLD_CHAIN
    ? coldChainBottomItems
    : activeView.value === VIEW_INDUSTRY_INSIGHTS
    ? industryBottomItems
    : activeView.value === VIEW_CITY_PROFILE
    ? cityBottomItems
    : activeView.value === VIEW_FULFILLMENT
    ? fulfillmentBottomItems
    : activeView.value === VIEW_RISK_WARNING
    ? ["风险态势", "风险光柱", "处置队列", "异常预警"]
    : ["全景态势", "订单光柱", "履约热力", "异常预警"],
)
const bottomTrayActive = computed(() =>
  activeSubModeByView[activeView.value] || bottomTrayItems.value[0] || "全景态势",
)
const drawerModeItems = computed(() =>
  [VIEW_FULFILLMENT, VIEW_COLD_CHAIN, VIEW_CITY_PROFILE, VIEW_INDUSTRY_INSIGHTS, VIEW_RISK_WARNING].includes(activeView.value)
    ? bottomTrayItems.value
    : [],
)
const directorCurrentTitle = computed(() => {
  const step = DIRECTOR_STEPS[directorState.stepIndex]
  return step ? step.title : "自动演示模式"
})
const directorProgress = computed(() => {
  if (!directorState.running) return 0
  return Math.min(100, Math.max(8, ((directorState.stepIndex + 1) / DIRECTOR_STEPS.length) * 100))
})
const opsLiveGmvYuan = computed(() => {
  const live = Number(opsConsole.liveGmv.value)
  const fallback = Number(state.totalView?.[0]?.value)
  const value = Number.isFinite(live) && (live > 0 || !Number.isFinite(fallback) || fallback <= 0) ? live : fallback
  if (!Number.isFinite(value)) return "—"
  return Math.round(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 })
})
const opsLiveOrderCountText = computed(() => {
  const live = Number(opsConsole.liveOrderCount.value)
  const fallback = Number(state.totalView?.[1]?.value)
  const value = Number.isFinite(live) && (live > 0 || !Number.isFinite(fallback) || fallback <= 0) ? live : fallback
  if (!Number.isFinite(value)) return "—"
  return Math.round(value).toLocaleString("zh-CN", { maximumFractionDigits: 0 })
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
const mockStream = useTianshuMockStream()
mockStream.bindOpsConsole(opsConsole)

async function toggleMockStream() {
  if (mockStream.isRunning()) {
    mockStream.stop()
  } else {
    mockStream.start()
  }
  lastOrderPillarsFingerprint = undefined
  // loadFlylines 依赖 lastRealDeliveries（由 loadTodayOrderPillars 写入），需顺序执行
  await loadTodayOrderPillars()
  await loadFlylines()
}

function onPageVisibility() {
  if (document.visibilityState === "hidden" && mockStream.isRunning()) {
    mockStream.stop()
    lastOrderPillarsFingerprint = undefined
    void loadTodayOrderPillars()
    void loadFlylines()
  }
}

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
  if (activeView.value === VIEW_RISK_WARNING) {
    lastRiskFingerprint = undefined
    void loadRiskWarningOverview({ force: true })
  } else if (activeView.value === VIEW_FULFILLMENT) {
    lastFulfillmentFingerprint = undefined
    void loadFulfillmentOverview({ force: true })
  } else if (activeView.value === VIEW_COLD_CHAIN) {
    lastColdChainFingerprint = undefined
    void loadColdChainOverview({ force: true })
  } else if (activeView.value === VIEW_INDUSTRY_INSIGHTS) {
    lastIndustryFingerprint = undefined
    void loadIndustryInsightsOverview({ force: true })
  } else if (activeView.value === VIEW_CITY_PROFILE) {
    lastCityProfileFingerprint = undefined
    void loadCityProfileOverview({ force: true })
  }
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
  orderHover.value = {
    role: String(payload.role || "").toLowerCase(),
    risk_type: payload.risk_type,
    risk_level: payload.risk_level,
    stage: payload.stage,
    cold_type: payload.cold_type,
    industry_type: payload.industry_type,
    product_name: payload.product_name,
    category_name: payload.category_name,
    change_pct: payload.change_pct,
    forecast_price: payload.forecast_price,
    confidence: payload.confidence,
    profile_type: payload.profile_type,
    district_name: payload.district_name,
    client_count: payload.client_count,
    canteen_count: payload.canteen_count,
    risk_count: payload.risk_count,
    vehicle_id: payload.vehicle_id,
    warehouse_id: payload.warehouse_id,
    temperature: payload.temperature,
    humidity: payload.humidity,
    trip_id: payload.trip_id,
    route_no: payload.route_no,
    status: payload.status,
    description: String(payload.description ?? "").trim(),
    order_sn: String(payload.order_sn ?? "").trim(),
    order_id: payload.order_id,
    address: String(payload.address ?? "").trim() || "—",
    customer_name: String(payload.customer_name ?? "").trim() || "—",
    order_count: Number(payload.order_count) || 0,
    gmv: Number(payload.gmv) || 0,
  }
}

function riskTypeText(type) {
  const t = String(type || "").toLowerCase()
  if (t === "return") return "退单"
  if (t === "abnormal_order") return "异常订单"
  if (t === "alert") return "开放告警"
  return "预警"
}

function riskLevelText(level) {
  const t = String(level || "").toLowerCase()
  if (t === "high" || t === "高") return "高"
  if (t === "low" || t === "低") return "低"
  return "中"
}

function riskLevelClass(level) {
  const t = riskLevelText(level)
  if (t === "高") return "high"
  if (t === "低") return "low"
  return "medium"
}

function riskBarWidth(count) {
  const n = Number(count) || 0
  return Math.max(6, Math.round((n / riskDistributionMax.value) * 100))
}

function compactMoney(v) {
  const n = Number(v) || 0
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toLocaleString("zh-CN", { maximumFractionDigits: 0 })
}

function formatRiskTime(ts) {
  const n = Number(ts)
  if (!Number.isFinite(n) || n <= 0) return "—"
  const d = new Date(n * 1000)
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

function buildRiskMockData(reason = "") {
  const now = Math.floor(Date.now() / 1000)
  const points = RISK_MOCK_POINTS.map((p, idx) => ({
    ...p,
    created_at: now - idx * 420,
  }))
  return {
    date: clock.date || new Date().toISOString().slice(0, 10),
    kpis: {
      open_alerts: 2,
      abnormal_orders: 2,
      return_amount: 33680,
      pending_count: points.length,
      high_count: 3,
      medium_count: 2,
      low_count: 0,
      abnormal_amount: 21030,
    },
    risk_distribution: [
      { key: "alert", label: "开放告警", count: 2 },
      { key: "return", label: "退单风险", count: 2 },
      { key: "abnormal_order", label: "异常订单", count: 2 },
      { key: "delivery", label: "配送异常", count: 1 },
    ],
    risk_points: points,
    latest_items: points.map((p, idx) => ({
      id: `mock-risk:${idx}`,
      type: riskTypeText(p.risk_type),
      level: riskLevelText(p.risk_level),
      status: "待处置",
      order_id: p.order_id,
      order_sn: p.order_sn,
      customer_name: p.customer_name,
      amount: p.gmv,
      description: p.description,
      created_at: p.created_at,
    })),
    recommendations: [
      {
        title: "高风险优先闭环",
        content: "朝阳与雄安退单金额较高，建议先核对质检报告、收货差异和账单冲销。",
      },
      {
        title: "冷链告警快处",
        content: "通州冷链温控告警需 30 分钟内联系配送商复核，避免批量投诉扩大。",
      },
      {
        title: "补单风险复核",
        content: "大兴补单链路存在重复配送风险，建议锁定同地址同品类订单做去重。",
      },
    ],
    mock_reason: reason,
  }
}

function applyRiskPayload(payload) {
  riskData.date = payload?.date || ""
  riskData.kpis = payload?.kpis || {}
  riskData.risk_distribution = Array.isArray(payload?.risk_distribution) ? payload.risk_distribution : []
  riskData.risk_points = Array.isArray(payload?.risk_points) ? payload.risk_points : []
  riskData.latest_items = Array.isArray(payload?.latest_items) ? payload.latest_items : []
  riskData.recommendations = Array.isArray(payload?.recommendations) ? payload.recommendations : []
}

function formatPct(v) {
  const n = Number(v) || 0
  return `${n.toLocaleString("zh-CN", { maximumFractionDigits: 1 })}%`
}

function fulfillmentStageText(stage) {
  const s = String(stage || "").toLowerCase()
  if (s === "blocked") return "阻塞节点"
  if (s === "in_transit") return "在途站点"
  return "履约站点"
}

function fulfillmentTripClass(item) {
  const status = String(item?.status || "")
  if (status.includes("阻塞")) return "is-blocked"
  if (status.includes("运输")) return "is-moving"
  if (status.includes("完成")) return "is-done"
  return "is-pending"
}

function fulfillmentFunnelWidth(item) {
  const n = Number(item?.count) || 0
  return Math.max(8, Math.round((n / fulfillmentFunnelMax.value) * 100))
}

function fulfillmentRows(rows, mapper) {
  return (Array.isArray(rows) ? rows : []).map(mapper)
}

function fulfillmentOrderRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    订单号: row.order_no || row.order_sn || "—",
    客户: row.client_name || row.customer_name || row.canteen_name || "—",
    配送日: row.expected_delivery_date || "—",
    配送窗口: row.expected_delivery_slot || "—",
    配送商: row.delivery_name || "—",
    状态: row.status || "—",
    金额: row.amount != null ? `¥${formatMoney(row.amount)}` : "—",
    车次: row.route_no || "暂未绑定",
  }))
}

function fulfillmentAllocationRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    分单号: row.allocation_no || `A${row.allocation_id || ""}`,
    订单号: row.order_no || "—",
    供应商: row.supplier_name || "—",
    数量: row.quantity != null ? row.quantity : "—",
    出库: row.shipment_status || "—",
    分检: row.sort_status || "—",
    装车: row.load_status || "—",
    车次: row.route_no || "暂未绑定",
    问题: row.reason || row.business_status || "—",
  }))
}

function fulfillmentTripRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    车次号: row.route_no || "—",
    状态: row.status || "—",
    配送商: row.delivery_name || "—",
    车牌: row.vehicle_no || "未定车",
    司机: row.driver_name || "未填司机",
    站点: `${row.stop_count || 0} 站`,
    里程: row.distance_km != null ? `${row.distance_km}km` : "—",
    用时: row.duration_minutes ? `${row.duration_minutes}分钟` : "—",
    阻塞: `${row.blocked_count || 0} 条`,
    未随车: `${row.not_loaded_count || 0} 条`,
  }))
}

function fulfillmentStopRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    顺序: `第 ${row.sequence || "—"} 站`,
    订单号: row.order_no || "—",
    客户: row.canteen_name || row.client_name || "—",
    窗口: row.expected_delivery_slot || "—",
    到达: row.planned_arrive_time || "—",
    状态: row.status || "—",
    地址: row.address || "—",
    异常: row.affected ? "是" : "否",
  }))
}

function buildFulfillmentMockData(reason = "") {
  const trips = [
    {
      id: 7101,
      route_no: "京配-朝阳-01",
      status: "运输中",
      delivery_name: "京东鲜配朝阳中心",
      vehicle_no: "京A·F8101",
      driver_name: "张师傅",
      departure_time: "08:30",
      ready_count: 18,
      blocked_count: 0,
      not_loaded_count: 0,
      stop_count: 6,
      affected_stop_count: 0,
      distance_km: 42.6,
      duration_minutes: 128,
      risk_count: 0,
      stops: [
        { sequence: 1, order_no: "OD-FUL-810011", canteen_name: "朝阳实验小学", expected_delivery_slot: "09:00-10:00", planned_arrive_time: "09:18", status: "已送达" },
        { sequence: 2, order_no: "OD-FUL-810001", canteen_name: "朝阳区第一实验中学", expected_delivery_slot: "10:00-11:00", planned_arrive_time: "10:20", status: "运输中" },
      ],
    },
    {
      id: 7102,
      route_no: "京配-海淀-02",
      status: "有阻塞",
      delivery_name: "海淀校园配送中心",
      vehicle_no: "京N·H9202",
      driver_name: "李师傅",
      departure_time: "09:10",
      ready_count: 11,
      blocked_count: 3,
      not_loaded_count: 1,
      stop_count: 5,
      affected_stop_count: 2,
      distance_km: 36.2,
      duration_minutes: 116,
      risk_count: 2,
      stops: [
        { sequence: 1, order_no: "OD-FUL-810002", canteen_name: "海淀区师大附中", expected_delivery_slot: "10:00-11:30", planned_arrive_time: "10:45", status: "有阻塞" },
      ],
      risk_alerts: ["供应商未出库 3 条，影响 2 个站点", "北斗定位 18 分钟未刷新"],
    },
    {
      id: 7103,
      route_no: "京配-通州-03",
      status: "待发车",
      delivery_name: "通州城市副中心配送",
      vehicle_no: "京Q·T3303",
      driver_name: "王师傅",
      departure_time: "10:30",
      ready_count: 22,
      blocked_count: 0,
      not_loaded_count: 0,
      stop_count: 7,
      affected_stop_count: 0,
      distance_km: 51.9,
      duration_minutes: 154,
      risk_count: 0,
      stops: [{ sequence: 1, order_no: "OD-FUL-810003", canteen_name: "通州区城市副中心", expected_delivery_slot: "11:00-12:00", planned_arrive_time: "11:22", status: "待发车" }],
    },
  ]
  const orders = FULFILLMENT_MOCK_POINTS.map((p) => ({
    order_id: p.order_id,
    order_no: p.order_sn,
    client_name: p.customer_name,
    canteen_name: p.customer_name,
    delivery_name: trips.find((t) => t.id === p.trip_id)?.delivery_name || "配送商",
    status: p.status,
    amount: p.gmv,
    route_no: p.route_no,
    trip_id: p.trip_id,
  }))
  const allocations = [
    { allocation_id: 1, allocation_no: "OD-FUL-810002-A1", order_no: "OD-FUL-810002", supplier_name: "北菜源供应链", shipment_status: "未出库", sort_status: "未分检", load_status: "未进入车次", business_status: "未出库", reason: "供货商尚未完成出库登记" },
    { allocation_id: 2, allocation_no: "OD-FUL-810002-A2", order_no: "OD-FUL-810002", supplier_name: "北菜源供应链", shipment_status: "已出库", sort_status: "未分检", load_status: "未进入车次", business_status: "未分检", reason: "配送商分检端尚未扫码确认" },
    { allocation_id: 3, allocation_no: "OD-FUL-810002-A3", order_no: "OD-FUL-810002", supplier_name: "华鲜直采", shipment_status: "已出库", sort_status: "已分检", load_status: "滞留未装", business_status: "未随车", reason: "现场复核质量问题，暂缓装车" },
  ]
  return {
    date: clock.date || new Date().toISOString().slice(0, 10),
    data_mode: "mock",
    mock_reason: reason,
    summary: {
      today_orders: 42,
      total_allocations: 156,
      pending_trips: 2,
      in_transit_trips: 2,
      arrived_orders: 18,
      blocked_allocations: 6,
      not_loaded: 1,
      risk_count: 8,
      sort_rate: 86.5,
      load_rate: 78.2,
      arrival_rate: 42.9,
      health_score: 82,
    },
    funnel: [
      { key: "orders", label: "今日订单", count: 42, total: 42, percent: 100 },
      { key: "allocated", label: "已分单", count: 42, total: 42, percent: 100 },
      { key: "shipped", label: "已出库", count: 132, total: 156, percent: 84.6 },
      { key: "sorted", label: "已分检", count: 135, total: 156, percent: 86.5 },
      { key: "loaded", label: "已装车", count: 122, total: 156, percent: 78.2 },
      { key: "departed", label: "已发车", count: 4, total: 6, percent: 66.7 },
      { key: "arrived", label: "已送达", count: 18, total: 42, percent: 42.9 },
    ],
    supplier_blocks: [
      { supplier_id: 1, supplier_name: "北菜源供应链", not_shipped: 3, not_sorted: 2, not_loaded: 0, blocked_count: 5, affected_orders: 3, affected_clients: ["海淀区师大附中", "清华附小"] },
      { supplier_id: 2, supplier_name: "华鲜直采", not_shipped: 0, not_sorted: 0, not_loaded: 1, blocked_count: 1, affected_orders: 1, affected_clients: ["海淀区师大附中"] },
    ],
    trips,
    in_transit: trips.filter((t) => t.status === "运输中"),
    risk_events: [
      { id: "mock-risk-1", type: "未出库", level: "中", title: "OD-FUL-810002", description: "北菜源供应链 3 条分单未出库", route_no: "京配-海淀-02", trip_id: 7102 },
      { id: "mock-risk-2", type: "未随车", level: "高", title: "OD-FUL-810002", description: "华鲜直采 1 条分单因质量复核滞留", route_no: "京配-海淀-02", trip_id: 7102 },
    ],
    map_points: FULFILLMENT_MOCK_POINTS,
    orders_detail: orders,
    allocations_detail: allocations,
  }
}

function applyFulfillmentPayload(payload) {
  fulfillmentData.date = payload?.date || ""
  fulfillmentData.data_mode = payload?.data_mode || ""
  fulfillmentData.summary = payload?.summary || {}
  fulfillmentData.funnel = Array.isArray(payload?.funnel) ? payload.funnel : []
  fulfillmentData.supplier_blocks = Array.isArray(payload?.supplier_blocks) ? payload.supplier_blocks : []
  fulfillmentData.trips = Array.isArray(payload?.trips) ? payload.trips : []
  fulfillmentData.in_transit = Array.isArray(payload?.in_transit) ? payload.in_transit : []
  fulfillmentData.risk_events = Array.isArray(payload?.risk_events) ? payload.risk_events : []
  fulfillmentData.map_points = Array.isArray(payload?.map_points) ? payload.map_points : []
  fulfillmentData.orders_detail = Array.isArray(payload?.orders_detail) ? payload.orders_detail : []
  fulfillmentData.allocations_detail = Array.isArray(payload?.allocations_detail) ? payload.allocations_detail : []
}

function setFulfillmentKpiCards() {
  const s = fulfillmentSummary.value
  state.totalView = [
    {
      icon: "xiaoshoujine",
      zh: "履约健康分",
      en: "Fulfillment score",
      value: Number(s.health_score) || 0,
      unit: "分",
      decimals: 0,
    },
    {
      icon: "zongxiaoliang",
      zh: "待发/在途车次",
      en: "Active trips",
      value: (Number(s.pending_trips) || 0) + (Number(s.in_transit_trips) || 0),
      unit: "车",
      decimals: 0,
    },
  ]
}

function fingerprintFulfillmentPoints(pts) {
  if (!Array.isArray(pts) || pts.length === 0) return ""
  return pts
    .map((p) => {
      const lng = Number(p.lng)
      const lat = Number(p.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
      return `${p.stage || ""}:${p.trip_id || ""}:${p.order_id || ""}:${lng.toFixed(5)}:${lat.toFixed(5)}:${p.status || ""}`
    })
    .filter(Boolean)
    .sort()
    .join("|")
}

let lastFulfillmentFingerprint = undefined

function renderFulfillmentModeLayer({ force = false } = {}) {
  const w = getMapWorld()
  const pts = fulfillmentMapPointsByMode.value
  const fp = `${fulfillmentMode.value}|${fingerprintFulfillmentPoints(pts)}`
  if ((force || fp !== lastFulfillmentFingerprint) && w?.setOrderPillars) {
    lastFulfillmentFingerprint = fp
    w.setOrderPillars(pts)
    w.setFlylines?.(buildFulfillmentFlylines(pts))
  }
}

async function loadFulfillmentOverview({ force = false } = {}) {
  fulfillmentLoading.value = true
  fulfillmentError.value = ""
  setFulfillmentKpiCards()
  try {
    const q = new URLSearchParams({ limit: "100" })
    if (chartQueryDistrict.value) q.set("district_name", chartQueryDistrict.value)
    let d = await fetchJson(`${FULFILLMENT_OVERVIEW}?${q}`, { bypassCache: force })
    const hasRealRows =
      Number(d?.summary?.today_orders || 0) > 0 ||
      (Array.isArray(d?.trips) && d.trips.length > 0) ||
      (Array.isArray(d?.orders_detail) && d.orders_detail.length > 0)
    if (!hasRealRows) {
      d = buildFulfillmentMockData("empty")
    } else if (!Array.isArray(d?.map_points) || !d.map_points.length) {
      d = { ...d, map_points: FULFILLMENT_MOCK_POINTS, data_mode: d?.data_mode || "real" }
    }
    applyFulfillmentPayload(d)
    setFulfillmentKpiCards()
    renderFulfillmentModeLayer({ force })
  } catch (e) {
    applyFulfillmentPayload(buildFulfillmentMockData("fallback"))
    setFulfillmentKpiCards()
    const msg = e?.message || String(e)
    fulfillmentError.value = msg === "Not Found" || isTianshuAuthMissingError(e) ? "" : msg
    renderFulfillmentModeLayer({ force: true })
  } finally {
    fulfillmentLoading.value = false
  }
}

function buildFulfillmentFlylines(points) {
  const pts = Array.isArray(points) ? points : []
  const hub = { lng: 116.4074, lat: 39.9042, name: "履约调度中枢" }
  return pts
    .filter((p) => Number.isFinite(Number(p.lng)) && Number.isFinite(Number(p.lat)))
    .slice(0, 24)
    .map((p, idx) => ({
      from_lng: hub.lng,
      from_lat: hub.lat,
      to_lng: Number(p.lng),
      to_lat: Number(p.lat),
      from_name: hub.name,
      to_name: p.customer_name || p.address || `站点${idx + 1}`,
      gmv: Number(p.gmv) || Number(p.order_count) || 1,
      order_count: Number(p.order_count) || 1,
      color: String(p.stage || "") === "blocked" ? "#f59e0b" : "#67e8f9",
    }))
}

function closeFulfillmentDrawer() {
  fulfillmentDrawerOpen.value = false
  fulfillmentDrawerState.deviceTarget = null
  deviceBindingState.loading = false
  deviceBindingState.error = ""
  deviceBindingState.data = null
  closeDeviceOverlay()
}

function closeTianshuOverlays() {
  if (fulfillmentDrawerOpen.value) closeFulfillmentDrawer()
  if (orderDetailOpen.value) closeOrderDetail()
  orderHover.value = null
}

function tianshuDirectorDelay(ms, runId) {
  return new Promise((resolve, reject) => {
    window.setTimeout(() => {
      if (directorRunId !== runId || !directorState.running) {
        reject(new Error("director_stopped"))
        return
      }
      resolve()
    }, ms)
  })
}

function postTianshuDirectorState() {
  if (typeof window === "undefined" || window.parent === window) return
  try {
    window.parent.postMessage(
      {
        type: "tianshu-director-state",
        running: Boolean(directorState.running),
        phase: directorState.phase,
        stepIndex: directorState.stepIndex,
      },
      "*",
    )
  } catch {
    /* ignore */
  }
}

async function toggleTianshuDirector() {
  if (directorState.running) {
    stopTianshuDirector()
    return
  }
  await startTianshuDirector()
}

function stopTianshuDirector() {
  directorRunId += 1
  directorState.running = false
  directorState.phase = "已停止"
  directorState.stepIndex = -1
  closeTianshuOverlays()
  postTianshuDirectorState()
}

async function startTianshuDirector() {
  const runId = directorRunId + 1
  directorRunId = runId
  directorState.running = true
  directorState.phase = "启动巡航"
  closeTianshuOverlays()
  postTianshuDirectorState()
  try {
    for (let i = 0; i < DIRECTOR_STEPS.length; i += 1) {
      const step = DIRECTOR_STEPS[i]
      directorState.stepIndex = i
      directorState.phase = `切换 ${step.title}`
      postTianshuDirectorState()
      state.activeIndex = step.menuIndex
      await switchTianshuView(step.view)
      await tianshuDirectorDelay(step.view === VIEW_OVERVIEW ? 1200 : 1650, runId)
      if (step.mode && bottomTrayItems.value.includes(step.mode)) {
        directorState.phase = `${step.title} · ${step.mode}`
        onBottomTraySelect(step.mode)
        await tianshuDirectorDelay(900, runId)
      }
      directorState.phase = `${step.title} · 下钻`
      await openDirectorStepDetail(step)
      await tianshuDirectorDelay(step.view === VIEW_OVERVIEW ? 2200 : 3400, runId)
      closeTianshuOverlays()
      await tianshuDirectorDelay(450, runId)
    }
    directorState.phase = "演示完成"
  } catch (e) {
    if (e?.message !== "director_stopped") {
      console.warn("[tianshu] 自动演示中断", e)
      directorState.phase = "演示中断"
    }
  } finally {
    if (directorRunId === runId) {
      directorState.running = false
      directorState.stepIndex = -1
      postTianshuDirectorState()
    }
  }
}

async function openDirectorStepDetail(step) {
  await nextTick()
  if (step.open === "overview") {
    openTodayOrdersListFromOps()
    return
  }
  if (step.open === "fulfillment") {
    const trip =
      fulfillmentTrips.value.find((item) => Number(item.blocked_count || item.not_loaded_count || item.risk_count) > 0) ||
      fulfillmentTrips.value[0]
    if (trip) openFulfillmentTripDetail(trip)
    else openFulfillmentHubDetail()
    return
  }
  if (step.open === "cold") {
    const event = coldChainEvents.value[0]
    if (event) openColdEventDetail(event)
    else if (coldChainAbnormalVehicles.value[0]) openColdVehicleDetail(coldChainAbnormalVehicles.value[0])
    else if (coldChainAbnormalWarehouses.value[0]) openColdWarehouseDetail(coldChainAbnormalWarehouses.value[0])
    else openColdChainHubDetail()
    return
  }
  if (step.open === "city") {
    const district = cityRiskDistricts.value[0] || cityModeDistricts.value[0] || cityDistricts.value[0]
    if (district) openCityDistrictDetail(district)
    else openCityProfileHubDetail()
    return
  }
  if (step.open === "industry") {
    const impact = industryImpacts.value[0]
    if (impact) openIndustryItemDetail(impact, "采购影响")
    else if (industryModeGoods.value[0]) openIndustryItemDetail(industryModeGoods.value[0], "商品")
    else if (industryForecasts.value[0]) openIndustryItemDetail(industryForecasts.value[0], "价格品种")
    else openIndustryHubDetail()
    return
  }
  if (step.open === "risk") {
    const high = riskItemsByMode.value.find((item) => riskLevelText(item.level) === "高") || riskItemsByMode.value[0]
    if (high) openRiskItemDetail(high)
    else if (riskPoints.value[0]) openRiskPointDetail(riskPoints.value[0])
    else openRiskHubDetail()
  }
}

function setFulfillmentDrawer(payload) {
  fulfillmentDrawerState.title = payload.title || "履约详情"
  fulfillmentDrawerState.subtitle = payload.subtitle || "供应链履约"
  fulfillmentDrawerState.conclusion = payload.conclusion || ""
  fulfillmentDrawerState.summaryCards = Array.isArray(payload.summaryCards) ? payload.summaryCards : []
  fulfillmentDrawerState.sections = Array.isArray(payload.sections) ? payload.sections : []
  fulfillmentDrawerState.deviceTarget = payload.deviceTarget || null
  fulfillmentDrawerOpen.value = true
  void loadDeviceBinding(fulfillmentDrawerState.deviceTarget)
}

function deviceTargetFrom(item) {
  if (!item) return null
  const vehicleId = item.vehicle_id ?? item.vehicleId
  const warehouseId = item.warehouse_id ?? item.warehouseId
  const asTarget = (type, id) => {
    const n = Number(id)
    return Number.isFinite(n) && n > 0 ? { type, id: n } : null
  }
  if (vehicleId != null && vehicleId !== "") return asTarget("vehicle", vehicleId)
  if (warehouseId != null && warehouseId !== "") return asTarget("warehouse", warehouseId)
  if (item.target_type === "vehicle" && item.target_id) return asTarget("vehicle", item.target_id)
  if (item.target_type === "warehouse" && item.target_id) return asTarget("warehouse", item.target_id)
  return null
}

function openFulfillmentHubDetail() {
  const s = fulfillmentSummary.value
  setFulfillmentDrawer({
    title: "今日履约总览",
    subtitle: fulfillmentData.data_mode === "mock" ? "模拟数据 · 用于展示动效和下钻" : "真实履约闭环聚合",
    conclusion: `今日 ${s.today_orders || 0} 单配送任务，分检完成率 ${formatPct(s.sort_rate)}，装车完成率 ${formatPct(s.load_rate)}，仍有 ${s.blocked_allocations || 0} 条阻塞分单。`,
    summaryCards: [
      { label: "健康分", value: `${s.health_score || 0} 分`, tone: "good" },
      { label: "今日订单", value: `${s.today_orders || 0} 单` },
      { label: "在途车次", value: `${s.in_transit_trips || 0} 车` },
      { label: "履约风险", value: `${s.risk_count || 0} 项`, tone: s.risk_count ? "warn" : "good" },
    ],
    sections: [
      { title: "关联订单", rows: fulfillmentOrderRows(fulfillmentData.orders_detail).slice(0, 20) },
      { title: "分单/商品履约", rows: fulfillmentAllocationRows(fulfillmentData.allocations_detail).slice(0, 24) },
      { title: "车次队列", rows: fulfillmentTripRows(fulfillmentData.trips).slice(0, 12) },
    ],
  })
}

function openFulfillmentFunnelDetail(item) {
  const key = item?.key
  const unfinishedKeys = {
    shipped: "未出库",
    sorted: "未分检",
    loaded: "未随车",
  }
  const blockedStatus = unfinishedKeys[key]
  const allocations = blockedStatus
    ? fulfillmentData.allocations_detail.filter((row) => row.business_status === blockedStatus)
    : fulfillmentData.allocations_detail
  setFulfillmentDrawer({
    title: item?.label || "履约阶段",
    subtitle: "履约闭环漏斗下钻",
    conclusion: `当前阶段完成 ${item?.count || 0} / ${item?.total || 0}，完成率 ${formatPct(item?.percent)}。`,
    summaryCards: [
      { label: "完成数", value: item?.count || 0, tone: "good" },
      { label: "总数", value: item?.total || 0 },
      { label: "完成率", value: formatPct(item?.percent) },
    ],
    sections: key === "departed" || key === "arrived"
      ? [{ title: key === "departed" ? "已发车车次" : "已送达订单", rows: key === "departed" ? fulfillmentTripRows(fulfillmentData.trips.filter((t) => t.status === "运输中" || t.departed_at)) : fulfillmentOrderRows(fulfillmentData.orders_detail.filter((o) => ["收货", "收货确认", "已结算"].includes(o.status))) }]
      : [
          { title: "关联订单", rows: fulfillmentOrderRows(fulfillmentData.orders_detail).slice(0, 20) },
          { title: blockedStatus ? `${blockedStatus}明细` : "分单明细", rows: fulfillmentAllocationRows(allocations).slice(0, 24) },
        ],
  })
}

function openFulfillmentSupplierDetail(item) {
  const rows = fulfillmentData.allocations_detail.filter((row) => Number(row.supplier_id) === Number(item.supplier_id))
  setFulfillmentDrawer({
    title: item.supplier_name || "供应商阻塞",
    subtitle: "供应商履约阻塞下钻",
    conclusion: `当前阻塞 ${item.blocked_count || 0} 条，影响 ${item.affected_orders || 0} 单。`,
    summaryCards: [
      { label: "未出库", value: item.not_shipped || 0, tone: item.not_shipped ? "warn" : "" },
      { label: "未分检", value: item.not_sorted || 0, tone: item.not_sorted ? "warn" : "" },
      { label: "未随车", value: item.not_loaded || 0, tone: item.not_loaded ? "danger" : "" },
    ],
    sections: [
      { title: "阻塞分单", rows: fulfillmentAllocationRows(rows).slice(0, 24) },
      { title: "影响客户", rows: (item.affected_clients || []).map((name) => ({ 客户: name, 状态: "受影响" })) },
    ],
  })
}

function openFulfillmentTripDetail(item) {
  setFulfillmentDrawer({
    title: item.route_no || "车次详情",
    subtitle: `${item.delivery_name || "配送商"} · ${item.status || "状态待识别"}`,
    conclusion: `车次 ${item.route_no || ""} 当前状态为${item.status || "待识别"}，共 ${item.stop_count || 0} 个站点，阻塞 ${item.blocked_count || 0} 条，未随车 ${item.not_loaded_count || 0} 条。`,
    summaryCards: [
      { label: "状态", value: item.status || "—" },
      { label: "站点", value: `${item.stop_count || 0} 站` },
      { label: "阻塞", value: item.blocked_count || 0, tone: item.blocked_count ? "warn" : "good" },
      { label: "未随车", value: item.not_loaded_count || 0, tone: item.not_loaded_count ? "danger" : "good" },
    ],
    sections: [
      { title: "车次与司机车辆", rows: fulfillmentTripRows([item]) },
      { title: "站点顺序", rows: fulfillmentStopRows(item.stops || []) },
      { title: "风险原因", rows: (item.risk_alerts || []).map((text) => ({ 风险说明: text, 建议动作: "请调度员核实路线、时窗或车辆安排。" })) },
    ],
    deviceTarget: deviceTargetFrom(item),
  })
}

function openFulfillmentRiskDetail(item) {
  const trip = fulfillmentData.trips.find((t) => Number(t.id) === Number(item.trip_id))
  if (trip) {
    openFulfillmentTripDetail(trip)
    return
  }
  setFulfillmentDrawer({
    title: item.type || "履约风险",
    subtitle: item.title || item.route_no || "风险事件",
    conclusion: item.description || "当前履约事件需要人工复核。",
    summaryCards: [
      { label: "等级", value: item.level || "中", tone: item.level === "高" ? "danger" : "warn" },
      { label: "车次", value: item.route_no || "—" },
    ],
    sections: [{ title: "事件说明", rows: [{ 风险类型: item.type, 风险说明: item.description, 关联对象: item.title || item.route_no }] }],
  })
}

function riskPointRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    对象: row.customer_name || row.address || "—",
    类型: riskTypeText(row.risk_type),
    等级: riskLevelText(row.risk_level),
    金额: row.gmv != null ? `¥${formatMoney(row.gmv)}` : "—",
    订单: row.order_sn || row.order_id || "—",
    说明: row.description || "—",
  }))
}

function riskItemRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    类型: row.type || "风险事件",
    等级: row.level || "中",
    状态: row.status || "待处置",
    对象: row.customer_name || row.order_sn || "—",
    金额: row.amount != null ? `¥${formatMoney(row.amount)}` : "—",
    说明: row.description || "—",
  }))
}

function openRiskHubDetail() {
  const k = riskKpis.value
  setFulfillmentDrawer({
    title: "风险预警总览",
    subtitle: riskMode.value,
    conclusion: `当前待处置风险 ${k.pending_count} 项，开放告警 ${k.open_alerts} 条，高风险 ${k.high_count} 项。`,
    summaryCards: [
      { label: "待处置", value: k.pending_count, tone: k.pending_count ? "warn" : "good" },
      { label: "高风险", value: k.high_count, tone: k.high_count ? "danger" : "good" },
      { label: "异常订单", value: k.abnormal_orders, tone: k.abnormal_orders ? "danger" : "good" },
      { label: "退单金额", value: `¥${compactMoney(k.return_amount)}`, tone: k.return_amount ? "warn" : "good" },
    ],
    sections: [
      { title: "风险点位", rows: riskPointRows(riskMapPointsByMode.value).slice(0, 20) },
      { title: "实时风险队列", rows: riskItemRows(riskItemsByMode.value).slice(0, 20) },
      { title: "处置建议", rows: riskRecommendations.value.map((item) => ({ 建议: item.title, 内容: item.content })) },
    ],
  })
}

function openRiskPointDetail(payload) {
  const point = riskPoints.value.find((p) => {
    if (payload.order_id != null && p.order_id != null && String(p.order_id) === String(payload.order_id)) return true
    if (payload.order_sn && p.order_sn && String(p.order_sn) === String(payload.order_sn)) return true
    return (
      String(p.customer_name || p.address || "") === String(payload.customer_name || payload.address || "") &&
      String(p.risk_type || "") === String(payload.risk_type || "")
    )
  }) || payload
  const related = riskItemsByMode.value.filter((item) => {
    if (point.order_id != null && item.order_id != null && String(item.order_id) === String(point.order_id)) return true
    if (point.order_sn && item.order_sn && String(item.order_sn) === String(point.order_sn)) return true
    return String(item.customer_name || "") === String(point.customer_name || "")
  })
  setFulfillmentDrawer({
    title: point.customer_name || point.address || "风险点位",
    subtitle: `${riskLevelText(point.risk_level)}风险 · ${riskTypeText(point.risk_type)}`,
    conclusion: point.description || "该地图光柱对应一个需要复核的业务风险点位。",
    summaryCards: [
      { label: "等级", value: riskLevelText(point.risk_level), tone: riskLevelText(point.risk_level) === "高" ? "danger" : "warn" },
      { label: "类型", value: riskTypeText(point.risk_type) },
      { label: "金额", value: `¥${compactMoney(point.gmv)}` },
      { label: "订单", value: point.order_sn || point.order_id || "—" },
    ],
    sections: [
      { title: "点位明细", rows: riskPointRows([point]) },
      { title: "关联风险队列", rows: riskItemRows(related.length ? related : riskItemsByMode.value.slice(0, 5)) },
      { title: "建议动作", rows: riskRecommendations.value.slice(0, 3).map((row) => ({ 建议: row.title, 内容: row.content })) },
    ],
    deviceTarget: deviceTargetFrom(point),
  })
}

function openRiskItemDetail(item) {
  const point = riskPoints.value.find((p) => String(p.order_id || p.order_sn) === String(item.order_id || item.order_sn))
  setFulfillmentDrawer({
    title: item.type || riskTypeText(point?.risk_type) || "风险事件",
    subtitle: `${item.level || riskLevelText(point?.risk_level)}风险 · ${item.status || "待处置"}`,
    conclusion: item.description || point?.description || "该风险事件需要人工复核并闭环处置。",
    summaryCards: [
      { label: "等级", value: item.level || riskLevelText(point?.risk_level), tone: riskLevelText(item.level || point?.risk_level) === "高" ? "danger" : "warn" },
      { label: "金额", value: `¥${compactMoney(item.amount ?? point?.gmv)}` },
      { label: "订单", value: item.order_sn || point?.order_sn || "—" },
      { label: "状态", value: item.status || "待处置" },
    ],
    sections: [
      { title: "事件明细", rows: riskItemRows([item]) },
      { title: "地图点位", rows: point ? riskPointRows([point]) : [] },
      { title: "建议动作", rows: riskRecommendations.value.slice(0, 3).map((row) => ({ 建议: row.title, 内容: row.content })) },
    ],
    deviceTarget: deviceTargetFrom(item) || deviceTargetFrom(point),
  })
}

function openRiskRecommendationDetail(item) {
  setFulfillmentDrawer({
    title: item.title || "处置建议",
    subtitle: "风险预警 · 处置队列",
    conclusion: item.content || "该建议用于辅助风险闭环处置。",
    summaryCards: [
      { label: "待处置", value: riskKpis.value.pending_count, tone: riskKpis.value.pending_count ? "warn" : "good" },
      { label: "高风险", value: riskKpis.value.high_count, tone: riskKpis.value.high_count ? "danger" : "good" },
      { label: "开放告警", value: riskKpis.value.open_alerts, tone: riskKpis.value.open_alerts ? "warn" : "good" },
    ],
    sections: [
      { title: "建议内容", rows: [{ 建议: item.title, 内容: item.content }] },
      { title: "关联高风险", rows: riskItemRows(riskItemsByMode.value.filter((row) => riskLevelText(row.level) === "高")).slice(0, 8) },
    ],
  })
}

function coldTypeText(type) {
  const t = String(type || "").toLowerCase()
  if (t === "vehicle") return "冷链车辆"
  if (t === "warehouse") return "冷库仓温"
  return "冷链点位"
}

function coldTempNumber(v) {
  const n = Number(String(v ?? "").replace("℃", "").replace("%", "").trim())
  return Number.isFinite(n) ? n : null
}

function coldWarehouseAlert(item) {
  const temp = coldTempNumber(item?.elitech_temperature)
  const hum = coldTempNumber(item?.elitech_humidity)
  return Boolean(
    (temp != null && (temp < -2 || temp > 8)) ||
      (hum != null && hum > 85) ||
      (item?.elitech_bound && !item?.elitech_online),
  )
}

function buildColdChainMockData(reason = "") {
  const vehicles = [
    {
      id: 9101,
      vehicle_no: "京A·C8101",
      driver_name: "赵师傅",
      delivery_name: "朝阳冷链配送中心",
      online_status: "online",
      coordinate_valid: true,
      lng: 116.486,
      lat: 39.921,
      speed: 42,
      reported_at: "刚刚",
      cameras: [{ id: 1 }],
      temperature: "3.8",
      humidity: "62",
    },
    {
      id: 9102,
      vehicle_no: "京N·C9202",
      driver_name: "孙师傅",
      delivery_name: "海淀冷链配送中心",
      online_status: "offline",
      coordinate_valid: true,
      lng: 116.298,
      lat: 39.959,
      speed: 0,
      reported_at: "18 分钟前",
      cameras: [],
      temperature: "9.6",
      humidity: "71",
    },
  ]
  const warehouses = [
    {
      id: 9201,
      name: "朝阳一号冷库",
      address: "北京市朝阳区冷链仓",
      delivery_name: "朝阳冷链配送中心",
      lng: 116.455,
      lat: 39.905,
      elitech_bound: true,
      elitech_temperature: "3.2",
      elitech_humidity: "61",
      elitech_online: true,
      cameras: [{ id: 1 }, { id: 2 }],
    },
    {
      id: 9202,
      name: "海淀校园冷库",
      address: "北京市海淀区冷链仓",
      delivery_name: "海淀冷链配送中心",
      lng: 116.315,
      lat: 39.962,
      elitech_bound: true,
      elitech_temperature: "10.4",
      elitech_humidity: "78",
      elitech_online: true,
      cameras: [{ id: 3 }],
    },
  ]
  return {
    date: clock.date || new Date().toISOString().slice(0, 10),
    data_mode: "mock",
    mock_reason: reason,
    summary: {
      vehicles: 2,
      online_vehicles: 1,
      offline_vehicles: 1,
      unlocated_vehicles: 0,
      warehouses: 2,
      temperature_online: 2,
      temperature_alerts: 1,
      cameras: 3,
      online_rate: 50,
      cold_score: 78,
    },
    vehicles,
    warehouses,
    events: [
      { id: "mock-cold-vehicle-9102", type: "车辆离线", level: "高", title: "京N·C9202", description: "北斗 18 分钟未刷新，建议联系司机确认冷链状态。", target_type: "vehicle", target_id: 9102 },
      { id: "mock-cold-warehouse-9202", type: "仓温偏高", level: "高", title: "海淀校园冷库", description: "实时温度 10.4℃，超过冷藏上限，建议立即复核库门和制冷机组。", target_type: "warehouse", target_id: 9202 },
    ],
    map_points: COLD_CHAIN_MOCK_POINTS,
  }
}

function applyColdChainPayload(payload) {
  coldChainData.date = payload?.date || ""
  coldChainData.data_mode = payload?.data_mode || ""
  coldChainData.summary = payload?.summary || {}
  coldChainData.vehicles = Array.isArray(payload?.vehicles) ? payload.vehicles : []
  coldChainData.warehouses = Array.isArray(payload?.warehouses) ? payload.warehouses : []
  coldChainData.events = Array.isArray(payload?.events) ? payload.events : []
  coldChainData.map_points = Array.isArray(payload?.map_points) ? payload.map_points : []
}

function setColdChainKpiCards() {
  const s = coldChainSummary.value
  state.totalView = [
    {
      icon: "xiaoshoujine",
      zh: "冷链在线率",
      en: "Cold-chain online",
      value: Number(s.online_rate) || 0,
      unit: "%",
      decimals: 1,
    },
    {
      icon: "zongxiaoliang",
      zh: "温控异常",
      en: "Temperature alerts",
      value: Number(s.temperature_alerts) || 0,
      unit: "项",
      decimals: 0,
    },
  ]
}

function fingerprintColdChainPoints(pts) {
  if (!Array.isArray(pts) || pts.length === 0) return ""
  return pts
    .map((p) => {
      const lng = Number(p.lng)
      const lat = Number(p.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
      return `${p.cold_type || ""}:${p.vehicle_id || p.warehouse_id || ""}:${lng.toFixed(5)}:${lat.toFixed(5)}:${p.stage || ""}:${p.status || ""}`
    })
    .filter(Boolean)
    .sort()
    .join("|")
}

let lastColdChainFingerprint = undefined

function renderColdChainModeLayer({ force = false } = {}) {
  const w = getMapWorld()
  const pts = coldChainMapPointsByMode.value
  const fp = `${coldChainMode.value}|${fingerprintColdChainPoints(pts)}`
  if ((force || fp !== lastColdChainFingerprint) && w?.setOrderPillars) {
    lastColdChainFingerprint = fp
    w.setOrderPillars(pts)
    w.setFlylines?.(buildColdChainFlylines(pts))
  }
}

async function loadColdChainOverview({ force = false } = {}) {
  coldChainLoading.value = true
  coldChainError.value = ""
  setColdChainKpiCards()
  try {
    let d = await fetchJson(`${COLD_CHAIN_OVERVIEW}?limit=100`, { bypassCache: force })
    if ((!Array.isArray(d?.vehicles) || !d.vehicles.length) && (!Array.isArray(d?.warehouses) || !d.warehouses.length)) {
      d = buildColdChainMockData("empty")
    } else if (!Array.isArray(d?.map_points) || !d.map_points.length) {
      d = { ...d, map_points: COLD_CHAIN_MOCK_POINTS, data_mode: d?.data_mode || "real" }
    }
    applyColdChainPayload(d)
    setColdChainKpiCards()
    renderColdChainModeLayer({ force })
  } catch (e) {
    applyColdChainPayload(buildColdChainMockData("fallback"))
    setColdChainKpiCards()
    const msg = e?.message || String(e)
    coldChainError.value = msg === "Not Found" || isTianshuAuthMissingError(e) ? "" : msg
    renderColdChainModeLayer({ force: true })
  } finally {
    coldChainLoading.value = false
  }
}

function buildColdChainFlylines(points) {
  const pts = Array.isArray(points) ? points : []
  const hub = { lng: 116.4074, lat: 39.9042, name: "冷链调度中枢" }
  const mode = coldChainMode.value
  return pts
    .filter((p) => Number.isFinite(Number(p.lng)) && Number.isFinite(Number(p.lat)))
    .slice(0, 24)
    .map((p, idx) => ({
      from_lng: hub.lng,
      from_lat: hub.lat,
      to_lng: Number(p.lng),
      to_lat: Number(p.lat),
      from_name: hub.name,
      to_name: p.customer_name || p.address || `冷链点${idx + 1}`,
      gmv: p.stage === "alert" || mode === "异常处置" ? 3 : mode === "车辆轨迹" ? 2 : 1,
      order_count: 1,
      color:
        p.stage === "alert" || mode === "异常处置"
          ? "#fb7185"
          : mode === "仓温监控"
          ? "#c084fc"
          : "#a7f3ff",
    }))
}

function applyIndustryPayload(payload) {
  industryData.date = payload?.date || payload?.end_date || ""
  industryData.data_mode = payload?.data_mode || ""
  industryData.summary = payload?.summary || {}
  industryData.category_mix = Array.isArray(payload?.category_mix) ? payload.category_mix : []
  industryData.goods_rank = Array.isArray(payload?.goods_rank) ? payload.goods_rank : []
  industryData.forecast_items = Array.isArray(payload?.forecast_items) ? payload.forecast_items : []
  industryData.price_series = Array.isArray(payload?.price_series) ? payload.price_series : []
  industryData.impact_items = Array.isArray(payload?.impact_items) ? payload.impact_items : []
  industryData.map_points = Array.isArray(payload?.map_points) ? payload.map_points : []
}

function setIndustryKpiCards() {
  const s = industrySummary.value
  state.totalView = [
    { icon: "xiaoshoujine", zh: "价格波动品种", en: "Volatile goods", value: Number(s.volatile_products) || 0, unit: "种", decimals: 0 },
    { icon: "zongxiaoliang", zh: "预测可用商品", en: "Forecast ready", value: Number(s.forecast_usable) || 0, unit: "种", decimals: 0 },
  ]
}

function fingerprintBusinessPoints(pts, role) {
  if (!Array.isArray(pts) || pts.length === 0) return ""
  return pts
    .map((p) => {
      const lng = Number(p.lng)
      const lat = Number(p.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
      return `${role}:${p.stage || ""}:${p.product_name || p.district_name || p.customer_name || ""}:${lng.toFixed(5)}:${lat.toFixed(5)}:${p.gmv || 0}:${p.risk_count || ""}`
    })
    .filter(Boolean)
    .sort()
    .join("|")
}

function buildIndustryMockData(reason = "") {
  const forecasts = [
    { product_name: "小白菜", latest_price: 3.2, forecast_price: 3.48, change_pct: 8.6, confidence: 82, status: "可预测" },
    { product_name: "猪后腿肉", latest_price: 27.8, forecast_price: 29.7, change_pct: 6.8, confidence: 76, status: "可预测" },
    { product_name: "鲜鸡蛋", latest_price: 8.9, forecast_price: 8.62, change_pct: -3.2, confidence: 79, status: "可预测" },
  ]
  const goods = [
    { goods_name: "小白菜", total_quantity: 1880, total_amount: 62500, order_count: 23, change_pct: 8.6 },
    { goods_name: "鲜鸡蛋", total_quantity: 920, total_amount: 58400, order_count: 18, change_pct: -3.2 },
    { goods_name: "土豆", total_quantity: 2100, total_amount: 42300, order_count: 21, change_pct: 2.1 },
    { goods_name: "猪后腿肉", total_quantity: 640, total_amount: 76800, order_count: 14, change_pct: 6.8 },
  ]
  const anchors = [[116.486, 39.921], [116.298, 39.959], [116.656, 39.91]]
  return {
    date: clock.date || new Date().toISOString().slice(0, 10),
    data_mode: "mock",
    mock_reason: reason,
    summary: { monitored_categories: 4, volatile_products: 2, forecast_usable: 3, hot_goods: "小白菜", quote_count: 12, business_goods: goods.length },
    category_mix: [
      { category_name: "叶菜类", order_count: 46, total_amount: 286000, total_quantity: 8200 },
      { category_name: "肉禽蛋", order_count: 31, total_amount: 244000, total_quantity: 3900 },
      { category_name: "根茎类", order_count: 28, total_amount: 118000, total_quantity: 6100 },
      { category_name: "米面粮油", order_count: 18, total_amount: 96000, total_quantity: 5200 },
    ],
    goods_rank: goods,
    forecast_items: forecasts,
    price_series: forecasts.map((x) => ({ date: clock.date || "", product_name: x.product_name, category_name: "全国农产品", avg_price: x.latest_price })),
    impact_items: [
      { title: "叶菜采购预警", target: "小白菜", impact: "预测上行 8.6%，建议锁定明日高频食堂采购量。", level: "高" },
      { title: "肉类成本压力", target: "猪后腿肉", impact: "平台 GMV 占比较高，建议复核供应商报价。", level: "中" },
      { title: "蛋类回落窗口", target: "鲜鸡蛋", impact: "预测回落，可延后非刚需补库。", level: "低" },
    ],
    map_points: forecasts.map((item, idx) => {
      const [lng, lat] = anchors[idx]
      return {
        role: "industry",
        stage: Math.abs(Number(item.change_pct) || 0) >= 5 ? "volatile" : "normal",
        industry_type: "forecast",
        product_name: item.product_name,
        category_name: "重点品种",
        change_pct: item.change_pct,
        forecast_price: item.forecast_price,
        confidence: item.confidence,
        lng,
        lat,
        customer_name: item.product_name,
        address: `${item.product_name}价格预测热区`,
        description: `预测 ${item.forecast_price} 元，波动 ${item.change_pct}%`,
        order_count: 1,
        gmv: Math.abs(item.change_pct) * 100,
      }
    }),
  }
}

let lastIndustryFingerprint = undefined

function renderIndustryModeLayer({ force = false } = {}) {
  const w = getMapWorld()
  const pts = industryMapPointsByMode.value
  const fp = `${industryMode.value}|${fingerprintBusinessPoints(pts, "industry")}`
  if ((force || fp !== lastIndustryFingerprint) && w?.setOrderPillars) {
    lastIndustryFingerprint = fp
    w.setOrderPillars(pts)
    w.setFlylines?.(buildIndustryFlylines(pts))
  }
}

async function loadIndustryInsightsOverview({ force = false } = {}) {
  const w = getMapWorld()
  industryLoading.value = true
  industryError.value = ""
  setIndustryKpiCards()
  try {
    const qs = new URLSearchParams({ limit: "120" })
    let d = await fetchJson(`${INDUSTRY_INSIGHTS_OVERVIEW}?${qs.toString()}`, { bypassCache: force })
    if (
      (!Array.isArray(d?.forecast_items) || !d.forecast_items.length) &&
      (!Array.isArray(d?.goods_rank) || !d.goods_rank.length) &&
      (!Array.isArray(d?.category_mix) || !d.category_mix.length)
    ) {
      d = buildIndustryMockData("empty")
    } else if (!Array.isArray(d?.map_points) || !d.map_points.length) {
      d = { ...d, map_points: buildIndustryMockData("points").map_points, data_mode: d?.data_mode || "real" }
    }
    applyIndustryPayload(d)
    setIndustryKpiCards()
    renderIndustryModeLayer({ force })
  } catch (e) {
    const msg = e?.message || String(e)
    industryError.value = msg === "Not Found" || isTianshuAuthMissingError(e) ? "" : msg
    applyIndustryPayload(buildIndustryMockData("fallback"))
    setIndustryKpiCards()
    renderIndustryModeLayer({ force: true })
  } finally {
    industryLoading.value = false
  }
}

function buildIndustryFlylines(points) {
  const pts = Array.isArray(points) ? points : []
  const hub = { lng: 116.4074, lat: 39.9042, name: "全国价格预测中枢" }
  const mode = industryMode.value
  return pts
    .filter((p) => Number.isFinite(Number(p.lng)) && Number.isFinite(Number(p.lat)))
    .slice(0, 20)
    .map((p) => ({
      from_lng: hub.lng,
      from_lat: hub.lat,
      to_lng: Number(p.lng),
      to_lat: Number(p.lat),
      from_name: hub.name,
      to_name: p.product_name || p.customer_name || "产业热区",
      gmv: mode === "价格脉冲" ? Math.max(2, Math.abs(Number(p.change_pct) || 1)) : Math.max(1, Math.abs(Number(p.change_pct) || 1)),
      order_count: 1,
      color:
        mode === "采购影响"
          ? "#22d3ee"
          : mode === "预测曲线"
          ? "#c084fc"
          : p.stage === "volatile" || mode === "价格脉冲"
          ? "#facc15"
          : "#c084fc",
    }))
}

function applyCityProfilePayload(payload) {
  cityProfileData.date = payload?.date || payload?.end_date || ""
  cityProfileData.data_mode = payload?.data_mode || ""
  cityProfileData.summary = payload?.summary || {}
  cityProfileData.district_profiles = Array.isArray(payload?.district_profiles) ? payload.district_profiles : []
  cityProfileData.growth_districts = Array.isArray(payload?.growth_districts) ? payload.growth_districts : []
  cityProfileData.risk_districts = Array.isArray(payload?.risk_districts) ? payload.risk_districts : []
  cityProfileData.thin_areas = Array.isArray(payload?.thin_areas) ? payload.thin_areas : []
  cityProfileData.map_points = Array.isArray(payload?.map_points) ? payload.map_points : []
}

function setCityProfileKpiCards() {
  const s = cityProfileSummary.value
  state.totalView = [
    { icon: "xiaoshoujine", zh: "覆盖区县", en: "Covered districts", value: Number(s.district_cover_count) || 0, unit: "个", decimals: 0 },
    { icon: "zongxiaoliang", zh: "活跃食堂/客户", en: "Active canteens", value: Number(s.active_canteens || s.active_clients) || 0, unit: "个", decimals: 0 },
  ]
}

function buildCityProfileMockData(reason = "") {
  const districts = [
    { district_name: "朝阳区", gmv: 386000, order_count: 86, client_count: 18, canteen_count: 22, risk_count: 3, fulfillment_count: 12, growth_pct: 12.6 },
    { district_name: "海淀区", gmv: 342000, order_count: 73, client_count: 16, canteen_count: 19, risk_count: 5, fulfillment_count: 10, growth_pct: 8.1 },
    { district_name: "通州区", gmv: 238000, order_count: 48, client_count: 11, canteen_count: 13, risk_count: 1, fulfillment_count: 8, growth_pct: 16.3 },
    { district_name: "大兴区", gmv: 191000, order_count: 42, client_count: 9, canteen_count: 10, risk_count: 2, fulfillment_count: 6, growth_pct: 5.4 },
  ]
  const coords = {
    朝阳区: [116.486, 39.921],
    海淀区: [116.298, 39.959],
    通州区: [116.656, 39.91],
    大兴区: [116.341, 39.726],
  }
  return {
    date: clock.date || new Date().toISOString().slice(0, 10),
    data_mode: "mock",
    mock_reason: reason,
    summary: {
      district_cover_count: districts.length,
      active_clients: districts.reduce((sum, x) => sum + x.client_count, 0),
      active_canteens: districts.reduce((sum, x) => sum + x.canteen_count, 0),
      total_gmv: districts.reduce((sum, x) => sum + x.gmv, 0),
      total_orders: districts.reduce((sum, x) => sum + x.order_count, 0),
      risk_events: districts.reduce((sum, x) => sum + x.risk_count, 0),
    },
    district_profiles: districts,
    growth_districts: [...districts].sort((a, b) => b.growth_pct - a.growth_pct),
    risk_districts: [...districts].sort((a, b) => b.risk_count - a.risk_count),
    thin_areas: districts.filter((x) => x.client_count <= 11),
    map_points: districts.map((d) => {
      const [lng, lat] = coords[d.district_name]
      return {
        role: "city_profile",
        stage: d.risk_count >= 4 ? "risk" : "heat",
        profile_type: "district",
        district_name: d.district_name,
        lng,
        lat,
        customer_name: d.district_name,
        address: `${d.district_name}经营画像`,
        description: `GMV ¥${d.gmv} · 风险 ${d.risk_count} · 食堂 ${d.canteen_count}`,
        order_count: d.order_count,
        gmv: d.gmv,
        client_count: d.client_count,
        canteen_count: d.canteen_count,
        risk_count: d.risk_count,
      }
    }),
  }
}

let lastCityProfileFingerprint = undefined

function renderCityProfileModeLayer({ force = false } = {}) {
  const w = getMapWorld()
  const pts = cityMapPointsByMode.value
  const fp = `${cityProfileMode.value}|${fingerprintBusinessPoints(pts, "city")}`
  if ((force || fp !== lastCityProfileFingerprint) && w?.setOrderPillars) {
    lastCityProfileFingerprint = fp
    w.setOrderPillars(pts)
    w.setFlylines?.(buildCityProfileFlylines(pts))
  }
}

async function loadCityProfileOverview({ force = false } = {}) {
  const w = getMapWorld()
  cityProfileLoading.value = true
  cityProfileError.value = ""
  setCityProfileKpiCards()
  try {
    const qs = new URLSearchParams({ limit: "120" })
    if (chartQueryDistrict.value) qs.set("district_name", chartQueryDistrict.value)
    let d = await fetchJson(`${CITY_PROFILE_OVERVIEW}?${qs.toString()}`, { bypassCache: force })
    if (!Array.isArray(d?.district_profiles) || !d.district_profiles.length) {
      d = buildCityProfileMockData("empty")
    } else if (!Array.isArray(d?.map_points) || !d.map_points.length) {
      d = { ...d, map_points: buildCityProfileMockData("points").map_points, data_mode: d?.data_mode || "real" }
    }
    applyCityProfilePayload(d)
    setCityProfileKpiCards()
    renderCityProfileModeLayer({ force })
  } catch (e) {
    const msg = e?.message || String(e)
    cityProfileError.value = msg === "Not Found" || isTianshuAuthMissingError(e) ? "" : msg
    applyCityProfilePayload(buildCityProfileMockData("fallback"))
    setCityProfileKpiCards()
    renderCityProfileModeLayer({ force: true })
  } finally {
    cityProfileLoading.value = false
  }
}

function buildCityProfileFlylines(points) {
  const pts = Array.isArray(points) ? points : []
  const hub = { lng: 116.4074, lat: 39.9042, name: "城市经营中枢" }
  const mode = cityProfileMode.value
  return pts
    .filter((p) => Number.isFinite(Number(p.lng)) && Number.isFinite(Number(p.lat)))
    .slice(0, 24)
    .map((p) => ({
      from_lng: hub.lng,
      from_lat: hub.lat,
      to_lng: Number(p.lng),
      to_lat: Number(p.lat),
      from_name: hub.name,
      to_name: p.district_name || p.customer_name || "区域画像",
      gmv: mode === "风险密度" ? Math.max(1, Number(p.risk_count) || 1) : Math.max(1, Number(p.order_count) || 1),
      order_count: Number(p.order_count) || 1,
      color:
        mode === "风险密度" || p.stage === "risk"
          ? "#f97316"
          : mode === "客户覆盖"
          ? "#38bdf8"
          : "#22d3ee",
    }))
}

function coldVehicleRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    车牌: row.vehicle_no || "—",
    配送商: row.delivery_name || "—",
    司机: row.driver_name || "—",
    北斗: row.online_status || "offline",
    速度: row.speed || 0,
    上报: row.reported_at || "—",
    定位: row.coordinate_valid === false ? "无效/缺失" : "有效",
    坐标: row.lng != null && row.lat != null ? `${Number(row.lng).toFixed(5)}, ${Number(row.lat).toFixed(5)}` : "—",
    摄像头: row.cameras?.length || 0,
  }))
}

function coldWarehouseRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    冷库: row.name || "—",
    配送商: row.delivery_name || "—",
    温度: `${row.elitech_temperature || "—"}℃`,
    湿度: `RH ${row.elitech_humidity || "—"}%`,
    温控: row.elitech_online ? "在线" : "离线",
    地址: row.address || "—",
    坐标: row.lng != null && row.lat != null ? `${Number(row.lng).toFixed(5)}, ${Number(row.lat).toFixed(5)}` : "—",
    摄像头: row.cameras?.length || 0,
  }))
}

function coldEventRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    异常类型: row.type || "冷链异常",
    等级: row.level || "中",
    对象: row.title || "—",
    说明: row.description || "—",
    建议动作: row.target_type === "warehouse"
      ? "复核 Elitech 设备在线状态、库门开闭和冷机运行。"
      : "联系司机确认北斗/车辆状态，必要时切换备用车。",
  }))
}

function tianshuAuthHeaders() {
  const token = typeof window !== "undefined" ? window.localStorage?.getItem("dz_token") : ""
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function fetchTianshuJsonWithTimeout(url, { timeoutMs = DEVICE_LINK_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      headers: tianshuAuthHeaders(),
      signal: controller.signal,
    })
    const text = await res.text()
    let data = null
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
    if (!res.ok) {
      const detail = data?.detail
      throw new Error(typeof detail === "string" ? detail : text || res.statusText || `HTTP ${res.status}`)
    }
    return data
  } catch (e) {
    if (e?.name === "AbortError") throw new Error("设备联动接口超时，请确认 VPN 或外部设备服务状态")
    throw e
  } finally {
    window.clearTimeout(timer)
  }
}

async function postTianshuJson(url, body = {}, { timeoutMs = DEVICE_LINK_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        ...tianshuAuthHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    const text = await res.text()
    let data = null
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
    if (!res.ok) {
      const detail = data?.detail
      throw new Error(typeof detail === "string" ? detail : text || res.statusText || `HTTP ${res.status}`)
    }
    return data
  } catch (e) {
    if (e?.name === "AbortError") throw new Error("设备联动接口超时，请确认 VPN 或外部设备服务状态")
    throw e
  } finally {
    window.clearTimeout(timer)
  }
}

function deviceOnlineText(status) {
  const s = String(status || "").toLowerCase()
  if (s === "online") return "在线"
  if (s === "offline") return "离线"
  if (s === "unbound") return "未绑定"
  return status || "未知"
}

function formatDateTimeText(value) {
  if (!value) return ""
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, "0")
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function deviceName(device) {
  if (!device) return "—"
  const code = device.device_code || "—"
  const name = device.device_name || code
  const ch = Number(device.channel_no || 0)
  return `${name}${ch ? ` · CH${ch}` : ""}`
}

function deviceRows(devices) {
  return fulfillmentRows(devices || [], (device) => ({
    设备: deviceName(device),
    厂商: String(device.vendor || "").toUpperCase() || "—",
    类型: device.device_type || "—",
    状态: deviceOnlineText(device.online_status),
    编号: device.device_code || "—",
    上报: device.updated_at ? formatDateTimeText(device.updated_at) : "—",
  }))
}

function deviceBindingSummary(binding) {
  if (!binding) return []
  if (binding.target_type === "vehicle") {
    return [
      { label: "北斗", value: binding.summary?.beidou_bound ? deviceOnlineText(binding.beidou_device?.online_status) : "未绑定", tone: binding.summary?.beidou_bound ? "good" : "warn" },
      { label: "摄像头", value: binding.summary?.camera_count || 0 },
    ]
  }
  return [
    { label: "冷云", value: binding.summary?.elitech_bound ? (binding.elitech?.elitech_online ? "在线" : "离线") : "未绑定", tone: binding.summary?.elitech_bound ? (binding.elitech?.elitech_online ? "good" : "danger") : "warn" },
    { label: "摄像头", value: binding.summary?.camera_count || 0 },
  ]
}

const deviceBindingRows = computed(() => {
  const binding = deviceBindingState.data
  if (!binding) return []
  if (binding.target_type === "vehicle") {
    const v = binding.vehicle || {}
    return [
      {
        车辆: v.vehicle_no || "—",
        配送商: v.delivery_name || "—",
        司机: v.driver_name || "—",
        北斗: binding.summary?.beidou_bound ? deviceOnlineText(v.online_status) : "未绑定北斗",
        定位: v.coordinate_valid ? "有效" : (v.coordinate_hint || "无有效定位"),
        上报: v.reported_at || "—",
      },
    ]
  }
  const w = binding.warehouse || {}
  return [
    {
      冷库: w.name || "—",
      配送商: w.delivery_name || "—",
      冷云: binding.summary?.elitech_bound ? (w.elitech_online ? "在线" : "离线") : "未绑定冷云",
      温度: w.elitech_temperature ? `${w.elitech_temperature}℃` : "—",
      湿度: w.elitech_humidity ? `RH ${w.elitech_humidity}%` : "—",
      地址: w.address || "—",
    },
  ]
})

function extractTrackPoints(payload) {
  const candidates = [
    payload?.points,
    payload?.track_points,
    payload?.track,
    payload?.polyline,
    payload?.data?.points,
    payload?.data?.track_points,
  ]
  const rows = candidates.find((x) => Array.isArray(x)) || []
  return rows
    .map((p) => ({
      lng: Number(p.lng ?? p.longitude ?? p.x),
      lat: Number(p.lat ?? p.latitude ?? p.y),
    }))
    .filter((p) => Number.isFinite(p.lng) && Number.isFinite(p.lat))
}

const deviceTrackRawPoints = computed(() => extractTrackPoints(deviceOverlayState.data))
const deviceTrackPreviewPoints = computed(() => {
  const pts = deviceTrackRawPoints.value
  if (!pts.length) return []
  const lngs = pts.map((p) => p.lng)
  const lats = pts.map((p) => p.lat)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const dx = maxLng - minLng || 1
  const dy = maxLat - minLat || 1
  return pts.slice(-28).map((p) => ({
    x: Math.max(6, Math.min(94, ((p.lng - minLng) / dx) * 88 + 6)),
    y: Math.max(8, Math.min(92, 92 - ((p.lat - minLat) / dy) * 84)),
  }))
})

const deviceCurveRaw = computed(() => deviceOverlayState.data?.curve || {})
const deviceCurvePreviewPoints = computed(() => {
  const temps = Array.isArray(deviceCurveRaw.value.temperatureList) ? deviceCurveRaw.value.temperatureList : []
  const hums = Array.isArray(deviceCurveRaw.value.humidityList) ? deviceCurveRaw.value.humidityList : []
  const len = Math.max(temps.length, hums.length)
  if (!len) return []
  return Array.from({ length: Math.min(len, 32) }, (_, idx) => {
    const srcIdx = Math.max(0, len - Math.min(len, 32) + idx)
    const t = Number(temps[srcIdx])
    const h = Number(hums[srcIdx])
    return {
      x: len <= 1 ? 50 : (idx / (Math.min(len, 32) - 1 || 1)) * 88 + 6,
      tempY: Number.isFinite(t) ? Math.max(8, Math.min(88, 88 - ((t + 5) / 25) * 76)) : 12,
      humY: Number.isFinite(h) ? Math.max(8, Math.min(88, 88 - (h / 100) * 76)) : 12,
    }
  })
})

function closeDeviceOverlay() {
  deviceOverlayState.open = false
  deviceOverlayState.loading = false
  deviceOverlayState.type = ""
  deviceOverlayState.title = ""
  deviceOverlayState.subtitle = ""
  deviceOverlayState.error = ""
  deviceOverlayState.data = null
}

async function loadDeviceBinding(target) {
  if (!target?.type || !target?.id) {
    deviceBindingState.loading = false
    deviceBindingState.error = ""
    deviceBindingState.data = null
    return
  }
  deviceBindingState.loading = true
  deviceBindingState.error = ""
  try {
    const q = new URLSearchParams({ target_type: target.type, target_id: String(target.id) })
    deviceBindingState.data = await fetchTianshuJsonWithTimeout(`${DEVICE_BINDINGS}?${q.toString()}`, {
      timeoutMs: DEVICE_BINDING_TIMEOUT_MS,
    })
  } catch (e) {
    deviceBindingState.data = null
    deviceBindingState.error = e?.message || "设备绑定加载失败"
  } finally {
    deviceBindingState.loading = false
  }
}

async function openCameraDevicePanel(camera) {
  if (!camera?.id) return
  deviceOverlayState.open = true
  deviceOverlayState.loading = true
  deviceOverlayState.type = "camera"
  deviceOverlayState.title = deviceName(camera)
  deviceOverlayState.subtitle = "萤石摄像头直播"
  deviceOverlayState.error = ""
  deviceOverlayState.data = { camera }
  try {
    const data = await fetchTianshuJsonWithTimeout(`${DEVICE_BINDINGS}/cameras/${encodeURIComponent(camera.id)}/live-url`)
    deviceOverlayState.data = { camera, live: data }
  } catch (e) {
    deviceOverlayState.error = e?.message || "摄像头直播地址获取失败"
  } finally {
    deviceOverlayState.loading = false
  }
}

async function openBeidouTrackPanel() {
  const binding = deviceBindingState.data
  const vehicleId = binding?.vehicle?.id
  if (!vehicleId) return
  const now = Math.floor(Date.now() / 1000)
  deviceOverlayState.open = true
  deviceOverlayState.loading = true
  deviceOverlayState.type = "beidou"
  deviceOverlayState.title = binding.vehicle?.vehicle_no || "北斗轨迹"
  deviceOverlayState.subtitle = "最近 2 小时轨迹"
  deviceOverlayState.error = ""
  deviceOverlayState.data = null
  try {
    const data = await postTianshuJson(`${DEVICE_BINDINGS}/vehicles/${encodeURIComponent(vehicleId)}/beidou-history-track`, {
      start_time: now - 7200,
      end_time: now,
      force_demo: false,
    })
    deviceOverlayState.data = data
  } catch (e) {
    deviceOverlayState.error = e?.message || "北斗轨迹加载失败"
  } finally {
    deviceOverlayState.loading = false
  }
}

async function openElitechCurvePanel() {
  const binding = deviceBindingState.data
  const warehouseId = binding?.warehouse?.id
  if (!warehouseId) return
  deviceOverlayState.open = true
  deviceOverlayState.loading = true
  deviceOverlayState.type = "elitech"
  deviceOverlayState.title = binding.warehouse?.name || "冷云曲线"
  deviceOverlayState.subtitle = binding.elitech?.elitech_sn || "精创冷云"
  deviceOverlayState.error = ""
  deviceOverlayState.data = null
  try {
    const data = await fetchTianshuJsonWithTimeout(`${DEVICE_BINDINGS}/warehouses/${encodeURIComponent(warehouseId)}/elitech/realtime-curve`)
    deviceOverlayState.data = data
  } catch (e) {
    deviceOverlayState.error = e?.message || "冷云曲线加载失败"
  } finally {
    deviceOverlayState.loading = false
  }
}

function openColdChainHubDetail() {
  const s = coldChainSummary.value
  setFulfillmentDrawer({
    title: "冷链运力总览",
    subtitle: coldChainData.data_mode === "mock" ? "模拟数据 · 用于展示冷链动效" : "真实冷链设备聚合",
    conclusion: `当前冷链在线率 ${formatPct(s.online_rate)}，温控异常 ${s.temperature_alerts || 0} 项，车辆 ${s.vehicles || 0} 台，冷库 ${s.warehouses || 0} 个。`,
    summaryCards: [
      { label: "健康分", value: `${s.cold_score || 0} 分`, tone: "good" },
      { label: "在线车辆", value: `${s.online_vehicles || 0}/${s.vehicles || 0}` },
      { label: "温控异常", value: s.temperature_alerts || 0, tone: s.temperature_alerts ? "danger" : "good" },
      { label: "摄像头", value: s.cameras || 0 },
    ],
    sections: [
      { title: "冷链车辆", rows: coldVehicleRows(coldChainData.vehicles).slice(0, 20) },
      { title: "冷库温湿度", rows: coldWarehouseRows(coldChainData.warehouses).slice(0, 20) },
      { title: "异常处置队列", rows: coldEventRows(coldChainEvents.value).slice(0, 16) },
    ],
  })
}

function openColdVehicleDetail(item) {
  const realDeviceTarget = coldChainData.data_mode !== "mock" ? { type: "vehicle", id: Number(item.id) } : null
  setFulfillmentDrawer({
    title: item.vehicle_no || "冷链车辆",
    subtitle: `${item.delivery_name || "配送商"} · ${item.online_status || "offline"}`,
    conclusion: `车辆 ${item.vehicle_no || ""} 当前北斗状态 ${item.online_status || "offline"}，上报时间 ${item.reported_at || "未知"}。`,
    summaryCards: [
      { label: "北斗", value: item.online_status || "offline", tone: item.online_status === "online" ? "good" : "danger" },
      { label: "速度", value: item.speed || 0 },
      { label: "定位", value: item.coordinate_valid === false ? "无效" : "有效", tone: item.coordinate_valid === false ? "warn" : "good" },
      { label: "摄像头", value: item.cameras?.length || 0 },
    ],
    sections: [
      { title: "车辆详情", rows: coldVehicleRows([item]) },
      { title: "绑定摄像头", rows: deviceRows(item.cameras || []) },
      { title: "处置建议", rows: [{ 动作: item.online_status === "online" ? "保持轨迹监控，关注下一次上报。" : "通知司机检查北斗电源和 SIM 卡状态。", 影响: item.coordinate_valid === false ? "地图轨迹和预计到达可能失真" : "轨迹可用", 联动: "必要时同步调度员和客户经理" }] },
    ],
    deviceTarget: realDeviceTarget,
  })
}

function openColdWarehouseDetail(item) {
  const realDeviceTarget = coldChainData.data_mode !== "mock" ? { type: "warehouse", id: Number(item.id) } : null
  setFulfillmentDrawer({
    title: item.name || "冷库详情",
    subtitle: `${item.delivery_name || "配送商"} · ${item.address || "地址未填"}`,
    conclusion: `实时温度 ${item.elitech_temperature || "—"}℃，湿度 ${item.elitech_humidity || "—"}%，温控设备${item.elitech_online ? "在线" : "离线"}。`,
    summaryCards: [
      { label: "温度", value: `${item.elitech_temperature || "—"}℃`, tone: coldWarehouseAlert(item) ? "danger" : "good" },
      { label: "湿度", value: `RH ${item.elitech_humidity || "—"}%` },
      { label: "温控", value: item.elitech_online ? "在线" : "离线", tone: item.elitech_online ? "good" : "danger" },
      { label: "摄像头", value: item.cameras?.length || 0 },
    ],
    sections: [
      { title: "冷库详情", rows: coldWarehouseRows([item]) },
      { title: "绑定摄像头", rows: deviceRows(item.cameras || []) },
      { title: "阈值与处置", rows: [{ 冷藏阈值: "-2℃~8℃", 当前状态: coldWarehouseAlert(item) ? "异常" : "正常", 建议动作: coldWarehouseAlert(item) ? "复核温控设备、库门和冷机运行，并保留温度截图。" : "保持自动巡检与摄像头抽查。" }] },
    ],
    deviceTarget: realDeviceTarget,
  })
}

function openColdEventDetail(item) {
  const vehicle = coldChainData.vehicles.find((x) => Number(x.id) === Number(item.target_id))
  const warehouse = coldChainData.warehouses.find((x) => Number(x.id) === Number(item.target_id))
  if (item.target_type === "vehicle" && vehicle) {
    openColdVehicleDetail(vehicle)
    return
  }
  if (item.target_type === "warehouse" && warehouse) {
    openColdWarehouseDetail(warehouse)
    return
  }
  setFulfillmentDrawer({
    title: item.type || "冷链异常",
    subtitle: item.title || "异常事件",
    conclusion: item.description || "该冷链事件需要人工复核。",
    summaryCards: [{ label: "等级", value: item.level || "中", tone: item.level === "高" ? "danger" : "warn" }],
    sections: [{ title: "事件说明", rows: coldEventRows([item]) }],
    deviceTarget: deviceTargetFrom(item),
  })
}

function industryForecastRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    品种: row.product_name || "—",
    最新价: row.latest_price ? `${row.latest_price}` : "—",
    预测价: row.forecast_price ? `${row.forecast_price}` : "—",
    波动: `${row.change_pct || 0}%`,
    置信度: row.confidence ? `${row.confidence}%` : "—",
    状态: row.status || "—",
    产地: row.market_name || row.source || "全国行情",
  }))
}

function industryGoodsRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    商品: row.goods_name || row.product_name || "—",
    订单: row.order_count || 0,
    销量: row.total_quantity || "—",
    GMV: row.total_amount != null ? `¥${formatMoney(row.total_amount)}` : "—",
    波动: row.change_pct != null ? `${row.change_pct}%` : "—",
    品类: row.category_name || "—",
  }))
}

function industryCategoryRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    品类: row.category_name || "—",
    订单: row.order_count || 0,
    销量: row.total_quantity || "—",
    GMV: row.total_amount != null ? `¥${formatMoney(row.total_amount)}` : "—",
    占比: row.share_pct != null ? `${row.share_pct}%` : "—",
  }))
}

function industryImpactRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    标题: row.title || row.target || "采购影响",
    等级: row.level || "中",
    对象: row.target || row.product_name || row.goods_name || "—",
    影响: row.impact || row.description || "—",
    建议动作: row.level === "高" ? "优先复核采购价和供应商备货。" : "纳入今日采购观察清单。",
  }))
}

function openIndustryHubDetail() {
  const s = industrySummary.value
  setFulfillmentDrawer({
    title: "产业洞察总览",
    subtitle: industryData.data_mode === "mock" ? "模拟行情 · 业务联动演示" : "全国行情 / 平台业务联动",
    conclusion: `当前监测品类 ${s.monitored_categories || 0} 个，预测可用商品 ${s.forecast_usable || 0} 种，价格波动品种 ${s.volatile_products || 0} 种。`,
    summaryCards: [
      { label: "热销商品", value: s.hot_goods || "—" },
      { label: "波动品种", value: s.volatile_products || 0, tone: s.volatile_products ? "warn" : "good" },
      { label: "报价商品", value: s.quote_count || 0 },
      { label: "业务商品", value: s.business_goods || 0 },
    ],
    sections: [
      { title: "重点预测", rows: industryForecastRows(industryForecasts.value).slice(0, 12) },
      { title: "平台热销", rows: industryGoodsRows(industryGoods.value).slice(0, 12) },
      { title: "品类结构", rows: industryCategoryRows(industryCategories.value).slice(0, 12) },
      { title: "采购影响", rows: industryImpactRows(industryImpacts.value).slice(0, 12) },
    ],
  })
}

function openIndustryItemDetail(item, type = "品种") {
  const name = item.product_name || item.goods_name || item.category_name || item.target || "产业对象"
  const forecast = industryForecasts.value.find((x) => x.product_name === name || name.includes(x.product_name) || x.product_name?.includes(name))
  const goods = industryGoods.value.filter((x) => x.goods_name === name || x.goods_name?.includes(name) || name.includes(x.goods_name)).slice(0, 8)
  const categoryGoods = industryGoods.value.filter((x) => x.category_name && x.category_name === item.category_name).slice(0, 8)
  setFulfillmentDrawer({
    title: name,
    subtitle: `产业洞察 · ${type}`,
    conclusion: item.impact || item.description || `${name} 已接入产业洞察视图，可联动行情、预测、平台订单和采购影响。`,
    summaryCards: [
      { label: "波动", value: `${item.change_pct ?? forecast?.change_pct ?? 0}%`, tone: Math.abs(Number(item.change_pct ?? forecast?.change_pct) || 0) >= 5 ? "warn" : "good" },
      { label: "预测价", value: item.forecast_price || forecast?.forecast_price || "—" },
      { label: "置信度", value: item.confidence || forecast?.confidence ? `${item.confidence || forecast?.confidence}%` : "—" },
      { label: "关联订单", value: item.order_count || goods.reduce((sum, x) => sum + Number(x.order_count || 0), 0) || "—" },
    ],
    sections: [
      { title: "行情预测", rows: industryForecastRows(forecast ? [forecast] : []) },
      { title: "平台关联商品", rows: industryGoodsRows(goods.length ? goods : categoryGoods.length ? categoryGoods : [item]) },
      { title: "采购影响", rows: industryImpactRows(industryImpacts.value.filter((x) => x.target === name || name.includes(x.target)).slice(0, 6)) },
      { title: "联动判断", rows: [{ 对象: name, 采购建议: Math.abs(Number(item.change_pct ?? forecast?.change_pct) || 0) >= 5 ? "价格波动较大，建议锁价或拆分采购批次。" : "价格波动可控，按当前合约和订单需求推进。", 经营联动: item.total_amount != null ? `平台 GMV ¥${formatMoney(item.total_amount)}` : "关注订单品类需求变化" }] },
    ],
  })
}

function cityDistrictRows(rows) {
  return fulfillmentRows(rows, (row) => ({
    区县: row.district_name || "—",
    订单: row.order_count || 0,
    GMV: row.gmv != null ? `¥${formatMoney(row.gmv)}` : "—",
    客户: row.client_count || 0,
    食堂: row.canteen_count || 0,
    风险: row.risk_count || 0,
    履约: row.fulfillment_count || 0,
    增长: `${row.growth_pct || 0}%`,
  }))
}

function cityAdviceRows(rows) {
  return fulfillmentRows(rows, (x) => ({
    区县: x.district_name || x.customer_name || "—",
    覆盖判断: (x.client_count || 0) <= 2 ? "客户覆盖薄弱" : "覆盖稳定",
    履约判断: (x.fulfillment_count || 0) ? `${x.fulfillment_count} 个履约对象/车次` : "履约样本不足",
    风险建议: (x.risk_count || 0) ? "优先复核异常订单、退单和配送风险。" : "暂无高风险，保持服务频次。",
    增长建议: Number(x.growth_pct || 0) >= 10 ? "可作为增长样板区继续扩点。" : "建议跟踪客户活跃与品类结构。",
  }))
}

function openCityProfileHubDetail() {
  const s = cityProfileSummary.value
  setFulfillmentDrawer({
    title: "城市画像总览",
    subtitle: cityProfileData.data_mode === "mock" ? "模拟区域画像 · 展示热力" : "区县经营 / 覆盖 / 风险聚合",
    conclusion: `当前覆盖区县 ${s.district_cover_count || 0} 个，活跃食堂 ${s.active_canteens || 0} 个，区域风险事件 ${s.risk_events || 0} 项。`,
    summaryCards: [
      { label: "GMV", value: `¥${compactMoney(s.total_gmv)}` },
      { label: "订单", value: s.total_orders || 0 },
      { label: "客户", value: s.active_clients || 0 },
      { label: "风险", value: s.risk_events || 0, tone: s.risk_events ? "warn" : "good" },
    ],
    sections: [
      { title: "区县经营排行", rows: cityDistrictRows(cityDistricts.value).slice(0, 16) },
      { title: "增长区县", rows: cityDistrictRows(cityGrowthDistricts.value).slice(0, 8) },
      { title: "风险密度", rows: cityDistrictRows(cityRiskDistricts.value).slice(0, 8) },
      { title: "区域建议", rows: cityAdviceRows(cityDistricts.value).slice(0, 10) },
    ],
  })
}

function openCityDistrictDetail(item) {
  const name = item.district_name || item.customer_name || "区县画像"
  const row = cityDistricts.value.find((x) => x.district_name === name) || item
  setFulfillmentDrawer({
    title: name,
    subtitle: "城市画像 · 区县下钻",
    conclusion: item.description || `${name} 近7日订单 ${row.order_count || 0} 单，GMV ¥${formatMoney(row.gmv || 0)}，风险事件 ${row.risk_count || 0} 项。`,
    summaryCards: [
      { label: "GMV", value: `¥${compactMoney(row.gmv)}` },
      { label: "订单", value: row.order_count || 0 },
      { label: "食堂", value: row.canteen_count || 0 },
      { label: "风险", value: row.risk_count || 0, tone: row.risk_count ? "warn" : "good" },
    ],
    sections: [
      { title: "区县经营", rows: cityDistrictRows([row]) },
      { title: "增长/薄弱建议", rows: cityAdviceRows([row]) },
      { title: "区域联动", rows: [{ 区县: name, 地图动作: "点击区县可聚焦热力与点位", 业务动作: (row.risk_count || 0) ? "先处理风险密度，再推进覆盖扩张。" : "优先推进客户覆盖和履约稳定性。" }] },
    ],
  })
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
  if (ev.data?.type === "tianshu-fullscreen-state") {
    spectacleFullscreen.value = Boolean(ev.data.value)
    scheduleTianshuViewportLayoutRefresh()
    return
  }
  if (ev.data?.type === "tianshu-director-control") {
    const action = String(ev.data.action || "")
    if (action === "start") {
      void startTianshuDirector()
    } else if (action === "stop") {
      stopTianshuDirector()
    } else if (action === "toggle") {
      void toggleTianshuDirector()
    }
  }
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

/** 最近一次拉到的真实 delivery 点位，loadFlylines 计算 mock 飞线时取用 */
let lastRealDeliveries = []

async function loadTodayOrderPillars() {
  const w = getMapWorld()
  if (!w || typeof w.setOrderPillars !== "function") {
    return
  }
  try {
    const { todayIso } = todayYesterdayIso()
    // role=both 让后端把客户(蓝)与配送商(金)真实点位都返回；map.js 已按 point.role 着色
    const url = `${COCKPIT_MAP_POINTS}?start_date=${encodeURIComponent(todayIso)}&end_date=${encodeURIComponent(todayIso)}&limit=500&role=both`
    const d = await fetchJson(url)
    const realPts = Array.isArray(d?.points) ? d.points : []
    lastRealDeliveries = realPts.filter((p) => String(p?.role || "").toLowerCase() === "delivery")
    const mockPts = mockStream.isRunning() ? mockStream.mockPoints.value : []
    const pts = mockPts.length ? [...realPts, ...mockPts] : realPts
    const fp = fingerprintOrderMapPoints(pts) + (mockPts.length ? `|mock:${mockPts.length}` : "")
    if (fp === lastOrderPillarsFingerprint) return
    lastOrderPillarsFingerprint = fp
    w.setOrderPillars(pts)
  } catch (e) {
    if (!isTianshuAuthMissingError(e)) console.warn("[gdMap] 今日订单光柱:", e?.message || e)
    lastOrderPillarsFingerprint = undefined
    w.setOrderPillars([])
  }
}

/**
 * 业务语义：金色光柱（配送商）→ 蓝色光柱（客户）。
 * 真实飞线由后端按区间内 (delivery, client) 订单对聚合返回；mock 模式叠加 mock 飞线作为补量。
 */
async function loadFlylines() {
  const w = getMapWorld()
  if (!w || typeof w.setFlylines !== "function") return
  let realLines = []
  try {
    const { todayIso } = todayYesterdayIso()
    const url = `${COCKPIT_FLYLINES}?start_date=${encodeURIComponent(todayIso)}&end_date=${encodeURIComponent(todayIso)}&limit=60`
    const d = await fetchJson(url)
    realLines = Array.isArray(d?.lines) ? d.lines : []
  } catch (e) {
    if (!isTianshuAuthMissingError(e)) console.warn("[gdMap] 飞线:", e?.message || e)
  }
  const mockLines = mockStream.isRunning() && typeof mockStream.buildMockFlylines === "function"
    ? mockStream.buildMockFlylines(lastRealDeliveries)
    : []
  const all = mockLines.length ? [...realLines, ...mockLines] : realLines
  w.setFlylines(all)
}

function setOverviewKpiCards() {
  state.totalView = [
    {
      icon: "xiaoshoujine",
      zh: "今日 GMV",
      en: "Today's GMV",
      value: state.totalView[0]?.value || 0,
      unit: "元",
      decimals: 2,
    },
    {
      icon: "zongxiaoliang",
      zh: "今日下单数",
      en: "Today's orders",
      value: state.totalView[1]?.value || 0,
      unit: "单",
      decimals: 0,
    },
  ]
}

function setRiskKpiCards() {
  const k = riskKpis.value
  state.totalView = [
    {
      icon: "xiaoshoujine",
      zh: "待处置风险",
      en: "Pending risks",
      value: k.pending_count,
      unit: "项",
      decimals: 0,
    },
    {
      icon: "zongxiaoliang",
      zh: "开放告警",
      en: "Open alerts",
      value: k.open_alerts,
      unit: "条",
      decimals: 0,
    },
  ]
}

function fingerprintRiskPoints(pts) {
  if (!Array.isArray(pts) || pts.length === 0) return ""
  return pts
    .map((p) => {
      const lng = Number(p.lng)
      const lat = Number(p.lat)
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
      return `${p.risk_type || "risk"}:${p.order_id || p.order_sn || p.description || ""}:${lng.toFixed(5)}:${lat.toFixed(5)}:${p.risk_level || ""}:${Math.round(Number(p.gmv) || 0)}`
    })
    .filter(Boolean)
    .sort()
    .join("|")
}

let lastRiskFingerprint = undefined

function renderRiskModeLayer({ force = false } = {}) {
  const w = getMapWorld()
  const pts = riskMapPointsByMode.value
  const fp = `${riskMode.value}|${fingerprintRiskPoints(pts)}`
  if ((force || fp !== lastRiskFingerprint) && w?.setOrderPillars) {
    lastRiskFingerprint = fp
    w.setOrderPillars(pts)
    w.setFlylines?.([])
  }
}

async function loadRiskWarningOverview({ force = false } = {}) {
  const w = getMapWorld()
  riskLoading.value = true
  riskError.value = ""
  setRiskKpiCards()
  try {
    const q = new URLSearchParams({ limit: "60" })
    if (chartQueryDistrict.value) q.set("district_name", chartQueryDistrict.value)
    let d = await fetchJson(`${RISK_WARNING_OVERVIEW}?${q}`, { bypassCache: force })
    if (!Array.isArray(d?.risk_points) || !d.risk_points.length) {
      d = buildRiskMockData("empty")
    }
    applyRiskPayload(d)
    setRiskKpiCards()
    renderRiskModeLayer({ force })
  } catch (e) {
    applyRiskPayload(buildRiskMockData("fallback"))
    setRiskKpiCards()
    const msg = e?.message || String(e)
    riskError.value = msg === "Not Found" || isTianshuAuthMissingError(e) ? "" : msg
    renderRiskModeLayer({ force: true })
  } finally {
    riskLoading.value = false
  }
}

async function refreshActiveMapLayer({ force = false } = {}) {
  if (activeView.value === VIEW_RISK_WARNING) {
    await loadRiskWarningOverview({ force })
    return
  }
  if (activeView.value === VIEW_FULFILLMENT) {
    await loadFulfillmentOverview({ force })
    return
  }
  if (activeView.value === VIEW_COLD_CHAIN) {
    await loadColdChainOverview({ force })
    return
  }
  if (activeView.value === VIEW_INDUSTRY_INSIGHTS) {
    await loadIndustryInsightsOverview({ force })
    return
  }
  if (activeView.value === VIEW_CITY_PROFILE) {
    await loadCityProfileOverview({ force })
    return
  }
  await loadTodayOrderPillars()
  await loadFlylines()
}

async function switchTianshuView(view) {
  if (activeView.value === view) return
  closeTianshuOverlays()
  activeView.value = view
  if (view === VIEW_RISK_WARNING) {
    lastRiskFingerprint = undefined
    await nextTick()
    await loadRiskWarningOverview({ force: true })
  } else if (view === VIEW_FULFILLMENT) {
    lastFulfillmentFingerprint = undefined
    await nextTick()
    await loadFulfillmentOverview({ force: true })
  } else if (view === VIEW_COLD_CHAIN) {
    lastColdChainFingerprint = undefined
    await nextTick()
    await loadColdChainOverview({ force: true })
  } else if (view === VIEW_INDUSTRY_INSIGHTS) {
    lastIndustryFingerprint = undefined
    await nextTick()
    await loadIndustryInsightsOverview({ force: true })
  } else if (view === VIEW_CITY_PROFILE) {
    lastCityProfileFingerprint = undefined
    await nextTick()
    await loadCityProfileOverview({ force: true })
  } else {
    setOverviewKpiCards()
    lastOrderPillarsFingerprint = undefined
    await nextTick()
    await loadTodayKpi()
    await loadTodayOrderPillars()
    await loadFlylines()
  }
  requestAnimationFrame(() => emitter.$emit("tianshuChartsResize"))
}

async function onTianshuOrderPillarClick(payload) {
  if (String(payload?.role || "").toLowerCase() === "risk") {
    openRiskPointDetail(payload)
    return
  }
  if (String(payload?.role || "").toLowerCase() === "industry") {
    openIndustryItemDetail(payload, payload.industry_type === "goods" ? "商品" : "价格品种")
    return
  }
  if (String(payload?.role || "").toLowerCase() === "city_profile") {
    openCityDistrictDetail(payload)
    return
  }
  if (String(payload?.role || "").toLowerCase() === "cold_chain") {
    if (payload.cold_type === "vehicle") {
      const vehicle = coldChainData.vehicles.find((item) => Number(item.id) === Number(payload.vehicle_id))
      if (vehicle) {
        openColdVehicleDetail(vehicle)
        return
      }
    }
    if (payload.cold_type === "warehouse") {
      const warehouse = coldChainData.warehouses.find((item) => Number(item.id) === Number(payload.warehouse_id))
      if (warehouse) {
        openColdWarehouseDetail(warehouse)
        return
      }
    }
    setFulfillmentDrawer({
      title: payload.customer_name || "冷链点位",
      subtitle: coldTypeText(payload.cold_type),
      conclusion: payload.description || "该点位属于冷链运力地图层。",
      summaryCards: [
        { label: "状态", value: payload.status || "—" },
        { label: "温度", value: `${payload.temperature || "—"}℃` },
        { label: "湿度", value: `RH ${payload.humidity || "—"}%` },
      ],
      sections: [{ title: "点位信息", rows: [{ 地址: payload.address || "—", 对象: payload.customer_name || "—", 类型: coldTypeText(payload.cold_type) }] }],
    })
    return
  }
  if (String(payload?.role || "").toLowerCase() === "fulfillment") {
    const trip = fulfillmentData.trips.find((item) => Number(item.id) === Number(payload.trip_id))
    if (trip) {
      openFulfillmentTripDetail(trip)
      return
    }
    const order = fulfillmentData.orders_detail.find((item) => Number(item.order_id) === Number(payload.order_id))
    setFulfillmentDrawer({
      title: payload.route_no || payload.order_sn || "履约点位",
      subtitle: payload.customer_name || payload.address || "地图点位下钻",
      conclusion: payload.description || "该点位属于供应链履约地图层。",
      summaryCards: [
        { label: "状态", value: payload.status || "—" },
        { label: "订单", value: payload.order_sn || "—" },
        { label: "金额", value: `¥${formatMoney(payload.gmv)}` },
      ],
      sections: [
        { title: "关联订单", rows: fulfillmentOrderRows(order ? [order] : []) },
        { title: "点位信息", rows: [{ 地址: payload.address || "—", 客户: payload.customer_name || "—", 车次: payload.route_no || "—" }] },
      ],
    })
    return
  }
  const addr = (payload?.address || "").trim()
  const mid = Number(payload?.member_id)
  const hasMember = Number.isFinite(mid) && mid > 0
  const mockId = typeof payload?._mockId === "string" ? payload._mockId : ""

  if (!addr && !hasMember && !mockId) return

  orderDetailScope.value = "address"
  orderDetailAddress.value = addr || `会员 #${mid}`
  orderDetailOpen.value = true
  orderDetailLoading.value = true
  orderDetailError.value = ""
  orderDetailRows.value = []

  // 模拟光柱：从内存读，绕过 HTTP，避免后端污染
  if (mockId) {
    try {
      const rows = mockStream.getMockOrdersByMockId(mockId)
      orderDetailRows.value = rows
    } catch (e) {
      orderDetailError.value = e?.message || String(e)
    } finally {
      orderDetailLoading.value = false
    }
    return
  }

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
    mock: mockStream.isRunning(),
  }),
  ({ g, o, on, mock }) => {
    // mock 走合成事件不连真实 WS，wsConnected 始终 false；此时也允许写入 KPI 卡片
    if (activeView.value !== VIEW_OVERVIEW) return
    if (!on && !mock) return
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
    () => void refreshActiveMapLayer(),
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
  document.addEventListener("visibilitychange", onPageVisibility)
  document.addEventListener("pointerdown", onBottomTrayPointerCapture, true)
  bottomMenuRef.value?.addEventListener("pointerdown", onBottomTrayNativeEvent)
  bottomMenuRef.value?.addEventListener("click", onBottomTrayNativeEvent)
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
  stopTianshuDirector()
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
  document.removeEventListener("visibilitychange", onPageVisibility)
  document.removeEventListener("pointerdown", onBottomTrayPointerCapture, true)
  bottomMenuRef.value?.removeEventListener("pointerdown", onBottomTrayNativeEvent)
  bottomMenuRef.value?.removeEventListener("click", onBottomTrayNativeEvent)
  window.removeEventListener("message", onTianshuShellFullscreenMessage)
  // 任何离开此页都强制干掉模拟数据（用户硬约束：关闭页面要全部清掉）
  if (mockStream.isRunning()) {
    mockStream.stop()
  }
})

/**
 * HTTP 与 WS 单量一致但 GMV 偏差 >0.5 元时，以 kpi-summary（库表）校正 liveGmv，避免多 worker Hub 不同步。
 */
async function reconcileLiveKpiDriftWithHttp() {
  if (activeView.value !== VIEW_OVERVIEW) return
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
  if (activeView.value !== VIEW_OVERVIEW) return
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
    if (!ws || opsConsole.liveGmv.value == null || opsConsole.liveOrderCount.value == null) {
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
  closeTianshuOverlays()
  state.activeIndex = index
  if (index === "6") {
    void switchTianshuView(VIEW_RISK_WARNING)
  } else if (index === "2") {
    void switchTianshuView(VIEW_FULFILLMENT)
  } else if (index === "3") {
    void switchTianshuView(VIEW_COLD_CHAIN)
  } else if (index === "4") {
    void switchTianshuView(VIEW_CITY_PROFILE)
  } else if (index === "5") {
    void switchTianshuView(VIEW_INDUSTRY_INSIGHTS)
  } else if (index === "1") {
    void switchTianshuView(VIEW_OVERVIEW)
  }
}

function onBottomTraySelect(item) {
  if (!item || item === bottomTrayActive.value) return
  closeTianshuOverlays()
  activeSubModeByView[activeView.value] = item
  if (activeView.value === VIEW_COLD_CHAIN) {
    renderColdChainModeLayer({ force: true })
  } else if (activeView.value === VIEW_FULFILLMENT) {
    renderFulfillmentModeLayer({ force: true })
  } else if (activeView.value === VIEW_CITY_PROFILE) {
    renderCityProfileModeLayer({ force: true })
  } else if (activeView.value === VIEW_INDUSTRY_INSIGHTS) {
    renderIndustryModeLayer({ force: true })
  } else if (activeView.value === VIEW_RISK_WARNING) {
    renderRiskModeLayer({ force: true })
  }
  requestAnimationFrame(() => emitter.$emit("tianshuChartsResize"))
}

function getBottomTrayItemFromEvent(ev) {
  const target = ev.target?.closest?.("[data-bottom-tray-item]")
  if (!target) return ""
  const item = String(target.getAttribute("data-bottom-tray-item") || target.textContent || "").trim()
  return bottomTrayItems.value.includes(item) ? item : ""
}

function onBottomTrayContainerClick(ev) {
  const item = getBottomTrayItemFromEvent(ev)
  if (!item) return
  onBottomTraySelect(item)
}

function onBottomTrayNativeEvent(ev) {
  const item = getBottomTrayItemFromEvent(ev)
  if (!item) return
  ev.preventDefault?.()
  onBottomTraySelect(item)
}

function onBottomTrayPointerCapture(ev) {
  const item = getBottomTrayItemFromEvent(ev)
  if (!item) return
  onBottomTraySelect(item)
}
// 地图时间线播完时触发（大屏 UI 已默认可见，此处保留占位便于以后加动效）
function handleMapPlayComplete() {
  void refreshActiveMapLayer()
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
  z-index: 26;
  display: flex;
  justify-content: center;
  pointer-events: auto;
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
.large-screen-wrap .bottom-tray {
  z-index: 100002;
  pointer-events: auto;
}
.large-screen-wrap .bottom-tray .bottom-menu {
  pointer-events: auto;
}
.large-screen-wrap .bottom-tray .bottom-svg-line-left,
.large-screen-wrap .bottom-tray .bottom-tray-arrow {
  pointer-events: none;
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
  pointer-events: none;
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
  pointer-events: auto;
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

.tianshu-order-hover-dock__head--risk {
  color: #ffd6a3;
  text-shadow:
    0 0 12px rgba(248, 113, 113, 0.45),
    0 0 22px rgba(249, 115, 22, 0.32);
}
.tianshu-order-hover-dock__hq-tag--risk {
  color: rgba(254, 215, 170, 0.86);
}
.tianshu-order-hover-dock__head--fulfillment {
  color: #d9feff;
  text-shadow:
    0 0 14px rgba(34, 211, 238, 0.45),
    0 0 24px rgba(245, 158, 11, 0.2);
}
.tianshu-order-hover-dock__hq-tag--fulfillment {
  color: rgba(190, 245, 255, 0.88);
}
.tianshu-order-hover-dock__head--cold {
  color: #f0fdff;
  text-shadow:
    0 0 16px rgba(167, 243, 255, 0.5),
    0 0 26px rgba(192, 132, 252, 0.24);
}
.tianshu-order-hover-dock__hq-tag--cold {
  color: rgba(207, 250, 254, 0.88);
}

.tianshu-fulfillment-card {
  position: relative;
  flex: 1;
  min-height: 0;
  margin-bottom: 12px;
  padding: 16px 16px 14px;
  pointer-events: auto;
  overflow: hidden;
  border: 1px solid rgba(34, 211, 238, 0.28);
  background:
    linear-gradient(135deg, rgba(8, 145, 178, 0.18), transparent 36%),
    linear-gradient(180deg, rgba(8, 25, 44, 0.74), rgba(3, 10, 20, 0.8));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.035),
    0 0 30px rgba(34, 211, 238, 0.08);
  backdrop-filter: blur(4px);
  cursor: default;
  &::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(103, 232, 249, 0.88), transparent);
  }
}
.tianshu-fulfillment-card--command {
  flex: 1.12;
  cursor: pointer;
}
.tianshu-fulfillment-card--list {
  flex: 1.45;
}
.tianshu-fulfillment-card--split {
  flex: 0.82;
}
.tianshu-fulfillment-card__head {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  span {
    font-size: 17px;
    font-weight: 800;
    color: #e9feff;
    text-shadow: 0 0 14px rgba(34, 211, 238, 0.28);
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 12px;
    color: rgba(250, 204, 21, 0.82);
    letter-spacing: 0.14em;
  }
}
.tianshu-fulfillment-core {
  position: relative;
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 14px;
  align-items: center;
}
.tianshu-fulfillment-core__ring {
  position: relative;
  width: 142px;
  height: 142px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(6, 20, 35, 0.94) 0 50%, transparent 51%),
    conic-gradient(from 210deg, #22d3ee, #67e8f9, #facc15, #22d3ee);
  box-shadow:
    0 0 28px rgba(34, 211, 238, 0.2),
    inset 0 0 28px rgba(0, 0, 0, 0.55);
  animation: tianshuFulfillmentPulse 2.2s ease-in-out infinite;
  span {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 42px;
    font-weight: 800;
    color: #f4feff;
    line-height: 1;
    text-shadow: 0 0 18px rgba(103, 232, 249, 0.48);
  }
  small {
    margin-top: 7px;
    font-size: 12px;
    color: rgba(188, 240, 255, 0.78);
  }
}
.tianshu-fulfillment-core__metrics {
  display: grid;
  gap: 9px;
  div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 10px;
    border: 1px solid rgba(103, 232, 249, 0.15);
    background: linear-gradient(90deg, rgba(34, 211, 238, 0.1), rgba(5, 18, 30, 0.36));
  }
  span {
    font-size: 12px;
    color: rgba(190, 230, 240, 0.78);
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 19px;
    color: #bdfcff;
  }
}
.tianshu-fulfillment-funnel {
  display: grid;
  gap: 8px;
}
.tianshu-fulfillment-funnel__row,
.tianshu-fulfillment-supplier,
.tianshu-fulfillment-trip,
.tianshu-fulfillment-mini-list button {
  width: 100%;
  border: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}
.tianshu-fulfillment-funnel__row {
  display: grid;
  grid-template-columns: 74px 1fr 54px 48px;
  align-items: center;
  gap: 9px;
  padding: 6px 0;
  background: transparent;
  span {
    font-size: 13px;
    color: rgba(225, 250, 255, 0.92);
  }
  i {
    position: relative;
    height: 9px;
    overflow: hidden;
    border-radius: 999px;
    background: rgba(34, 211, 238, 0.1);
  }
  em {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #0891b2, #67e8f9, #facc15);
    box-shadow: 0 0 16px rgba(103, 232, 249, 0.32);
    animation: tianshuFulfillmentBar 2.8s ease-in-out infinite;
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 13px;
    color: #dffcff;
    text-align: right;
  }
  small {
    font-size: 12px;
    color: rgba(250, 204, 21, 0.82);
    text-align: right;
  }
}
.tianshu-fulfillment-suppliers,
.tianshu-fulfillment-trips,
.tianshu-fulfillment-mini-list {
  display: grid;
  gap: 8px;
}
.tianshu-fulfillment-supplier,
.tianshu-fulfillment-trip,
.tianshu-fulfillment-mini-list button {
  position: relative;
  padding: 10px 11px;
  border: 1px solid rgba(103, 232, 249, 0.14);
  background:
    linear-gradient(90deg, rgba(34, 211, 238, 0.12), rgba(6, 18, 30, 0.5)),
    rgba(2, 8, 16, 0.42);
  transition:
    transform 0.18s ease,
    border-color 0.18s ease,
    box-shadow 0.18s ease;
  &:hover {
    transform: translateX(-3px);
    border-color: rgba(103, 232, 249, 0.38);
    box-shadow: 0 0 18px rgba(34, 211, 238, 0.12);
  }
}
.tianshu-fulfillment-supplier {
  display: grid;
  grid-template-columns: 1fr 36px;
  gap: 4px 10px;
  span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #eefeff;
    font-weight: 700;
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    color: #facc15;
    text-align: right;
    font-size: 20px;
  }
  small {
    grid-column: 1 / -1;
    color: rgba(190, 230, 240, 0.72);
    font-size: 12px;
  }
}
.tianshu-fulfillment-trip {
  div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 5px;
  }
  span {
    color: #eefeff;
    font-weight: 800;
    letter-spacing: 0.04em;
  }
  b {
    padding: 2px 7px;
    border: 1px solid rgba(103, 232, 249, 0.26);
    color: #a5f3fc;
    background: rgba(34, 211, 238, 0.1);
    font-size: 12px;
  }
  p,
  small {
    display: block;
    margin: 0;
    color: rgba(198, 232, 242, 0.74);
    font-size: 12px;
    line-height: 1.45;
  }
  &.is-blocked {
    border-color: rgba(245, 158, 11, 0.42);
    background:
      linear-gradient(90deg, rgba(245, 158, 11, 0.18), rgba(6, 18, 30, 0.55)),
      rgba(2, 8, 16, 0.42);
    b {
      color: #fde68a;
      border-color: rgba(245, 158, 11, 0.42);
      background: rgba(245, 158, 11, 0.12);
    }
  }
  &.is-moving b {
    color: #67e8f9;
  }
}
.tianshu-fulfillment-mini-list button {
  display: grid;
  grid-template-columns: 1fr 46px;
  gap: 4px 8px;
  padding: 8px 10px;
  span {
    color: #eaffff;
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  b {
    color: #67e8f9;
    text-align: right;
    font-family: D-DIN, ui-monospace, monospace;
  }
  small {
    grid-column: 1 / -1;
    color: rgba(198, 232, 242, 0.72);
    font-size: 12px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
.tianshu-fulfillment-mini-list--risk button {
  border-color: rgba(245, 158, 11, 0.22);
  b {
    color: #fbbf24;
  }
}
.tianshu-fulfillment-empty {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(184, 220, 232, 0.72);
}
.tianshu-fulfillment-mode-hint {
  margin: -2px 0 10px;
  padding: 7px 10px;
  border: 1px solid rgba(103, 232, 249, 0.14);
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.1), rgba(2, 8, 16, 0.32));
  color: rgba(207, 250, 254, 0.78);
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0.04em;
}

.tianshu-cold-card {
  border-color: rgba(167, 243, 255, 0.3);
  background:
    linear-gradient(135deg, rgba(14, 165, 233, 0.16), transparent 34%),
    linear-gradient(180deg, rgba(8, 24, 42, 0.75), rgba(3, 8, 18, 0.82));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.035),
    0 0 32px rgba(125, 211, 252, 0.1);
  &::before {
    background: linear-gradient(90deg, transparent, rgba(207, 250, 254, 0.9), rgba(192, 132, 252, 0.55), transparent);
  }
}
.tianshu-cold-mode-hint {
  margin: -2px 0 10px;
  padding: 7px 10px;
  border: 1px solid rgba(167, 243, 255, 0.14);
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.1), rgba(2, 8, 16, 0.32));
  color: rgba(207, 250, 254, 0.78);
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0.04em;
}
.tianshu-cold-mode-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 0 0 10px;
  div {
    min-width: 0;
    padding: 7px 8px;
    border: 1px solid rgba(167, 243, 255, 0.16);
    background:
      linear-gradient(180deg, rgba(125, 211, 252, 0.1), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
    box-shadow: inset 0 0 12px rgba(167, 243, 255, 0.04);
  }
  span {
    display: block;
    color: rgba(207, 250, 254, 0.62);
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  b {
    display: block;
    margin-top: 4px;
    color: #ecfeff;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 16px;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .is-good b {
    color: #a7f3ff;
  }
  .is-warn b {
    color: #fde68a;
  }
  .is-danger {
    border-color: rgba(251, 113, 133, 0.28);
    background:
      linear-gradient(180deg, rgba(251, 113, 133, 0.14), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
    b {
      color: #fecdd3;
    }
  }
}
.tianshu-cold-core__ring {
  background:
    radial-gradient(circle, rgba(5, 18, 31, 0.95) 0 50%, transparent 51%),
    conic-gradient(from 210deg, #a7f3ff, #7dd3fc, #c084fc, #a7f3ff);
  box-shadow:
    0 0 30px rgba(167, 243, 255, 0.2),
    inset 0 0 30px rgba(0, 0, 0, 0.55);
}
.tianshu-cold-warehouse-grid {
  display: grid;
  gap: 8px;
}
.tianshu-cold-warehouse {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr 58px;
  gap: 4px 9px;
  padding: 10px 11px;
  border: 1px solid rgba(167, 243, 255, 0.16);
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
  background:
    linear-gradient(90deg, rgba(125, 211, 252, 0.12), rgba(6, 18, 30, 0.5)),
    rgba(2, 8, 16, 0.42);
  span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #f0fdff;
    font-weight: 800;
  }
  b {
    color: #cffafe;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 18px;
    text-align: right;
  }
  small {
    grid-column: 1 / -1;
    color: rgba(207, 250, 254, 0.72);
    font-size: 12px;
  }
  &.is-alert {
    border-color: rgba(216, 180, 254, 0.42);
    background:
      linear-gradient(90deg, rgba(126, 34, 206, 0.18), rgba(14, 165, 233, 0.08)),
      rgba(2, 8, 16, 0.46);
    b {
      color: #f5d0fe;
    }
  }
}
.tianshu-cold-alert-meter {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 12px 4px;
  span {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 54px;
    line-height: 1;
    color: #f5d0fe;
    text-shadow: 0 0 24px rgba(192, 132, 252, 0.38);
  }
  p {
    margin: 8px 0 6px;
    color: #f0fdff;
    font-weight: 800;
    letter-spacing: 0.08em;
  }
  small {
    color: rgba(207, 250, 254, 0.72);
    font-size: 12px;
  }
}
.tianshu-cold-vehicle b {
  color: #cffafe;
}

.tianshu-order-hover-dock__head--industry {
  color: #fef3c7;
  text-shadow: 0 0 16px rgba(250, 204, 21, 0.35);
}
.tianshu-order-hover-dock__head--city {
  color: #cffafe;
  text-shadow: 0 0 16px rgba(34, 211, 238, 0.35);
}
.tianshu-order-hover-dock__hq-tag--industry {
  color: rgba(253, 230, 138, 0.9);
}
.tianshu-order-hover-dock__hq-tag--city {
  color: rgba(165, 243, 252, 0.9);
}

.tianshu-industry-card {
  border-color: rgba(250, 204, 21, 0.3);
  background:
    radial-gradient(circle at 78% 10%, rgba(168, 85, 247, 0.16), transparent 32%),
    linear-gradient(135deg, rgba(250, 204, 21, 0.12), transparent 36%),
    linear-gradient(180deg, rgba(10, 24, 38, 0.78), rgba(4, 8, 18, 0.86));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.035),
    0 0 32px rgba(250, 204, 21, 0.1);
  &::before {
    background: linear-gradient(90deg, transparent, rgba(250, 204, 21, 0.85), rgba(34, 211, 238, 0.72), transparent);
  }
}
.tianshu-industry-mode-hint {
  margin: -2px 0 10px;
  padding: 7px 10px;
  border: 1px solid rgba(250, 204, 21, 0.16);
  background: linear-gradient(90deg, rgba(250, 204, 21, 0.1), rgba(2, 8, 16, 0.32));
  color: rgba(254, 243, 199, 0.78);
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0.04em;
}
.tianshu-industry-mode-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 0 0 10px;
  div {
    min-width: 0;
    padding: 7px 8px;
    border: 1px solid rgba(250, 204, 21, 0.16);
    background:
      linear-gradient(180deg, rgba(250, 204, 21, 0.1), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
  }
  span {
    display: block;
    color: rgba(254, 243, 199, 0.62);
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  b {
    display: block;
    margin-top: 4px;
    color: #fef3c7;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 16px;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .is-good b {
    color: #fde68a;
  }
  .is-warn b {
    color: #fbbf24;
  }
  .is-danger {
    border-color: rgba(251, 146, 60, 0.34);
    background:
      linear-gradient(180deg, rgba(249, 115, 22, 0.14), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
    b {
      color: #fed7aa;
    }
  }
}
.tianshu-industry-orbit {
  display: grid;
  grid-template-columns: 118px 1fr;
  gap: 14px;
  align-items: center;
}
.tianshu-industry-orbit__core {
  position: relative;
  height: 118px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(4, 12, 20, 0.96) 0 48%, transparent 49%),
    conic-gradient(from 160deg, #facc15, #22d3ee, #a855f7, #facc15);
  box-shadow: 0 0 32px rgba(250, 204, 21, 0.2), inset 0 0 28px rgba(0, 0, 0, 0.5);
  span {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 42px;
    color: #fef3c7;
  }
  small {
    position: absolute;
    bottom: 28px;
    color: rgba(254, 243, 199, 0.72);
    font-size: 12px;
  }
}
.tianshu-industry-orbit__metrics,
.tianshu-city-core__metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  div {
    min-width: 0;
    padding: 9px 10px;
    border: 1px solid rgba(103, 232, 249, 0.13);
    background: rgba(2, 8, 16, 0.42);
  }
  span {
    display: block;
    color: rgba(190, 226, 236, 0.68);
    font-size: 12px;
  }
  b {
    display: block;
    margin-top: 4px;
    color: #f0fdff;
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}
.tianshu-industry-price-list,
.tianshu-city-districts {
  display: grid;
  gap: 8px;
}
.tianshu-industry-price-list button,
.tianshu-city-districts button {
  width: 100%;
  border: 1px solid rgba(103, 232, 249, 0.14);
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
  background: rgba(2, 8, 16, 0.42);
}
.tianshu-industry-price-list button {
  display: grid;
  grid-template-columns: 1fr 64px;
  gap: 4px 10px;
  padding: 10px 11px;
  &.is-volatile {
    border-color: rgba(250, 204, 21, 0.36);
    background: linear-gradient(90deg, rgba(250, 204, 21, 0.12), rgba(168, 85, 247, 0.08));
  }
  span {
    color: #f8fafc;
    font-weight: 800;
  }
  b {
    color: #fef3c7;
    text-align: right;
    font-family: D-DIN, ui-monospace, monospace;
  }
  small {
    grid-column: 1 / -1;
    color: rgba(253, 230, 138, 0.72);
    font-size: 12px;
  }
}
.tianshu-industry-impact button b {
  color: #facc15;
}
.tianshu-industry-category b,
.tianshu-industry-goods b {
  color: #fef3c7;
}

.tianshu-city-card {
  border-color: rgba(34, 211, 238, 0.3);
  background:
    radial-gradient(circle at 80% 10%, rgba(14, 165, 233, 0.16), transparent 32%),
    linear-gradient(135deg, rgba(34, 211, 238, 0.13), transparent 36%),
    linear-gradient(180deg, rgba(8, 24, 42, 0.78), rgba(3, 8, 18, 0.84));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.035),
    0 0 32px rgba(34, 211, 238, 0.1);
  &::before {
    background: linear-gradient(90deg, transparent, rgba(34, 211, 238, 0.9), rgba(251, 191, 36, 0.55), transparent);
  }
}
.tianshu-city-core {
  display: grid;
  grid-template-columns: 118px 1fr;
  gap: 14px;
  align-items: center;
}
.tianshu-city-mode-hint {
  margin: -2px 0 10px;
  padding: 7px 10px;
  border: 1px solid rgba(34, 211, 238, 0.14);
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.1), rgba(2, 8, 16, 0.32));
  color: rgba(207, 250, 254, 0.78);
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0.04em;
}
.tianshu-city-mode-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 0 0 10px;
  div {
    min-width: 0;
    padding: 7px 8px;
    border: 1px solid rgba(34, 211, 238, 0.16);
    background:
      linear-gradient(180deg, rgba(34, 211, 238, 0.1), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
  }
  span {
    display: block;
    color: rgba(207, 250, 254, 0.62);
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  b {
    display: block;
    margin-top: 4px;
    color: #ecfeff;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 16px;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .is-good b {
    color: #a5f3fc;
  }
  .is-warn b {
    color: #fde68a;
  }
  .is-danger {
    border-color: rgba(251, 146, 60, 0.32);
    background:
      linear-gradient(180deg, rgba(249, 115, 22, 0.14), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
    b {
      color: #fed7aa;
    }
  }
}
.tianshu-city-core__ring {
  position: relative;
  height: 118px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(4, 12, 20, 0.96) 0 48%, transparent 49%),
    conic-gradient(from 210deg, #22d3ee, #38bdf8, #fbbf24, #22d3ee);
  box-shadow: 0 0 32px rgba(34, 211, 238, 0.18), inset 0 0 28px rgba(0, 0, 0, 0.5);
  span {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 42px;
    color: #cffafe;
  }
  small {
    position: absolute;
    bottom: 28px;
    color: rgba(207, 250, 254, 0.72);
    font-size: 12px;
  }
}
.tianshu-city-districts button {
  display: grid;
  grid-template-columns: 72px 1fr 74px;
  gap: 5px 9px;
  align-items: center;
  padding: 10px 11px;
  span {
    color: #f0fdff;
    font-weight: 800;
  }
  i {
    height: 5px;
    overflow: hidden;
    background: rgba(34, 211, 238, 0.12);
    em {
      display: block;
      height: 100%;
      background: linear-gradient(90deg, #22d3ee, #fbbf24);
      box-shadow: 0 0 12px rgba(34, 211, 238, 0.45);
    }
  }
  b {
    color: #cffafe;
    text-align: right;
    font-family: D-DIN, ui-monospace, monospace;
  }
  small {
    grid-column: 1 / -1;
    color: rgba(207, 250, 254, 0.7);
    font-size: 12px;
  }
}
.tianshu-city-coverage {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
  div {
    min-height: 86px;
    display: grid;
    align-content: center;
    padding: 12px;
    border: 1px solid rgba(103, 232, 249, 0.16);
    background: linear-gradient(180deg, rgba(34, 211, 238, 0.1), rgba(2, 8, 16, 0.42));
  }
  span {
    color: rgba(207, 250, 254, 0.7);
    font-size: 12px;
  }
  b {
    margin-top: 6px;
    color: #e0f2fe;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 26px;
  }
}
.tianshu-city-list b {
  color: #67e8f9;
}

.tianshu-fulfillment-drawer-overlay {
  position: fixed;
  inset: 0;
  z-index: 100001;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 94px 0 126px;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 60% 50%, rgba(34, 211, 238, 0.12), transparent 34%),
    rgba(3, 10, 18, 0.68);
  backdrop-filter: blur(5px);
  pointer-events: none;
}
.tianshu-fulfillment-drawer {
  position: relative;
  width: min(780px, 48vw);
  height: min(780px, calc(100vh - 220px));
  padding: 24px 26px 30px;
  overflow: auto;
  color: #eaffff;
  border-left: 1px solid rgba(103, 232, 249, 0.38);
  background:
    linear-gradient(135deg, rgba(8, 145, 178, 0.2), transparent 32%),
    linear-gradient(180deg, rgba(7, 20, 36, 0.96), rgba(2, 7, 14, 0.98));
  box-shadow:
    -18px 0 60px rgba(0, 0, 0, 0.48),
    inset 1px 0 0 rgba(255, 255, 255, 0.04);
  animation: tianshuFulfillmentDrawerIn 0.32s ease-out both;
  pointer-events: auto;
}
.tianshu-fulfillment-drawer__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  p {
    margin: 0 0 6px;
    color: rgba(250, 204, 21, 0.78);
    font-size: 12px;
    letter-spacing: 0.18em;
  }
  h2 {
    margin: 0;
    font-size: 28px;
    line-height: 1.1;
    letter-spacing: 0.08em;
    color: #f4feff;
    text-shadow: 0 0 26px rgba(34, 211, 238, 0.3);
  }
  span {
    display: block;
    margin-top: 8px;
    color: rgba(190, 235, 245, 0.72);
    font-size: 13px;
  }
  button {
    width: 38px;
    height: 38px;
    border: 1px solid rgba(103, 232, 249, 0.28);
    border-radius: 8px;
    color: #dffcff;
    background: rgba(34, 211, 238, 0.1);
    cursor: pointer;
    font-size: 26px;
    line-height: 1;
  }
}
.tianshu-fulfillment-drawer__scan {
  height: 2px;
  margin-bottom: 16px;
  background: linear-gradient(90deg, transparent, #67e8f9, #facc15, transparent);
  box-shadow: 0 0 18px rgba(103, 232, 249, 0.5);
  animation: tianshuFulfillmentScan 2.4s ease-in-out infinite;
}
.tianshu-fulfillment-drawer__modes {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: -4px 0 14px;
  button {
    min-width: 0;
    height: 30px;
    padding: 0 8px;
    border: 1px solid rgba(103, 232, 249, 0.18);
    color: rgba(207, 250, 254, 0.78);
    cursor: pointer;
    font: inherit;
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.05em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    background:
      linear-gradient(180deg, rgba(103, 232, 249, 0.1), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.38);
    transition:
      border-color 0.18s ease,
      color 0.18s ease,
      box-shadow 0.18s ease;
  }
  button:hover,
  button.is-active {
    color: #ecfeff;
    border-color: rgba(167, 243, 255, 0.52);
    box-shadow:
      inset 0 0 18px rgba(103, 232, 249, 0.12),
      0 0 16px rgba(103, 232, 249, 0.12);
  }
}
.tianshu-fulfillment-drawer__conclusion {
  margin: 0 0 16px;
  padding: 13px 14px;
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: rgba(34, 211, 238, 0.07);
  color: rgba(226, 252, 255, 0.86);
  line-height: 1.7;
}
.tianshu-fulfillment-drawer__cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}
.tianshu-fulfillment-drawer__card {
  padding: 12px;
  border: 1px solid rgba(103, 232, 249, 0.18);
  background: rgba(6, 20, 34, 0.68);
  span {
    display: block;
    margin-bottom: 8px;
    color: rgba(190, 230, 240, 0.7);
    font-size: 12px;
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 20px;
    color: #eaffff;
  }
  &.is-good b {
    color: #67e8f9;
  }
  &.is-warn b {
    color: #facc15;
  }
  &.is-danger b {
    color: #fb7185;
  }
}
.tianshu-fulfillment-drawer__section {
  margin-top: 16px;
  h3 {
    margin: 0 0 9px;
    color: #dffcff;
    font-size: 16px;
    letter-spacing: 0.08em;
  }
}
.tianshu-fulfillment-drawer__rows {
  display: grid;
  gap: 9px;
}
.tianshu-fulfillment-drawer__row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
  border: 1px solid rgba(103, 232, 249, 0.12);
  background: rgba(2, 9, 18, 0.52);
}
.tianshu-fulfillment-drawer__cell {
  min-width: 0;
  span {
    display: block;
    margin-bottom: 4px;
    color: rgba(150, 205, 220, 0.68);
    font-size: 11px;
  }
  b {
    display: block;
    color: rgba(238, 254, 255, 0.92);
    font-size: 13px;
    line-height: 1.45;
    word-break: break-word;
  }
}
.tianshu-device-link {
  padding: 12px;
  border: 1px solid rgba(103, 232, 249, 0.18);
  background:
    radial-gradient(circle at 12% 0%, rgba(56, 189, 248, 0.16), transparent 42%),
    rgba(2, 9, 18, 0.44);
}
.tianshu-device-link__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  h3 {
    margin: 0;
  }
  span {
    color: rgba(190, 235, 245, 0.68);
    font-size: 12px;
  }
}
.tianshu-device-link__cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.tianshu-device-link__card {
  padding: 10px 12px;
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: rgba(4, 16, 30, 0.72);
  span {
    display: block;
    margin-bottom: 6px;
    color: rgba(165, 224, 236, 0.68);
    font-size: 11px;
  }
  b {
    color: #eaffff;
    font-size: 17px;
    font-family: D-DIN, ui-monospace, monospace;
  }
  &.is-good b {
    color: #67e8f9;
  }
  &.is-warn b {
    color: #facc15;
  }
  &.is-danger b {
    color: #fb7185;
  }
}
.tianshu-device-link__rows {
  margin-bottom: 10px;
}
.tianshu-device-link__devices {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 8px;
}
.tianshu-device-chip {
  min-width: 0;
  padding: 10px;
  text-align: left;
  border: 1px solid rgba(103, 232, 249, 0.2);
  color: #eaffff;
  cursor: pointer;
  background:
    linear-gradient(135deg, rgba(14, 165, 233, 0.14), rgba(2, 8, 16, 0.48)),
    rgba(2, 9, 18, 0.7);
  transition:
    border-color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease;
  span,
  small {
    display: block;
    color: rgba(190, 235, 245, 0.68);
    font-size: 11px;
  }
  b {
    display: block;
    margin: 5px 0;
    overflow: hidden;
    color: #f4feff;
    font-size: 13px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  &:hover {
    transform: translateY(-1px);
    border-color: rgba(165, 243, 252, 0.55);
    box-shadow: 0 0 18px rgba(34, 211, 238, 0.16);
  }
  &.is-beidou {
    border-color: rgba(34, 211, 238, 0.32);
  }
  &.is-elitech {
    border-color: rgba(167, 139, 250, 0.32);
  }
  &.is-camera {
    border-color: rgba(96, 165, 250, 0.32);
  }
}
.tianshu-device-overlay {
  position: fixed;
  inset: 0;
  z-index: 100002;
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  padding: 188px 34px 42px;
  background:
    radial-gradient(circle at 82% 52%, rgba(14, 165, 233, 0.15), transparent 30%),
    rgba(1, 7, 14, 0.22);
  backdrop-filter: blur(2px);
  pointer-events: none;
}
.tianshu-device-panel {
  width: min(720px, 40vw);
  max-height: calc(100vh - 230px);
  overflow: auto;
  padding: 22px 24px 26px;
  color: #eaffff;
  border: 1px solid rgba(103, 232, 249, 0.28);
  background:
    linear-gradient(135deg, rgba(14, 165, 233, 0.16), transparent 34%),
    linear-gradient(180deg, rgba(7, 20, 36, 0.97), rgba(2, 7, 14, 0.99));
  box-shadow:
    0 28px 80px rgba(0, 0, 0, 0.55),
    inset 0 0 0 1px rgba(255, 255, 255, 0.035);
  animation: tianshuFulfillmentDrawerIn 0.26s ease-out both;
  pointer-events: auto;
}
.tianshu-device-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  p {
    margin: 0 0 5px;
    color: rgba(250, 204, 21, 0.78);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: 0.18em;
  }
  h2 {
    margin: 0;
    color: #f4feff;
    font-size: 28px;
    letter-spacing: 0.06em;
  }
  span {
    display: block;
    margin-top: 7px;
    color: rgba(190, 235, 245, 0.72);
  }
  button {
    width: 38px;
    height: 38px;
    border: 1px solid rgba(103, 232, 249, 0.28);
    color: #dffcff;
    cursor: pointer;
    background: rgba(34, 211, 238, 0.1);
    font-size: 26px;
    line-height: 1;
  }
}
.tianshu-device-panel__error {
  margin: 0;
  padding: 14px;
  border: 1px solid rgba(251, 113, 133, 0.28);
  color: #ffe4e6;
  background: rgba(127, 29, 29, 0.22);
}
.tianshu-device-panel__kv {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr);
  gap: 8px 12px;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid rgba(103, 232, 249, 0.13);
  background: rgba(2, 9, 18, 0.52);
  span {
    color: rgba(165, 224, 236, 0.68);
    font-size: 12px;
  }
  b {
    color: rgba(238, 254, 255, 0.92);
    font-size: 13px;
    word-break: break-all;
  }
}
.tianshu-device-live__screen,
.tianshu-device-track__map,
.tianshu-device-curve__chart {
  position: relative;
  height: 360px;
  overflow: hidden;
  border: 1px solid rgba(103, 232, 249, 0.2);
  background:
    linear-gradient(rgba(103, 232, 249, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(103, 232, 249, 0.08) 1px, transparent 1px),
    radial-gradient(circle at 50% 50%, rgba(34, 211, 238, 0.16), transparent 44%),
    rgba(1, 8, 16, 0.86);
  background-size: 32px 32px, 32px 32px, auto, auto;
}
.tianshu-device-live__screen {
  display: grid;
  place-items: center;
  video {
    width: 100%;
    height: 100%;
    object-fit: contain;
    background: #020714;
  }
  div {
    display: grid;
    gap: 8px;
    text-align: center;
  }
  b {
    color: #67e8f9;
    font-size: 24px;
  }
  span {
    color: rgba(190, 235, 245, 0.72);
  }
}
.tianshu-device-track__map span {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #67e8f9;
  box-shadow: 0 0 14px rgba(103, 232, 249, 0.9);
  transform: translate(-50%, -50%);
}
.tianshu-device-curve__chart i,
.tianshu-device-curve__chart em {
  position: absolute;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  transform: translate(-50%, 50%);
}
.tianshu-device-curve__chart i {
  background: #fb7185;
  box-shadow: 0 0 14px rgba(251, 113, 133, 0.75);
}
.tianshu-device-curve__chart em {
  background: #67e8f9;
  box-shadow: 0 0 14px rgba(103, 232, 249, 0.75);
}
@keyframes tianshuFulfillmentPulse {
  0%,
  100% {
    filter: drop-shadow(0 0 10px rgba(34, 211, 238, 0.16));
  }
  50% {
    filter: drop-shadow(0 0 24px rgba(103, 232, 249, 0.34));
  }
}
@keyframes tianshuFulfillmentBar {
  0%,
  100% {
    filter: brightness(0.95);
  }
  50% {
    filter: brightness(1.28);
  }
}
@keyframes tianshuFulfillmentDrawerIn {
  from {
    opacity: 0;
    transform: translateX(28px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
@keyframes tianshuFulfillmentScan {
  0%,
  100% {
    opacity: 0.55;
    transform: scaleX(0.82);
  }
  50% {
    opacity: 1;
    transform: scaleX(1);
  }
}

.tianshu-risk-card {
  position: relative;
  flex: 1;
  min-height: 0;
  margin-bottom: 12px;
  padding: 16px 16px 14px;
  pointer-events: auto;
  overflow: hidden;
  border: 1px solid rgba(248, 113, 113, 0.28);
  background:
    linear-gradient(135deg, rgba(127, 29, 29, 0.18), transparent 34%),
    linear-gradient(180deg, rgba(8, 22, 42, 0.72), rgba(3, 9, 18, 0.78));
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.035),
    0 0 28px rgba(248, 113, 113, 0.08);
  backdrop-filter: blur(4px);
  &::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(252, 165, 165, 0.9), transparent);
  }
}
.tianshu-risk-card__head {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  span {
    font-size: 17px;
    font-weight: 800;
    color: #fff7ed;
    text-shadow: 0 0 14px rgba(248, 113, 113, 0.28);
  }
  b {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 12px;
    color: rgba(251, 191, 36, 0.82);
    letter-spacing: 0.14em;
  }
}
.tianshu-risk-card--command {
  flex: 1.25;
}
.tianshu-risk-gauge {
  position: relative;
  width: 178px;
  height: 178px;
  margin: 4px auto 12px;
  border-radius: 50%;
  background:
    radial-gradient(circle, rgba(255, 247, 237, 0.12) 0 28%, transparent 29%),
    conic-gradient(from 220deg, rgba(239, 68, 68, 0.95), rgba(249, 115, 22, 0.7), rgba(34, 211, 238, 0.24), rgba(239, 68, 68, 0.95));
  box-shadow:
    0 0 32px rgba(248, 113, 113, 0.22),
    inset 0 0 35px rgba(0, 0, 0, 0.72);
  &::after {
    content: "";
    position: absolute;
    inset: 14px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(6, 12, 24, 0.98), rgba(10, 18, 35, 0.92));
    box-shadow: inset 0 0 24px rgba(248, 113, 113, 0.15);
  }
  &::before {
    content: "";
    position: absolute;
    inset: 10px;
    border-radius: 50%;
    background: conic-gradient(from 0deg, transparent, rgba(255, 237, 213, 0.72), transparent 22%);
    z-index: 1;
    animation: tianshuRiskSweep 2.8s linear infinite;
    opacity: 0.75;
  }
  i {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 4px;
    height: 28px;
    margin-left: -2px;
    margin-top: -89px;
    border-radius: 999px;
    background: rgba(254, 215, 170, 0.88);
    transform: rotate(var(--r)) translateY(4px);
    transform-origin: 50% 89px;
    z-index: 2;
    box-shadow: 0 0 16px rgba(251, 146, 60, 0.65);
  }
}
.tianshu-risk-gauge__core {
  position: absolute;
  inset: 42px;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(127, 29, 29, 0.55), rgba(7, 14, 28, 0.88));
  animation: tianshuRiskCorePulse 1.9s ease-in-out infinite;
  span {
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 48px;
    font-weight: 900;
    line-height: 1;
    color: #fff7ed;
    text-shadow: 0 0 24px rgba(248, 113, 113, 0.45);
  }
  small {
    margin-top: 8px;
    font-size: 12px;
    color: rgba(254, 215, 170, 0.76);
    letter-spacing: 0.18em;
  }
}
.tianshu-risk-ranks {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  div {
    padding: 9px 8px;
    border: 1px solid rgba(251, 146, 60, 0.2);
    background: rgba(7, 14, 28, 0.46);
  }
  span,
  b {
    display: block;
    text-align: center;
  }
  span {
    font-size: 12px;
    color: rgba(226, 232, 240, 0.7);
  }
  b {
    margin-top: 4px;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 24px;
    color: #fed7aa;
  }
}
.tianshu-risk-mode-hint {
  margin: -2px 0 10px;
  padding: 7px 10px;
  border: 1px solid rgba(248, 113, 113, 0.16);
  background: linear-gradient(90deg, rgba(248, 113, 113, 0.1), rgba(2, 8, 16, 0.32));
  color: rgba(254, 226, 226, 0.78);
  font-size: 12px;
  line-height: 1.45;
  letter-spacing: 0.04em;
}
.tianshu-risk-mode-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 0 0 10px;
  div {
    min-width: 0;
    padding: 7px 8px;
    border: 1px solid rgba(248, 113, 113, 0.16);
    background:
      linear-gradient(180deg, rgba(248, 113, 113, 0.1), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
  }
  span {
    display: block;
    color: rgba(254, 226, 226, 0.62);
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  b {
    display: block;
    margin-top: 4px;
    color: #fee2e2;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 16px;
    line-height: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .is-good b {
    color: #67e8f9;
  }
  .is-warn b {
    color: #fbbf24;
  }
  .is-danger {
    border-color: rgba(251, 113, 133, 0.34);
    background:
      linear-gradient(180deg, rgba(251, 113, 133, 0.14), rgba(2, 8, 16, 0.34)),
      rgba(2, 8, 16, 0.3);
    b {
      color: #fecdd3;
    }
  }
}
.tianshu-risk-bars {
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.tianshu-risk-bar__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.78);
  b {
    font-family: D-DIN, ui-monospace, monospace;
    color: #fff7ed;
  }
}
.tianshu-risk-bar__track {
  height: 8px;
  margin-top: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.82);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
  i {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #ef4444, #f97316, #facc15);
    box-shadow: 0 0 16px rgba(249, 115, 22, 0.45);
    transition: width 0.45s ease;
    animation: tianshuRiskBarGlow 1.8s ease-in-out infinite;
  }
}
.tianshu-risk-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  button {
    width: 100%;
    padding: 10px 11px;
    border: 0;
    border-left: 2px solid rgba(248, 113, 113, 0.75);
    color: inherit;
    text-align: left;
    cursor: pointer;
    font: inherit;
    background: rgba(15, 23, 42, 0.44);
  }
  span {
    display: block;
    font-size: 13px;
    font-weight: 800;
    color: #fed7aa;
  }
  p {
    margin: 5px 0 0;
    font-size: 12px;
    line-height: 1.45;
    color: rgba(226, 232, 240, 0.76);
  }
}
.tianshu-risk-card--list {
  flex: 2.15;
}
.tianshu-risk-feed {
  display: flex;
  flex-direction: column;
  gap: 9px;
  max-height: 420px;
  overflow: hidden;
}
.tianshu-risk-feed__item {
  width: 100%;
  padding: 10px 11px;
  border: 1px solid rgba(248, 113, 113, 0.2);
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
  background:
    linear-gradient(90deg, rgba(127, 29, 29, 0.2), transparent),
    rgba(2, 8, 23, 0.46);
  animation: tianshuRiskFeedIn 0.72s ease both;
  &.is-medium {
    border-color: rgba(251, 146, 60, 0.22);
  }
  &.is-low {
    border-color: rgba(34, 211, 238, 0.2);
  }
  p {
    height: 34px;
    margin: 6px 0;
    overflow: hidden;
    font-size: 12px;
    line-height: 1.42;
    color: rgba(226, 232, 240, 0.78);
  }
}
.tianshu-risk-feed__top,
.tianshu-risk-feed__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.tianshu-risk-feed__top {
  span {
    font-size: 13px;
    font-weight: 800;
    color: #fff7ed;
  }
  b {
    min-width: 24px;
    text-align: center;
    color: #3b0909;
    background: linear-gradient(180deg, #fecaca, #fb923c);
    font-size: 12px;
  }
}
.tianshu-risk-feed__foot {
  gap: 12px;
  span {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 11px;
    color: rgba(148, 163, 184, 0.78);
  }
}
.tianshu-risk-empty {
  padding: 34px 16px;
  text-align: center;
  font-size: 13px;
  color: rgba(226, 232, 240, 0.64);
  border: 1px dashed rgba(148, 163, 184, 0.28);
  background: rgba(15, 23, 42, 0.32);
}
.tianshu-risk-card--money {
  flex: 0.7;
}
.tianshu-risk-money {
  padding: 12px 4px 4px;
  span,
  small {
    display: block;
    color: rgba(226, 232, 240, 0.7);
  }
  span {
    font-size: 12px;
    letter-spacing: 0.16em;
  }
  b {
    display: block;
    margin: 8px 0;
    font-family: D-DIN, ui-monospace, monospace;
    font-size: 42px;
    line-height: 1;
    color: #fff7ed;
    text-shadow: 0 0 22px rgba(248, 113, 113, 0.38);
  }
  small {
    font-size: 12px;
  }
}
@keyframes tianshuRiskSweep {
  to {
    transform: rotate(360deg);
  }
}
@keyframes tianshuRiskCorePulse {
  0%,
  100% {
    box-shadow: inset 0 0 24px rgba(248, 113, 113, 0.15), 0 0 18px rgba(248, 113, 113, 0.1);
  }
  50% {
    box-shadow: inset 0 0 34px rgba(248, 113, 113, 0.28), 0 0 30px rgba(248, 113, 113, 0.22);
  }
}
@keyframes tianshuRiskBarGlow {
  0%,
  100% {
    filter: brightness(0.95);
  }
  50% {
    filter: brightness(1.25);
  }
}
@keyframes tianshuRiskFeedIn {
  from {
    opacity: 0;
    transform: translateX(18px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
/* 默认即显示大屏（不再依赖 GSAP 从 opacity:0 入场，避免部分环境下一直不可见） */
</style>
