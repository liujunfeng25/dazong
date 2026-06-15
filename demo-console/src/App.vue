<template>
  <div class="page">
    <header class="hdr">
      <h1>开发数据操盘台</h1>
      <p class="sub">真实链路验收 / 批量下单 / 级联清理</p>
    </header>

    <el-alert class="blk model-banner" type="info" :closable="false" show-icon>
      <template #title>真实业务模型（开发验收入口）</template>
      <p class="model-p">
        <strong>业务口径：食堂下单</strong>（与主站一致）：用<strong>采购单位账号</strong>登录后，必须先绑定<strong>履约食堂</strong>再下单；订单落库时带
        <code>canteen_id</code>，不是「绕过食堂的客户直订」。本页用 <code>GET /client/canteens</code> +
        <code>POST /client/canteen-session</code> 自动完成绑定（优先「默认食堂」，否则第一个启用食堂），再调商品与
        <code>POST /orders</code>（否则 403）。<strong>多单位</strong>：多选下方登录名批量造数，每个登录名对应一所学校/单位，并各自绑定一所启用食堂。<strong>单配送商</strong>：演示固定
        <code>delivery001</code>（「单配送商」框用于解析其 <code>delivery_id</code>）。<strong>多供货商</strong>：体现在智能分单后的<strong>分单行</strong>供货方（如
        supplier001/002/003），与「多个配送商」无关；<code>orders/meta</code> 里 <code>deliveries</code> 仅为「该单位账号还能签约哪些配送商」，演示通常只有一条。
      </p>
    </el-alert>

    <el-card class="blk step-flow" shadow="never">
      <template #header>
        <span class="step-flow__title">推荐真实链路验收流程</span>
      </template>
      <ol class="step-flow__list">
        <li>
          本页完成「合约校验」→「批量下单」（同一单位登录名多笔订单会<strong>错开 SKU 与数量</strong>，避免克隆单；收货坐标微偏移 + 随机时段便于排线）。
        </li>
        <li>
          配送商 <code>delivery001</code> 登录主站 →
          <strong>智能分单</strong>（<code>/delivery/smart-split</code>）→ 生成建议并确认分单。
        </li>
        <li>同一账号进入 <strong>智能排线</strong>（<code>/delivery/smart-routing</code>）选择订单做路线规划。</li>
        <li>
          回到本页（监管已登录）：填入 <code>order_id</code>，使用「全部供货商一键发货」或按单家发货；清场用「一键清除全部订单链路」。
        </li>
      </ol>
      <el-alert class="step-flow__warn" type="warning" :closable="false" show-icon>
        <template #title>分单与报价</template>
        智能分单要求行上商品至少有一家「挂靠该配送商」的供货商报价（指定厂家商品除外）。若大量「暂无报价」，请在运营端或种子数据里补
        <code>SupplierProductQuote</code>。
      </el-alert>
    </el-card>

    <el-collapse v-model="collapseActive" class="blk">
      <el-collapse-item title="连接与食堂造数" name="cfg">
        <el-form label-position="top" size="default">
          <el-form-item label="接口连到哪里">
            <el-select v-model="form.apiPreset" placeholder="请选择" style="width: 100%">
              <el-option
                v-for="opt in apiPresetOptions"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
            <p v-if="apiPresetHint" class="field-hint">{{ apiPresetHint }}</p>
            <el-input
              v-if="form.apiPreset === 'custom'"
              v-model="form.apiBaseCustom"
              class="field-custom"
              type="textarea"
              :rows="2"
              placeholder="完整 API 根路径，须以 /api 结尾，例如 http://192.168.1.5:8000/api"
              clearable
            />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :xs="24" :sm="12">
              <el-form-item label="单配送商登录名（解析 delivery_id，默认 delivery001）">
                <el-input v-model="form.deliveryUsername" placeholder="delivery001" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="采购端登录密码（演示各账号通常相同）">
                <el-input v-model="form.password" type="password" show-password />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="以食堂名义造数：选履约食堂（库里有几所列几所）">
            <el-select
              v-model="form.clients"
              multiple
              filterable
              allow-create
              default-first-option
              :loading="clientListLoading"
              placeholder="从库中加载后，每所启用食堂一行；也可只输入登录名（将自动选默认食堂）"
              style="width: 100%"
            >
              <el-option
                v-for="o in demoClientSelectOptions"
                :key="o.key"
                :label="formatDemoClientCanteenLabel(o)"
                :value="o.key"
              />
            </el-select>
            <p class="field-hint">
              <template v-if="clientListFromDb">
                列表来自 <code>GET /demo/client-accounts</code>：按库中 <code>client_canteens</code> 展开，仅展示<strong>启用</strong>食堂；值形如
                <code>登录名::食堂id</code>，下单前会按该行换食堂会话。
              </template>
              <template v-else>列表仅在接口成功返回后才有数据；加载失败时不会填入任何假列表，请看页面提示或检查网络 / VPN。</template>
              <el-button type="primary" link :loading="clientListLoading" @click="loadClientList">刷新</el-button>
            </p>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :xs="12" :sm="6">
              <el-form-item label="每账号订单数">
                <el-input-number v-model="form.ordersPerClient" :min="1" :max="50" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6">
              <el-form-item label="每笔行数">
                <el-input-number v-model="form.linesPerOrder" :min="1" :max="30" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6">
              <el-form-item label="每行数量">
                <el-input-number v-model="form.lineQuantity" :min="1" :max="9999" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="12" :sm="6">
              <el-form-item label="服务时长(分)">
                <el-input-number v-model="form.serviceDurationMin" :min="1" :max="240" controls-position="right" style="width: 100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="商品搜索关键词（空则不限）">
            <el-input v-model="form.productKeyword" clearable placeholder="如：白菜" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :xs="24" :sm="12">
              <el-form-item label="期望配送日">
                <el-date-picker v-model="form.expectedDate" type="date" value-format="YYYY-MM-DD" placeholder="必选" style="width: 100%" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="配送时段（整点一小时）">
                <el-switch v-model="form.randomDeliverySlot" active-text="每笔随机" inactive-text="固定" />
                <el-input
                  v-if="!form.randomDeliverySlot"
                  v-model="form.expectedSlot"
                  class="slot-below"
                  placeholder="09:00-10:00"
                />
                <p v-else class="field-hint">每笔下单在 00:00-01:00 … 22:00-23:00、23:00-24:00 中随机，与后端整点一小时规则一致，便于测智能排线。</p>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="经纬度微偏移（按订单序号累加，避免完全重合）">
            <el-input-number v-model="form.coordStep" :min="0" :max="0.01" :step="0.00001" :precision="5" controls-position="right" />
          </el-form-item>
          <el-form-item label="选品与校验">
            <el-space direction="vertical" alignment="flex-start" :size="10" style="width: 100%">
              <el-switch
                v-model="form.contractCategoriesOnly"
                active-text="仅合约内一级分类商品（推荐，按各采购单位签约合约筛选）"
                inactive-text="全库在售商品（不按合约筛分类）"
              />
              <el-switch v-model="form.force" active-text="无视异常商品校验（force，演示逃生）" />
              <p v-if="form.contractCategoriesOnly" class="field-hint">
                开启后对每个单位登录名单独拉取可下单 SKU，与 <code>POST /orders</code> 合约逻辑一致，一般<strong>无需</strong>再开 force。
              </p>
              <p v-else class="field-hint">全库选品时易遇到「分类不在该单位合约内」，可临时开启 force，或改回上一项推荐开关。</p>
            </el-space>
          </el-form-item>
        </el-form>
      </el-collapse-item>
    </el-collapse>

    <el-card class="blk" shadow="never">
      <template #header>
        <span>合约与 meta 校验</span>
        <el-button type="primary" link style="float: right" :loading="busyValidate" @click="runValidate">校验</el-button>
      </template>
      <el-alert v-if="validateOk === true" type="success" title="所选单位登录名已能绑定食堂，并与配送日、配送商匹配，可开始造单" :closable="false" show-icon />
      <el-alert v-if="validateOk === false" type="error" :title="'存在冲突：' + (validateIssues.join('；') || '请检查')" :closable="false" show-icon />
      <div v-if="metaPreview" class="meta-pre">
        <div class="meta-title">orders/meta（说明）</div>
        <p class="meta-expl">
          <strong>deliveries</strong>：该单位登录名当前可选签约的<strong>配送商</strong>，单配送商演示下通常只有
          <strong>一条</strong>，与「多供货商」无关。<strong>多供货商</strong>请看智能分单后订单的分单行
          <code>supplier_id</code>，或用下方「供货商一键发货」。
        </p>
        <pre>{{ metaPreview }}</pre>
      </div>
    </el-card>

    <el-card class="blk" shadow="never">
      <template #header>
        <span>批量下单</span>
      </template>
      <el-space wrap>
        <el-button type="primary" :disabled="validateOk !== true" :loading="busyPlace" @click="runPlaceOrders">开始批量下单</el-button>
        <el-button :disabled="!busyPlace" @click="cancelPlace">取消</el-button>
      </el-space>
      <p class="hint">串行执行，避免压垮开发库；完成后可在下方填入 order_id 调用开发辅助接口。</p>
    </el-card>

    <el-card class="blk" shadow="never">
      <template #header>
        <span>结果</span>
      </template>
      <div class="table-wrap">
        <el-table :data="resultRows" stripe size="small" style="width: 100%">
          <el-table-column prop="client" label="单位登录名" min-width="96" />
          <el-table-column prop="index" label="#" width="48" />
          <el-table-column prop="orderNo" label="订单号" min-width="120" />
          <el-table-column prop="orderId" label="order_id" width="88" />
          <el-table-column prop="status" label="状态" width="88" />
          <el-table-column prop="slot" label="时段" min-width="108" />
          <el-table-column prop="ms" label="耗时ms" width="88" />
          <el-table-column prop="error" label="错误" min-width="160">
            <template #default="{ row }">
              <el-button v-if="row.error" type="primary" link @click="showErr(row.error)">查看</el-button>
              <span v-else>—</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-collapse v-model="logCollapse" class="blk">
      <el-collapse-item title="请求日志" name="log">
        <div class="log-lines">
          <div v-for="(l, i) in logs" :key="i" class="log-line">{{ l }}</div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <el-card class="blk monitor" shadow="never">
      <template #header>
        <span>开发辅助（需 DEMO_MODE + 监管账号 monitor）</span>
      </template>
      <el-form label-position="top" size="default">
        <el-row :gutter="12">
          <el-col :xs="24" :sm="8">
            <el-form-item label="监管用户名">
              <el-input v-model="monitorForm.username" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label="密码">
              <el-input v-model="monitorForm.password" type="password" show-password />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="8">
            <el-form-item label=" ">
              <el-button type="primary" :loading="busyMonLogin" @click="monitorLogin">监管登录</el-button>
            </el-form-item>
          </el-col>
        </el-row>
        <el-alert v-if="monitorToken" type="info" :title="'已获取 token（前 20 字符）' + monitorToken.slice(0, 20) + '…'" :closable="false" />
        <el-alert
          v-else
          type="warning"
          :closable="false"
          show-icon
          class="monitor-login-hint"
          title="下方「发货」「删单」「一键清除全部订单链路」为灰色时：请先点击「监管登录」（默认 monitor001 / demo123）。登录成功后需后端开启 DEMO_MODE，否则会 403。"
        />
        <div class="tianshu-demo-panel">
          <div class="tianshu-demo-panel__head">
            <div>
              <div class="tianshu-demo-panel__title">天枢大屏真实模式批次</div>
              <p>生成 <code>TSDEMO</code> 批次：今日配送日订单、分单、分检、车次、风险告警、退单、账单和通知。清除只清这批数据。</p>
            </div>
            <el-space wrap>
              <el-button size="small" plain :disabled="!monitorToken" :loading="busyTianshuStatus" @click="refreshTianshuStatus">刷新状态</el-button>
              <el-button size="small" type="primary" plain @click="openTianshuScreen">打开天枢大屏</el-button>
              <el-tag effect="dark" type="success">真实接口</el-tag>
            </el-space>
          </div>
          <div class="tianshu-demo-panel__status">
            <div :class="{ 'is-empty': !tianshuBatchStatus.exists }">
              <span>当前批次</span>
              <b>{{ tianshuBatchStatus.exists ? "已生成" : "未生成" }}</b>
              <small>{{ tianshuBatchStatus.delivery_date || "等待生成 TSDEMO" }}</small>
            </div>
            <div>
              <span>订单 / 车次</span>
              <b>{{ tianshuBatchStatus.orders || 0 }} / {{ tianshuBatchStatus.dispatch_trips || 0 }}</b>
              <small>{{ tianshuBatchStatus.latest_order_no || "暂无订单" }}</small>
            </div>
            <div>
              <span>分单 / 分检</span>
              <b>{{ tianshuBatchStatus.allocations || 0 }} / {{ tianshuBatchStatus.sort_scan_records || 0 }}</b>
              <small>装车明细 {{ tianshuBatchStatus.dispatch_items || 0 }}</small>
            </div>
            <div>
              <span>预警 / 账单 / 通知</span>
              <b>{{ tianshuBatchStatus.alerts || 0 }} / {{ tianshuBatchStatus.bills || 0 }} / {{ tianshuBatchStatus.notifications || 0 }}</b>
              <small>退单 {{ tianshuBatchStatus.returns || 0 }}</small>
            </div>
          </div>
          <el-row :gutter="10" class="tianshu-demo-panel__controls">
            <el-col :xs="24" :sm="8">
              <el-input-number
                v-model="form.tianshuOrderCount"
                :min="12"
                :max="120"
                controls-position="right"
                style="width: 100%"
              />
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-button
                type="success"
                :disabled="!monitorToken"
                :loading="busyTianshuSeed"
                style="width: 100%"
                @click="seedTianshuRealData"
              >
                生成天枢真实模式数据
              </el-button>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-button
                type="danger"
                plain
                :disabled="!monitorToken"
                :loading="busyTianshuClear"
                style="width: 100%"
                @click="openClearTianshuDialog"
              >
                清除天枢批次
              </el-button>
            </el-col>
          </el-row>
          <p v-if="tianshuBatchSummary" class="tianshu-demo-panel__summary">{{ tianshuBatchSummary }}</p>
        </div>
        <el-form-item label="发货前（可选）">
          <el-switch
            v-model="form.mockPrintBeforeShip"
            active-text="全部供货商发货前：先模拟行级标签打印（写入 AuditLog，贴近真流程）"
          />
        </el-form-item>
        <el-form-item label="order_id 列表（逗号或换行）">
          <el-input v-model="demoOrderIdsText" type="textarea" :rows="3" placeholder="可从上方结果复制" />
          <el-button type="primary" link @click="fillIdsFromResults">填入本次成功订单 ID</el-button>
        </el-form-item>
        <el-form-item label="供货商一键发货（演示，等同发货结果：分单行→已出库，跳过打印门禁）">
          <el-row :gutter="8">
            <el-col :xs="24" :sm="14">
              <el-select
                v-model="supplierShipUsername"
                filterable
                placeholder="选择供货商"
                style="width: 100%"
                :loading="supplierListLoading"
              >
                <el-option
                  v-for="s in supplierChoices"
                  :key="s.username"
                  :label="`${(s.company_name || s.username) + '（' + s.username + '）'}`"
                  :value="s.username"
                />
              </el-select>
            </el-col>
            <el-col :xs="24" :sm="10">
              <el-button
                type="success"
                :disabled="!monitorToken"
                :loading="busySupplierShip"
                style="width: 100%"
                @click="supplierShipBulk"
              >
                对该供货商一键发货
              </el-button>
            </el-col>
          </el-row>
          <el-button
            class="ship-all-btn"
            type="primary"
            :disabled="!monitorToken"
            :loading="busySupplierShipAll"
            @click="supplierShipAllBulk"
          >
            全部供货商一键发货（按分单行归属，跳过真实打印门禁）
          </el-button>
          <p class="field-hint">
            单家发货：仅更新所选供货商在上方订单里的分单行。全部发货：对绑定本批订单配送商的所有供货商各执行一遍（无需切换账号）。演示接口均不校验真实标签打印。
          </p>
        </el-form-item>
        <el-form-item label="一键推进履约链路（演示，跳过分检/排线/签字门禁）">
          <el-button
            class="full-chain-btn"
            type="primary"
            :disabled="!monitorToken"
            :loading="busyFullChain"
            @click="runFullChain"
          >
            一键跑完整履约链路（配货→发货→取货→送达→收货确认→结算）
          </el-button>
          <el-space wrap class="chain-step-row">
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busyAllocate" @click="allocateOrders">① 一键配货（建分单）</el-button>
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busySupplierShipAll" @click="supplierShipAllBulk">② 发货（见上方按钮）</el-button>
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busyPickup" @click="pickupOrders">③ 一键取货 → 发货</el-button>
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busyDeliver" @click="deliverOrders">④ 一键送达 → 收货</el-button>
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busyReceive" @click="receiveOrders">⑤ 一键收货确认（生成账单）</el-button>
            <el-button type="warning" plain :disabled="!monitorToken" :loading="busySettle" @click="settleOrders">⑥ 一键结算</el-button>
          </el-space>
          <p class="field-hint">
            下单后订单无分单，需先「配货」生成分单行才能发货。各步按订单状态幂等：状态不符自动跳过。完整链路按钮内部用「分单行全部标已出库」做发货，可覆盖未绑定配送商的指定厂家。
          </p>
        </el-form-item>
        <el-space wrap>
          <el-tooltip
            :disabled="!!monitorToken"
            content="请先点击上方「监管登录」"
            placement="top"
          >
            <span class="btn-wrap">
              <el-button type="warning" :disabled="!monitorToken" :loading="busyMarkShipped" @click="markAllocationsShipped">分单行全部标为已出库（不区分供货商）</el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="!!monitorToken" content="请先点击上方「监管登录」" placement="top">
            <span class="btn-wrap">
              <el-button type="danger" :disabled="!monitorToken" :loading="busyDelete" @click="openDeleteDialog">按 ID 级联删单</el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="!!monitorToken" content="请先点击上方「监管登录」" placement="top">
            <span class="btn-wrap">
              <el-button type="danger" plain :disabled="!monitorToken" :loading="busyClearAll" @click="openClearAllDialog">一键清除全部订单链路</el-button>
            </span>
          </el-tooltip>
        </el-space>
      </el-form>
    </el-card>

    <el-dialog v-model="errDialog.visible" title="错误详情" width="90%" style="max-width: 560px">
      <pre class="err-pre">{{ errDialog.text }}</pre>
    </el-dialog>

    <el-dialog v-model="deleteDialog.visible" title="确认级联删单" width="90%" style="max-width: 480px">
      <p>
        将永久删除所列订单及其牵连的分单、分检记录、发车计划/司机端任务、收货称重、退单、账单、工单、通知、监管预警和流程时间线。
      </p>
      <p>基础资料（账号、商品、合约、车辆、设备、食堂）不会删除。</p>
      <p>请在下方输入 <strong>DELETE</strong> 后确认。</p>
      <el-input v-model="deleteDialog.confirm" placeholder="输入 DELETE" />
      <template #footer>
        <el-button @click="deleteDialog.visible = false">取消</el-button>
        <el-button type="danger" :disabled="deleteDialog.confirm !== 'DELETE'" :loading="busyDelete" @click="confirmDeleteOrders">确认删除</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="clearAllDialog.visible" title="确认清空全部订单" width="90%" style="max-width: 480px">
      <p>
        将永久删除数据库中<strong>全部</strong>订单链路数据：分单、分检记录、发车计划/司机端任务、收货称重、退单、账单、工单、通知、监管预警和流程时间线。
      </p>
      <p>基础资料（账号、商品、合约、车辆、设备、食堂）不会删除。</p>
      <p>请在下方输入 <strong>CLEAR ALL</strong> 后确认。</p>
      <el-input v-model="clearAllDialog.confirm" placeholder="输入 CLEAR ALL" />
      <template #footer>
        <el-button @click="clearAllDialog.visible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="clearAllDialog.confirm !== 'CLEAR ALL'"
          :loading="busyClearAll"
          @click="confirmClearAllOrders"
        >
          确认清空
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="clearTianshuDialog.visible" title="确认清除天枢批次" width="90%" style="max-width: 480px">
      <p>
        将删除订单号前缀为 <strong>TSDEMO</strong> 的天枢演示批次，以及它附带的分单、分检、车次、退单、账单、对账单、通知、预警和审计数据。
      </p>
      <p>普通演示订单和真实业务订单不会被删除。</p>
      <p>请在下方输入 <strong>CLEAR TIANSHU</strong> 后确认。</p>
      <el-input v-model="clearTianshuDialog.confirm" placeholder="输入 CLEAR TIANSHU" />
      <template #footer>
        <el-button @click="clearTianshuDialog.visible = false">取消</el-button>
        <el-button
          type="danger"
          :disabled="clearTianshuDialog.confirm !== 'CLEAR TIANSHU'"
          :loading="busyTianshuClear"
          @click="confirmClearTianshuData"
        >
          确认清除
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";
import { pickProductsForOrder, lineQuantityForDemo } from "./lib/orderPick.js";

/** 仅来自 GET /demo/client-accounts；加载失败时保持空数组，不使用内置假数据 */
const demoClientChoices = ref([]);

/** 与 el-option 对齐：每所启用食堂一行；离线无 id 时为「仅登录名」一行 */
const demoClientSelectOptions = computed(() => {
  const rows = demoClientChoices.value || [];
  const out = [];
  for (const raw of rows) {
    const company = raw.company || raw.company_name || "未知单位";
    const username = (raw.username || "").trim();
    if (!username) continue;
    const cant = Array.isArray(raw.canteens) ? raw.canteens : [];
    const active = cant.filter((x) => String(x.status || "active") === "active");
    if (!active.length) {
      out.push({
        key: username,
        username,
        company,
        canteenId: null,
        canteenName: "",
        noCanteen: true,
      });
      continue;
    }
    for (const cc of active) {
      const id = Number(cc.id);
      if (!Number.isFinite(id) || id <= 0) continue;
      out.push({
        key: `${username}::${id}`,
        username,
        company,
        canteenId: id,
        canteenName: ((cc.name || "") + "").trim() || `食堂#${id}`,
        noCanteen: false,
      });
    }
  }
  return out;
});

function formatDemoClientCanteenLabel(o) {
  if (!o) return "";
  const u = o.username || "";
  if (o.noCanteen || o.canteenId == null) {
    return `${o.company}（登录 ${u} · 库中无启用食堂或未加载明细）`;
  }
  return `${o.company} · ${o.canteenName}（登录 ${u} · 食堂 id ${o.canteenId}）`;
}

/** @returns {{ username: string, canteenId: number | null }} */
function parseClientChoice(entry) {
  const s = String(entry || "").trim();
  if (!s) return { username: "", canteenId: null };
  const idx = s.indexOf("::");
  if (idx === -1) return { username: s, canteenId: null };
  const username = s.slice(0, idx).trim();
  const canteenId = Number(s.slice(idx + 2));
  return {
    username,
    canteenId: Number.isFinite(canteenId) && canteenId > 0 ? canteenId : null,
  };
}

function syncClientSelectionsToAvailableOptions() {
  const opts = demoClientSelectOptions.value;
  const sel = [...(form.clients || [])].map((x) => String(x).trim()).filter(Boolean);
  if (!sel.length) return;
  const byUser = new Map();
  for (const o of opts) {
    if (!byUser.has(o.username)) byUser.set(o.username, []);
    byUser.get(o.username).push(o);
  }
  form.clients = sel.map((entry) => {
    if (entry.includes("::")) {
      if (opts.some((o) => o.key === entry)) return entry;
      const username = entry.split("::")[0];
      const list = byUser.get(username) || [];
      const first = list.find((x) => x.canteenId != null);
      return first ? first.key : username;
    }
    const list = byUser.get(entry) || [];
    const first = list.find((x) => x.canteenId != null);
    return first ? first.key : entry;
  });
}
const clientListLoading = ref(false);
const clientListFromDb = ref(false);
/** 来自 DB 的地址/坐标，用于下单；key 为 username */
const clientProfileByUser = ref({});

const supplierChoices = ref([]);
const supplierListLoading = ref(false);
const supplierShipUsername = ref("supplier001");
const busySupplierShip = ref(false);
const busySupplierShipAll = ref(false);

/** 普通人可读：value 为内部键，实际地址由 apiRoot() 解析 */
const apiPresetOptions = [
  {
    value: "same",
    label: "跟当前打开的网站一套（推荐）",
    hint: "和主站或本页同一地址，自动走「/api」。用 Docker 打开主站或 /demo-console/ 时选这项即可。",
    base: "",
  },
  {
    value: "docker8000",
    label: "本机 Docker 里的后端（浏览器直接连 8000 端口）",
    hint: "适合不经过主站 Nginx、直接访问后端映射端口时；若提示跨域，需在后端配置允许来源。",
    base: "http://127.0.0.1:8000/api",
  },
  {
    value: "alt18000",
    label: "本机后端在别的端口（例如 18000）",
    hint: "仅当你的后端映射在 18000 等端口时使用。",
    base: "http://127.0.0.1:18000/api",
  },
  {
    value: "custom",
    label: "其他地址（高级，很少用）",
    hint: "自行填写完整 API 根路径；跨域时要在后端 CORS 里放行你的页面来源。",
    base: "__custom__",
  },
];

/** 与 backend/database.py 种子一致，用于地址与坐标 */
/** 与 backend/services/delivery_slot.py 一致：整点起止、恰好一小时，含 23:00-24:00 */
function randomDeliverySlot() {
  const h = Math.floor(Math.random() * 24);
  const pad = (n) => String(n).padStart(2, "0");
  if (h === 23) return "23:00-24:00";
  return `${pad(h)}:00-${pad(h + 1)}:00`;
}

const SEED_CLIENT = {
  client001: { address: "北京市朝阳区望京演示点", lng: 116.481181, lat: 39.98941 },
  client002: { address: "北京市海淀区中关村大街演示点", lng: 116.316833, lat: 39.98396 },
  client003: { address: "北京市丰台区丽泽商务区演示点", lng: 116.321, lat: 39.866 },
  client004: { address: "北京市西城区金融街演示点", lng: 116.363227, lat: 39.914336 },
  client005: { address: "北京市朝阳区三里屯演示点", lng: 116.454, lat: 39.937 },
  client006: { address: "北京市通州区运河东大街演示点", lng: 116.656, lat: 39.902 },
};

const collapseActive = ref(["cfg"]);
const logCollapse = ref([]);

const form = reactive({
  apiPreset: "same",
  apiBaseCustom: "",
  deliveryUsername: "delivery001",
  password: "demo123",
  clients: [],
  ordersPerClient: 3,
  linesPerOrder: 5,
  lineQuantity: 2,
  serviceDurationMin: 30,
  productKeyword: "",
  expectedDate: "",
  expectedSlot: "09:00-10:00",
  randomDeliverySlot: true,
  coordStep: 0.00008,
  contractCategoriesOnly: true,
  force: false,
  mockPrintBeforeShip: false,
  tianshuOrderCount: 36,
});

const monitorForm = reactive({
  username: "monitor001",
  password: "demo123",
});

const busyValidate = ref(false);
const busyPlace = ref(false);
const busyMonLogin = ref(false);
const busyMarkShipped = ref(false);
const busyDelete = ref(false);
const busyClearAll = ref(false);
const busyAllocate = ref(false);
const busyPickup = ref(false);
const busyDeliver = ref(false);
const busyReceive = ref(false);
const busySettle = ref(false);
const busyFullChain = ref(false);
const busyTianshuSeed = ref(false);
const busyTianshuClear = ref(false);
const busyTianshuStatus = ref(false);
const validateOk = ref(null);
const validateIssues = ref([]);
const metaPreview = ref("");
const resolvedDeliveryId = ref(null);
const resultRows = ref([]);
const logs = ref([]);
const monitorToken = ref("");
const demoOrderIdsText = ref("");
const placeAbort = ref(null);

const errDialog = reactive({ visible: false, text: "" });
const deleteDialog = reactive({ visible: false, confirm: "" });
const clearAllDialog = reactive({ visible: false, confirm: "" });
const clearTianshuDialog = reactive({ visible: false, confirm: "" });
const tianshuBatchSummary = ref("");
const tianshuBatchStatus = reactive({
  exists: false,
  orders: 0,
  allocations: 0,
  sort_scan_records: 0,
  dispatch_trips: 0,
  dispatch_items: 0,
  returns: 0,
  bills: 0,
  alerts: 0,
  notifications: 0,
  latest_order_no: "",
  delivery_date: "",
});

const apiPresetHint = computed(() => {
  const o = apiPresetOptions.find((x) => x.value === form.apiPreset);
  return o ? o.hint : "";
});

function apiRoot() {
  if (form.apiPreset === "custom") {
    const t = (form.apiBaseCustom || "").trim().replace(/\/+$/, "");
    return t || "/api";
  }
  const o = apiPresetOptions.find((x) => x.value === form.apiPreset);
  const b = (o && o.base !== "__custom__" ? o.base : "").trim().replace(/\/+$/, "");
  return b || "/api";
}

function clientAxios(token) {
  const inst = axios.create({
    baseURL: apiRoot(),
    timeout: 120000,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  inst.interceptors.response.use(
    (r) => r,
    (err) => Promise.reject(err)
  );
  return inst;
}

/** 与主站一致：POST /orders 需要 JWT 含 canteen_id；优先「默认食堂」，否则第一个启用食堂 */
function pickDemoCanteenId(rows) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length) return null;
  const active = list.filter((r) => String(r.status || "active") === "active");
  const pool = active.length ? active : list;
  const def = pool.find((r) => String(r.name || "").trim() === "默认食堂");
  const row = def || pool[0];
  const id = Number(row?.id);
  return Number.isFinite(id) && id > 0 ? id : null;
}

/**
 * @param {string} clientToken
 * @param {AbortSignal} [signal]
 * @param {number | null} [preferredCanteenId] 与下拉「登录名::食堂id」一致；缺省时优先「默认食堂」
 * @returns {Promise<string>}
 */
async function ensureClientCanteenToken(clientToken, signal, preferredCanteenId) {
  const ax = clientAxios(clientToken);
  const { data: list } = await ax.get("/client/canteens", { signal });
  const rows = Array.isArray(list) ? list : [];
  let cid = null;
  const want = preferredCanteenId != null ? Number(preferredCanteenId) : null;
  if (Number.isFinite(want) && want > 0) {
    const hit = rows.find((r) => Number(r.id) === want && String(r.status || "active") === "active");
    if (hit) cid = want;
  }
  if (cid == null) {
    cid = pickDemoCanteenId(rows);
  }
  if (cid == null) {
    throw new Error("该单位登录名下无可用履约食堂，请先在运营端「客户食堂」菜单建档并启用");
  }
  const { data } = await ax.post("/client/canteen-session", { canteen_id: cid }, { signal });
  if (!data?.token) {
    throw new Error("换发食堂会话失败：响应无 token");
  }
  return data.token;
}

function pushLog(line) {
  const t = new Date().toISOString().slice(11, 23);
  logs.value.unshift(`[${t}] ${line}`);
  if (logs.value.length > 200) logs.value.pop();
}

async function timed(name, fn) {
  const t0 = performance.now();
  try {
    const data = await fn();
    pushLog(`${name} OK ${Math.round(performance.now() - t0)}ms`);
    return data;
  } catch (e) {
    const ms = Math.round(performance.now() - t0);
    const st = e.response?.status;
    const detail = e.response?.data?.detail;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail || e.message);
    pushLog(`${name} FAIL ${ms}ms HTTP ${st || "-"} ${msg}`);
    throw e;
  }
}

function parseOrderIds(text) {
  return (text || "")
    .split(/[\s,，;；]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n) && n > 0);
}

function cleanupSummaryText(data) {
  const d = data || {};
  const pairs = [
    ["订单", d.deleted_orders],
    ["车次", d.deleted_dispatch_trips],
    ["车次站点", d.deleted_dispatch_stops],
    ["装车明细", d.deleted_dispatch_items],
    ["分单", d.deleted_allocations],
    ["称重IoT", d.deleted_iot_data],
    ["分检", d.deleted_sort_scan_records],
    ["收货行", d.deleted_receiving_lines],
    ["退单", d.deleted_returns],
    ["退单行", d.deleted_return_lines],
    ["账单", d.deleted_bills],
    ["账单汇总", d.deleted_statements],
    ["工单", d.deleted_tickets],
    ["预警", d.deleted_alerts],
    ["通知", d.deleted_notifications],
    ["审计", d.deleted_audit_logs],
    ["幂等键", d.deleted_idempotency_keys],
    ["Outbox", d.deleted_outbox_events],
  ];
  const text = pairs
    .filter(([, v]) => Number(v || 0) > 0)
    .map(([k, v]) => `${k}${Number(v)}`)
    .join("，");
  if (text) return text;
  const requested = Number(d.requested_orders || 0);
  const matched = Number(d.matched_orders || 0);
  if (requested && !matched) return `未匹配到可删除订单（请求 ${requested} 个）`;
  return "未匹配到可删除数据";
}

function todayStr() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Fisher–Yates 打乱副本，用于同一采购账号多笔订单间 SKU 分布更随机 */
function shuffleArray(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

/** 多页拉取并去重，扩大合约内商品池，减轻「窗不够分」导致的克隆单 */
async function fetchMergedProductPool(clientToken, baseParams, signal, wantMin) {
  const byId = new Map();
  let page = 1;
  const pageSize = 100;
  const capPages = 8;
  while (page <= capPages && byId.size < wantMin) {
    const params = { ...baseParams, page, page_size: pageSize };
    const { data } = await clientAxios(clientToken).get("/orders/products/search", {
      params,
      signal,
    });
    const items = data.items || [];
    for (const it of items) {
      const id = Number(it.id);
      if (Number.isFinite(id) && id > 0 && !byId.has(id)) byId.set(id, it);
    }
    if (items.length < pageSize) break;
    page += 1;
  }
  return shuffleArray([...byId.values()]);
}

function seedForClient(username) {
  const p = clientProfileByUser.value[username];
  if (p && p.address && p.lng != null && p.lat != null) {
    return { address: p.address, lng: Number(p.lng), lat: Number(p.lat) };
  }
  return (
    SEED_CLIENT[username] || {
      address: "演示地址",
      lng: 116.4,
      lat: 39.9,
    }
  );
}

/**
 * @param {unknown} e axios 错误
 * @param {string} label 如「采购方/食堂」「供货商列表」
 */
function describeDemoApiLoadError(e, label) {
  const err = e && typeof e === "object" ? e : {};
  const code = err.code;
  const msg = (err.message && String(err.message)) || "";
  if (code === "ERR_NETWORK" || msg === "Network Error") {
    return `${label}加载失败：网络不通或请求被拦截（若正在使用 VPN / 系统代理，请检查是否把本页所连的 API 指错或拦掉）。`;
  }
  const resp = err.response;
  const st = resp && resp.status;
  const detail = resp && resp.data && resp.data.detail;
  const detailStr = typeof detail === "string" ? detail : "";
  if (st === 403) {
    return `${label}加载失败：HTTP 403（演示模式未开启或无权访问）。${detailStr}`;
  }
  if (Number.isFinite(st) && st > 0) {
    return `${label}加载失败：HTTP ${st}。${detailStr || msg || ""}`;
  }
  return `${label}加载失败：${msg || String(e)}`;
}

let clientReloadTimer = null;
async function loadClientList() {
  clientListLoading.value = true;
  try {
    const ax = clientAxios();
    const { data } = await ax.get("/demo/client-accounts");
    const rows = Array.isArray(data) ? data : [];
    if (!rows.length) {
      demoClientChoices.value = [];
      clientProfileByUser.value = {};
      clientListFromDb.value = true;
      form.clients = [];
      ElMessage.warning("演示接口已返回：当前库中没有任何采购方（client）账号，或全部未启用。");
    } else {
      demoClientChoices.value = rows.map((r) => ({
        username: r.username,
        company: ((r.company_name || "") + "").trim() || r.username,
        address: ((r.address || "") + "").trim(),
        lng: r.lng != null && r.lng !== "" ? Number(r.lng) : null,
        lat: r.lat != null && r.lat !== "" ? Number(r.lat) : null,
        canteens: Array.isArray(r.canteens) ? r.canteens : [],
      }));
      const map = {};
      for (const r of demoClientChoices.value) {
        map[r.username] = {
          address: r.address,
          lng: r.lng,
          lat: r.lat,
          company: r.company,
        };
      }
      clientProfileByUser.value = map;
      clientListFromDb.value = true;
    }
  } catch (e) {
    demoClientChoices.value = [];
    clientProfileByUser.value = {};
    clientListFromDb.value = false;
    form.clients = [];
    ElMessage.error(describeDemoApiLoadError(e, "采购方/食堂"));
  } finally {
    clientListLoading.value = false;
    syncClientSelectionsToAvailableOptions();
  }
}

function scheduleClientReload() {
  clearTimeout(clientReloadTimer);
  clientReloadTimer = setTimeout(() => {
    loadClientList();
    loadSupplierList();
  }, 450);
}

async function loadSupplierList() {
  supplierListLoading.value = true;
  try {
    const { data } = await clientAxios().get("/demo/supplier-accounts");
    const rows = Array.isArray(data) ? data : [];
    supplierChoices.value = rows;
    if (!rows.length) {
      supplierShipUsername.value = "";
      ElMessage.warning("演示接口已返回：当前库中没有任何供货商账号，或全部未启用。");
    } else if (
      supplierShipUsername.value &&
      !supplierChoices.value.some((x) => x.username === supplierShipUsername.value)
    ) {
      supplierShipUsername.value = supplierChoices.value[0].username;
    }
  } catch (e) {
    supplierChoices.value = [];
    supplierShipUsername.value = "";
    ElMessage.error(describeDemoApiLoadError(e, "供货商列表"));
  } finally {
    supplierListLoading.value = false;
  }
}

async function supplierShipBulk() {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return;
  }
  const u = (supplierShipUsername.value || "").trim();
  if (!u) {
    ElMessage.warning("请选择供货商");
    return;
  }
  busySupplierShip.value = true;
  try {
    if (form.mockPrintBeforeShip) {
      await clientAxios(monitorToken.value).post("/demo/orders/mock-print-allocation-labels", { order_ids: ids });
      pushLog("demo mock-print-allocation-labels OK (before single-supplier ship)");
    }
    const r = await clientAxios(monitorToken.value).post("/demo/orders/supplier-ship-bulk", {
      order_ids: ids,
      supplier_username: u,
    });
    ElMessage.success(
      `已处理：涉及订单数 ${r.data.orders_with_lines || 0}，更新分单行 ${r.data.allocation_rows_updated || 0} 条`
    );
    pushLog(`demo supplier-ship-bulk ${u} OK`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busySupplierShip.value = false;
  }
}

async function supplierShipAllBulk() {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return;
  }
  busySupplierShipAll.value = true;
  try {
    if (form.mockPrintBeforeShip) {
      await clientAxios(monitorToken.value).post("/demo/orders/mock-print-allocation-labels", { order_ids: ids });
      pushLog("demo mock-print-allocation-labels OK (before ship-all)");
    }
    const r = await clientAxios(monitorToken.value).post("/demo/orders/supplier-ship-all", { order_ids: ids });
    const d = r.data || {};
    ElMessage.success(
      `全部供货商：共 ${d.suppliers_touched || 0} 家参与，更新分单行 ${d.allocation_rows_updated || 0} 条`
    );
    pushLog(`demo supplier-ship-all OK suppliers=${d.suppliers_touched} rows=${d.allocation_rows_updated}`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busySupplierShipAll.value = false;
  }
}

/** 履约链路单步：POST /demo/orders/{path}，监管 token，按 demoOrderIdsText 批量 */
async function demoLifecycleStep(path, busyRef) {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return null;
  }
  if (busyRef) busyRef.value = true;
  try {
    const r = await clientAxios(monitorToken.value).post(`/demo/orders/${path}`, { order_ids: ids });
    pushLog(`demo ${path} OK ${JSON.stringify(r.data).slice(0, 160)}`);
    return r.data;
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
    pushLog(`demo ${path} FAIL`);
    throw e;
  } finally {
    if (busyRef) busyRef.value = false;
  }
}

const skipNote = (d) => (d.skipped?.length ? `，跳过 ${d.skipped.length}` : "");

async function allocateOrders() {
  const d = await demoLifecycleStep("allocate", busyAllocate).catch(() => null);
  if (d) ElMessage.success(`配货完成：订单 ${d.orders_allocated}，分单行 ${d.allocations_created}${skipNote(d)}`);
}
async function pickupOrders() {
  const d = await demoLifecycleStep("pickup", busyPickup).catch(() => null);
  if (d) ElMessage.success(`取货→发货：推进 ${d.advanced?.length || 0}${skipNote(d)}`);
}
async function deliverOrders() {
  const d = await demoLifecycleStep("deliver", busyDeliver).catch(() => null);
  if (d) ElMessage.success(`送达→收货：推进 ${d.advanced?.length || 0}${skipNote(d)}`);
}
async function receiveOrders() {
  const d = await demoLifecycleStep("receive", busyReceive).catch(() => null);
  if (d) ElMessage.success(`收货确认：推进 ${d.advanced?.length || 0}，生成账单 ${d.bills_created || 0}${skipNote(d)}`);
}
async function settleOrders() {
  const d = await demoLifecycleStep("settle", busySettle).catch(() => null);
  if (d) ElMessage.success(`结算：推进 ${d.advanced?.length || 0}，结算账单 ${d.bills_settled || 0}/对账单 ${d.statements_settled || 0}${skipNote(d)}`);
}

/** 一键串跑：配货→发货(标已出库,含指定厂家)→取货→送达→收货确认→结算 */
async function runFullChain() {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return;
  }
  busyFullChain.value = true;
  const steps = [
    ["allocate", "配货"],
    ["mark-allocations-shipped", "发货"],
    ["pickup", "取货"],
    ["deliver", "送达"],
    ["receive", "收货确认"],
    ["settle", "结算"],
  ];
  try {
    for (const [path, label] of steps) {
      const r = await clientAxios(monitorToken.value).post(`/demo/orders/${path}`, { order_ids: ids });
      pushLog(`链路·${label} OK ${JSON.stringify(r.data).slice(0, 140)}`);
    }
    ElMessage.success("已跑完整履约链路：下单→配货→发货→送达→收货确认→结算");
  } catch (e) {
    ElMessage.error(`链路在某步中断：${e.response?.data?.detail || e.message}（可单步排查）`);
  } finally {
    busyFullChain.value = false;
  }
}

function applyTianshuStatus(payload) {
  const d = payload || {};
  Object.assign(tianshuBatchStatus, {
    exists: Boolean(d.exists),
    orders: Number(d.orders || 0),
    allocations: Number(d.allocations || 0),
    sort_scan_records: Number(d.sort_scan_records || 0),
    dispatch_trips: Number(d.dispatch_trips || 0),
    dispatch_items: Number(d.dispatch_items || 0),
    returns: Number(d.returns || 0),
    bills: Number(d.bills || 0),
    alerts: Number(d.alerts || 0),
    notifications: Number(d.notifications || 0),
    latest_order_no: d.latest_order_no || "",
    delivery_date: d.delivery_date || "",
  });
}

async function refreshTianshuStatus({ silent = false } = {}) {
  if (!monitorToken.value) {
    if (!silent) ElMessage.warning("请先监管登录");
    return;
  }
  busyTianshuStatus.value = true;
  try {
    const r = await clientAxios(monitorToken.value).get("/demo/tianshu/status");
    applyTianshuStatus(r.data || {});
    if (!silent) ElMessage.success("天枢批次状态已刷新");
  } catch (e) {
    if (!silent) ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busyTianshuStatus.value = false;
  }
}

function openTianshuScreen() {
  const { protocol, hostname, port, origin } = window.location;
  const devConsolePorts = new Set(["5173", "5174", "5175", "5176", "5177", "5178", "5179"]);
  const base = devConsolePorts.has(port) ? `${protocol}//${hostname}` : origin;
  window.open(`${base}/tianshu/`, "_blank", "noopener,noreferrer");
}

async function seedTianshuRealData() {
  if (!monitorToken.value) {
    ElMessage.warning("请先监管登录");
    return;
  }
  busyTianshuSeed.value = true;
  try {
    const r = await clientAxios(monitorToken.value).post("/demo/tianshu/seed", {
      order_count: Number(form.tianshuOrderCount || 36),
      delivery_username: (form.deliveryUsername || "delivery001").trim(),
      clear_existing: true,
    });
    const d = r.data || {};
    const ids = Array.isArray(d.order_ids) ? d.order_ids : [];
    demoOrderIdsText.value = ids.join(", ");
    tianshuBatchSummary.value = `已生成 ${d.inserted_orders || 0} 单、${d.dispatch_trips || 0} 个车次、${d.alerts || 0} 条预警、${d.returns || 0} 条退单、${d.bills || 0} 条账单。`;
    await refreshTianshuStatus({ silent: true });
    pushLog(`demo tianshu/seed OK orders=${d.inserted_orders || 0} trips=${d.dispatch_trips || 0} alerts=${d.alerts || 0}`);
    ElMessage.success("天枢真实模式演示数据已生成，已填入本批 order_id");
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
    pushLog("demo tianshu/seed FAIL");
  } finally {
    busyTianshuSeed.value = false;
  }
}

function openClearTianshuDialog() {
  clearTianshuDialog.confirm = "";
  clearTianshuDialog.visible = true;
}

async function confirmClearTianshuData() {
  if (!monitorToken.value) {
    ElMessage.warning("请先监管登录");
    return;
  }
  busyTianshuClear.value = true;
  try {
    const r = await clientAxios(monitorToken.value).post("/demo/tianshu/clear");
    const summary = cleanupSummaryText(r.data);
    tianshuBatchSummary.value = `已清除：${summary}`;
    demoOrderIdsText.value = "";
    applyTianshuStatus({});
    pushLog(`demo tianshu/clear OK ${summary}`);
    ElMessage.success(`天枢批次清理完成：${summary}`);
    clearTianshuDialog.visible = false;
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
    pushLog("demo tianshu/clear FAIL");
  } finally {
    busyTianshuClear.value = false;
  }
}

onMounted(() => {
  if (!form.expectedDate) {
    form.expectedDate = todayStr();
  }
  loadClientList();
  loadSupplierList();
});

watch(
  () => `${form.apiPreset}|${form.apiBaseCustom}`,
  () => {
    scheduleClientReload();
  }
);

async function runValidate() {
  validateOk.value = null;
  validateIssues.value = [];
  metaPreview.value = "";
  resolvedDeliveryId.value = null;
  if (!form.expectedDate) {
    ElMessage.error("请选择期望配送日");
    return;
  }
  const choiceKeys = (form.clients || []).map((c) => String(c).trim()).filter(Boolean);
  if (!choiceKeys.length) {
    ElMessage.error("请至少选择一所食堂（或输入登录名；未带食堂 id 时将自动选默认食堂）");
    return;
  }
  busyValidate.value = true;
  try {
    const { username: firstUser } = parseClientChoice(choiceKeys[0]);
    const ax0 = clientAxios();
    const login0 = await timed(`login ${firstUser}`, () =>
      ax0.post("/auth/login", { username: firstUser, password: form.password }).then((r) => r.data)
    );
    const token0 = login0.token;
    const ax = clientAxios(token0);
    const meta = await timed("GET /orders/meta", () => ax.get("/orders/meta").then((r) => r.data));
    const du = (form.deliveryUsername || "").trim();
    const hit = (meta.deliveries || []).find((d) => d.username === du);
    if (!hit) {
      validateIssues.value.push(`在单位登录名 ${firstUser} 的 orders/meta 中未找到配送商用户名「${du}」；请确认该登录名对 ${du} 已有「已中标」且合约期含今日。`);
      validateOk.value = false;
      return;
    }
    resolvedDeliveryId.value = hit.id;
    const meta2 = await timed(`GET /orders/meta?delivery_id=${hit.id}`, () =>
      ax.get("/orders/meta", { params: { delivery_id: hit.id } }).then((r) => r.data)
    );
    metaPreview.value = JSON.stringify(meta2, null, 2);

    if (!form.randomDeliverySlot) {
      const slot = (form.expectedSlot || "").trim();
      if (!/^\d{2}:\d{2}-\d{2}:\d{2}$/.test(slot)) {
        validateIssues.value.push("固定模式下配送时段格式须如 09:00-10:00");
      }
    }

    const today = todayStr();
    for (const key of choiceKeys) {
      const { username: u, canteenId } = parseClientChoice(key);
      const who = canteenId != null ? `${u}（食堂 id ${canteenId}）` : u;
      try {
        const axC = clientAxios();
        const lgRes = await axC.post("/auth/login", { username: u, password: form.password });
        const lg = lgRes.data;
        let scoped = lg.token;
        try {
          scoped = await ensureClientCanteenToken(lg.token, undefined, canteenId);
        } catch (e) {
          const msg = e.response?.data?.detail || e.message || String(e);
          validateIssues.value.push(`「${who}」：无法绑定食堂会话 — ${msg}`);
          continue;
        }
        const contracts = await clientAxios(scoped).get("/client/contracts").then((r) => r.data);
        const list = Array.isArray(contracts) ? contracts : [];
        const rel = list.filter((ct) => ct.delivery_id === hit.id && ct.status === "已中标");
        if (!rel.length) {
          validateIssues.value.push(`「${who}」没有指向 ${du} 的「已中标」合约`);
          continue;
        }
        const okContract = rel.find((ct) => {
          const ps = String(ct.period_start).slice(0, 10);
          const pe = String(ct.period_end).slice(0, 10);
          return (
            ps <= form.expectedDate &&
            pe >= form.expectedDate &&
            ps <= today &&
            pe >= today
          );
        });
        if (!okContract) {
          validateIssues.value.push(
            `「${who}」：没有同时覆盖「今日(${today})」与「配送日 ${form.expectedDate}」的已中标合约（与后端下单校验一致）`
          );
        }
      } catch (e) {
        const detail = e.response?.data?.detail;
        const msg = typeof detail === "string" ? detail : e.message || String(e);
        validateIssues.value.push(`「${who}」：登录或获取合约失败 — ${msg}`);
      }
    }

    if (validateIssues.value.length) {
      validateOk.value = false;
    } else {
      validateOk.value = true;
      ElMessage.success("校验通过");
    }
  } catch (e) {
    validateOk.value = false;
    const detail = e.response?.data?.detail;
    const msg = typeof detail === "string" ? detail : e.message || String(e);
    if (!validateIssues.value.length) {
      validateIssues.value.push(`请求失败：${msg}`);
    } else {
      validateIssues.value.push(`前置步骤失败：${msg}`);
    }
  } finally {
    busyValidate.value = false;
  }
}

function cancelPlace() {
  if (placeAbort.value) placeAbort.value.abort();
}

async function runPlaceOrders() {
  if (validateOk.value !== true || !resolvedDeliveryId.value) {
    ElMessage.warning("请先通过校验");
    return;
  }
  const choiceKeys = (form.clients || []).map((c) => String(c).trim()).filter(Boolean);
  const deliveryId = resolvedDeliveryId.value;
  const signal = new AbortController();
  placeAbort.value = signal;
  busyPlace.value = true;
  resultRows.value = [];
  let globalIdx = 0;
  try {
    for (const key of choiceKeys) {
      if (signal.signal.aborted) break;
      const { username: u, canteenId } = parseClientChoice(key);
      const who = canteenId != null ? `${u}·#${canteenId}` : u;
      const lg0 = await clientAxios().post(
        "/auth/login",
        { username: u, password: form.password },
        { signal: signal.signal }
      );
      let clientToken = lg0.data.token;
      clientToken = await timed(`POST /client/canteen-session (${who})`, () =>
        ensureClientCanteenToken(clientToken, signal.signal, canteenId)
      );
      const searchBase = { delivery_id: deliveryId };
      if (form.productKeyword.trim()) searchBase.keyword = form.productKeyword.trim();
      if (form.contractCategoriesOnly) {
        searchBase.contract_categories_only = true;
        searchBase.expected_delivery_date = form.expectedDate;
      }
      const wantPool = Math.max(
        80,
        form.linesPerOrder * Math.max(form.ordersPerClient * 4, 12),
      );
      const pool = await timed(`GET /orders/products/search 多页 (${who})`, () =>
        fetchMergedProductPool(clientToken, searchBase, signal.signal, wantPool)
      );
      if (pool.length < form.linesPerOrder) {
        ElMessage.error(
          `「${who}」：合约内可下单商品不足 ${form.linesPerOrder} 条（当前 ${pool.length}）。请改关键词、换配送日或关闭「仅合约内商品」。`
        );
        busyPlace.value = false;
        placeAbort.value = null;
        return;
      }
      if (pool.length < form.linesPerOrder * form.ordersPerClient) {
        pushLog(
          `「${who}」：合约内 SKU 仅 ${pool.length} 条，少于 行数×笔数=${form.linesPerOrder * form.ordersPerClient}，多笔将复用 SKU，已加大笔间数量差。`,
        );
      }

      const usedProductIds = new Set();

      for (let oi = 0; oi < form.ordersPerClient; oi++) {
        if (signal.signal.aborted) break;
        const slotForOrder = form.randomDeliverySlot ? randomDeliverySlot() : (form.expectedSlot || "").trim();
        const row = {
          client: who,
          index: ++globalIdx,
          orderNo: "",
          orderId: "",
          status: "",
          slot: slotForOrder,
          ms: "",
          error: "",
        };
        const t0 = performance.now();
        try {
          const token = clientToken;
          const subset = pickProductsForOrder(
            pool,
            form.linesPerOrder,
            oi,
            form.ordersPerClient,
            u,
            usedProductIds,
          );
          const baseQty = Math.max(1, Math.floor(Number(form.lineQuantity) || 1));
          // 与后端 OrderItemIn 一致：须传 unit_price（服务端会按合约重算并覆盖，但请求体校验必填）
          const picked = subset.map((p, li) => {
            const unit =
              p.contract_unit_price != null && p.contract_unit_price !== ""
                ? Number(p.contract_unit_price)
                : Number(p.guide_price ?? p.reference_price ?? 0);
            const quantity = lineQuantityForDemo(baseQty, oi, li, u);
            return {
              product_id: Number(p.id),
              quantity,
              unit_price: Number.isFinite(unit) && unit > 0 ? unit : 0.01,
            };
          });
          const seed = seedForClient(u);
          const off = globalIdx * (form.coordStep || 0);
          const lng = seed.lng + off;
          const lat = seed.lat + off;
          const body = {
            delivery_id: deliveryId,
            items: picked,
            delivery_address: seed.address,
            delivery_lng: lng,
            delivery_lat: lat,
            expected_delivery_date: form.expectedDate,
            expected_delivery_slot: slotForOrder,
            service_duration_min: form.serviceDurationMin,
            force: !!form.force,
          };
          const ord = await clientAxios(token).post("/orders", body, { signal: signal.signal });
          const data = ord.data;
          if (data && data.need_confirm) {
            row.status = "失败";
            row.error = "存在异常商品需确认：可开启「无视异常商品校验」或确认已勾选「仅合约内商品」";
            row.ms = String(Math.round(performance.now() - t0));
            resultRows.value.push(row);
            continue;
          }
          row.orderNo = data.order_no || "";
          row.orderId = data.id != null ? String(data.id) : "";
          row.status = "成功";
          row.ms = String(Math.round(performance.now() - t0));
          for (const p of subset) {
            const id = Number(p.id);
            if (Number.isFinite(id) && id > 0) usedProductIds.add(id);
          }
          pushLog(`POST /orders ${who} #${oi + 1} OK id=${row.orderId} slot=${slotForOrder}`);
        } catch (e) {
          row.status = "失败";
          row.ms = String(Math.round(performance.now() - t0));
          const detail = e.response?.data?.detail;
          row.error = formatHttpDetail(detail) || String(e.message || e);
          pushLog(`POST /orders ${who} FAIL`);
        }
        resultRows.value.push(row);
      }
    }
    if (!signal.signal.aborted) ElMessage.success("批量下单结束");
  } catch (e) {
    if (e.code === "ERR_CANCELED" || e.name === "CanceledError") ElMessage.info("已取消");
    else ElMessage.error(String(e.message || e));
  } finally {
    busyPlace.value = false;
    placeAbort.value = null;
  }
}

function showErr(t) {
  errDialog.text = t;
  errDialog.visible = true;
}

/** 422 校验错误常为数组，转成可读字符串便于表格「查看」 */
function formatHttpDetail(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((x) => {
        if (!x || typeof x !== "object") return String(x);
        const loc = Array.isArray(x.loc) ? x.loc.filter(Boolean).join(".") : "";
        const msg = x.msg || x.message || "";
        return loc ? `${loc}: ${msg}` : msg || JSON.stringify(x);
      })
      .filter(Boolean)
      .join("；");
  }
  return JSON.stringify(detail);
}

function fillIdsFromResults() {
  const ids = resultRows.value.filter((r) => r.orderId && r.status === "成功").map((r) => r.orderId);
  demoOrderIdsText.value = ids.join(", ");
}

async function monitorLogin() {
  busyMonLogin.value = true;
  try {
    const r = await clientAxios().post("/auth/login", {
      username: monitorForm.username.trim(),
      password: monitorForm.password,
    });
    monitorToken.value = r.data.token;
    if (r.data.role !== "monitor") ElMessage.warning("该账号角色不是 monitor，演示接口可能被拒绝");
    else {
      ElMessage.success("监管登录成功");
      await refreshTianshuStatus({ silent: true });
    }
  } catch (e) {
    monitorToken.value = "";
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busyMonLogin.value = false;
  }
}

async function markAllocationsShipped() {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return;
  }
  busyMarkShipped.value = true;
  try {
    await clientAxios(monitorToken.value).post("/demo/orders/mark-allocations-shipped", { order_ids: ids });
    ElMessage.success("已更新分单行状态");
    pushLog(`demo mark-allocations-shipped OK ids=${ids.join(",")}`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busyMarkShipped.value = false;
  }
}

function openDeleteDialog() {
  deleteDialog.confirm = "";
  deleteDialog.visible = true;
}

async function confirmDeleteOrders() {
  const ids = parseOrderIds(demoOrderIdsText.value);
  if (!ids.length) {
    ElMessage.warning("请填写 order_id");
    return;
  }
  busyDelete.value = true;
  try {
    const r = await clientAxios(monitorToken.value).post("/demo/orders/delete", { order_ids: ids });
    const summary = cleanupSummaryText(r.data);
    ElMessage.success(`删单完成：${summary}`);
    pushLog(`demo orders/delete OK ${summary}`);
    deleteDialog.visible = false;
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busyDelete.value = false;
  }
}

function openClearAllDialog() {
  clearAllDialog.confirm = "";
  clearAllDialog.visible = true;
}

async function confirmClearAllOrders() {
  busyClearAll.value = true;
  try {
    const r = await clientAxios(monitorToken.value).post("/demo/orders/clear-all");
    const summary = cleanupSummaryText(r.data);
    ElMessage.success(`清理完成：${summary}`);
    pushLog(`demo orders/clear-all OK ${summary}`);
    clearAllDialog.visible = false;
    resultRows.value = [];
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || e.message);
  } finally {
    busyClearAll.value = false;
  }
}

</script>

<style scoped>
.page {
  max-width: 920px;
  margin: 0 auto;
  padding: 16px 16px 40px;
  background: linear-gradient(180deg, #eef1f6 0%, #f4f5f7 120px);
  min-height: 100vh;
  box-sizing: border-box;
}
.hdr h1 {
  font-size: 1.35rem;
  font-weight: 600;
  margin: 0 0 6px;
  color: #1a1a2e;
  letter-spacing: -0.02em;
}
.sub {
  margin: 0 0 12px;
  font-size: 0.85rem;
  color: #666;
}
.model-banner :deep(.el-alert__title) {
  font-size: 0.95rem;
}
.model-p {
  margin: 6px 0 0;
  font-size: 0.82rem;
  line-height: 1.55;
  color: #444;
}
.model-p code {
  font-size: 0.8em;
  padding: 0 4px;
  background: #eef3f8;
  border-radius: 3px;
}
.blk {
  margin-bottom: 14px;
  border-radius: 10px;
  border: 1px solid #e4e7ed;
  overflow: hidden;
}
.blk :deep(.el-card__header) {
  font-weight: 600;
  color: #303133;
  background: #fafbfc;
  border-bottom: 1px solid #eef0f3;
}
.step-flow__title {
  font-weight: 600;
}
.step-flow__list {
  margin: 0 0 12px 1.1rem;
  padding: 0;
  font-size: 0.88rem;
  line-height: 1.65;
  color: #3a3f4a;
}
.step-flow__list li {
  margin-bottom: 6px;
}
.step-flow__list code {
  font-size: 0.82em;
  padding: 1px 6px;
  background: #f0f4f8;
  border-radius: 4px;
}
.step-flow__warn {
  margin-top: 4px;
}
.ship-all-btn {
  width: 100%;
  margin-top: 10px;
}
.full-chain-btn {
  width: 100%;
}
.chain-step-row {
  margin-top: 10px;
}
.monitor {
  border-left: 3px solid #409eff;
}
.monitor-login-hint {
  margin-bottom: 12px;
}
.tianshu-demo-panel {
  margin: 14px 0;
  padding: 14px;
  border: 1px solid rgba(64, 158, 255, 0.24);
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(9, 23, 46, 0.96), rgba(15, 47, 72, 0.92)),
    radial-gradient(circle at 80% 20%, rgba(64, 210, 255, 0.18), transparent 34%);
  color: #eaf7ff;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
}
.tianshu-demo-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}
.tianshu-demo-panel__title {
  font-size: 0.98rem;
  font-weight: 700;
  letter-spacing: 0;
}
.tianshu-demo-panel p {
  margin: 6px 0 0;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(234, 247, 255, 0.76);
}
.tianshu-demo-panel code {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(64, 210, 255, 0.14);
  color: #9eeeff;
}
.tianshu-demo-panel__status {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}
.tianshu-demo-panel__status > div {
  min-width: 0;
  padding: 10px 11px;
  border: 1px solid rgba(123, 220, 255, 0.18);
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(15, 51, 83, 0.78), rgba(8, 25, 46, 0.78)),
    radial-gradient(circle at 85% 18%, rgba(77, 220, 255, 0.16), transparent 42%);
  box-shadow: inset 0 0 20px rgba(37, 188, 255, 0.06);
}
.tianshu-demo-panel__status span,
.tianshu-demo-panel__status small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tianshu-demo-panel__status span {
  font-size: 0.72rem;
  color: rgba(199, 236, 255, 0.68);
}
.tianshu-demo-panel__status b {
  display: block;
  margin-top: 3px;
  font-size: 1rem;
  color: #dffbff;
}
.tianshu-demo-panel__status small {
  margin-top: 3px;
  font-size: 0.7rem;
  color: rgba(189, 248, 222, 0.78);
}
.tianshu-demo-panel__status .is-empty b {
  color: #ffd18a;
}
.tianshu-demo-panel__controls {
  margin-top: 12px;
}
.tianshu-demo-panel__summary {
  color: #bdf8de !important;
}
@media (max-width: 860px) {
  .tianshu-demo-panel__head {
    flex-direction: column;
  }
  .tianshu-demo-panel__status {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 520px) {
  .tianshu-demo-panel__status {
    grid-template-columns: 1fr;
  }
}
.btn-wrap {
  display: inline-block;
}
.meta-pre {
  margin-top: 10px;
}
.meta-title {
  font-size: 0.8rem;
  color: #888;
  margin-bottom: 4px;
}
.meta-expl {
  font-size: 0.78rem;
  color: #555;
  line-height: 1.5;
  margin: 0 0 8px;
}
.meta-pre pre {
  margin: 0;
  font-size: 11px;
  overflow: auto;
  max-height: 220px;
  background: #fff;
  padding: 8px;
  border-radius: 6px;
  border: 1px solid #e8e8e8;
}
.hint {
  font-size: 0.8rem;
  color: #888;
  margin-top: 8px;
}
.field-hint {
  font-size: 0.78rem;
  color: #666;
  line-height: 1.45;
  margin: 8px 0 0;
}
.field-custom {
  margin-top: 10px;
}
.slot-below {
  margin-top: 8px;
}
.table-wrap {
  overflow-x: auto;
}
.log-lines {
  max-height: 240px;
  overflow: auto;
  font-size: 12px;
  font-family: ui-monospace, monospace;
  background: #1e1e1e;
  color: #c8e6c9;
  padding: 8px;
  border-radius: 6px;
}
.log-line {
  margin-bottom: 4px;
  word-break: break-all;
}
.monitor :deep(.el-card__header) {
  font-size: 0.95rem;
}
.err-pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  margin: 0;
}
</style>
