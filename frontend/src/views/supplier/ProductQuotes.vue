<script setup>
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { listSupplierProductQuotesApi, saveSupplierProductQuotesApi } from '../../api/supplier'

const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
/** 报价筛选：all | quoted | unquoted */
const quoteStatus = ref('all')
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
const pricingStatus = ref('ok')
const rows = ref([])

const dirtyRows = computed(() => rows.value.filter((i) => i._dirty))

const markDirty = (row) => {
  row._dirty = true
}

const normalizePrice = (row) => {
  if (row.my_quote_price == null || row.my_quote_price === '') return
  const num = Number(row.my_quote_price)
  if (Number.isNaN(num)) return
  row.my_quote_price = Math.round(num * 100) / 100
}

const load = async () => {
  loading.value = true
  try {
    const res = await listSupplierProductQuotesApi({
      keyword: keyword.value || undefined,
      quote_status: quoteStatus.value !== 'all' ? quoteStatus.value : undefined,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = (res.items || []).map((item) => ({
      ...item,
      _dirty: false,
    }))
    total.value = Number(res.total || 0)
    pricingStatus.value = res.pricing_status || 'ok'
  } finally {
    loading.value = false
  }
}

const submitChanged = async () => {
  const payloadItems = dirtyRows.value
    .filter((i) => i.my_quote_price !== null && i.my_quote_price !== '')
    .map((i) => ({
      product_id: i.product_id,
      quote_price: Number(i.my_quote_price),
    }))

  if (!payloadItems.length) {
    ElMessage.warning('请至少填写一条有效报价后保存')
    return
  }
  if (payloadItems.some((i) => Number.isNaN(i.quote_price) || i.quote_price <= 0)) {
    ElMessage.warning('报价必须是大于0的数字')
    return
  }

  saving.value = true
  try {
    await saveSupplierProductQuotesApi({ items: payloadItems })
    ElMessage.success('报价保存成功')
    await load()
  } finally {
    saving.value = false
  }
}

const onSearch = () => {
  page.value = 1
  load()
}

const onQuoteStatusChange = () => {
  page.value = 1
  load()
}

const rateDisplay = (val) => {
  if (val == null) return '--'
  return `${(Number(val) * 100).toFixed(2)}%`
}

onMounted(load)
</script>

<template>
  <el-card class="mb-3">
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="按商品名称/编码搜索"
        clearable
        style="width: 300px"
        @keyup.enter="onSearch"
        @clear="onSearch"
      />
      <el-select
        v-model="quoteStatus"
        placeholder="报价状态"
        style="width: 140px"
        @change="onQuoteStatusChange"
      >
        <el-option label="全部" value="all" />
        <el-option label="已报价" value="quoted" />
        <el-option label="未报价" value="unquoted" />
      </el-select>
      <div class="toolbar-actions">
        <el-button @click="onSearch">查询</el-button>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="submitChanged">
          批量保存（{{ dirtyRows.length }}）
        </el-button>
      </div>
    </div>
    <div v-if="pricingStatus !== 'ok'" class="status-tip">
      当前未匹配到生效合约，浮动后价格暂不可用。
    </div>
  </el-card>

  <el-card>
    <template #header>
      <span class="font-semibold">商品报价</span>
      <span class="text-xs text-slate-500 font-normal ml-2">报给分包配送商，供其对终端订单做智能分包与比价，非终端客户直连。</span>
    </template>
    <el-table v-loading="loading" :data="rows" border row-key="product_id">
      <el-table-column label="缩略图" width="90" align="center">
        <template #default="{ row }">
          <el-image
            v-if="row.thumb_url || row.logo"
            :src="row.thumb_url || row.logo"
            fit="cover"
            style="width: 48px; height: 48px; border-radius: 6px"
            :preview-src-list="[row.thumb_url || row.logo]"
            preview-teleported
          />
          <span v-else>--</span>
        </template>
      </el-table-column>
      <el-table-column prop="goods_sn" label="商品编码" min-width="130" />
      <el-table-column prop="product_name" label="商品名称" min-width="180" />
      <el-table-column prop="category1_name" label="一级分类" min-width="120" />
      <el-table-column label="系统参考价" width="130">
        <template #default="{ row }">¥{{ Number(row.reference_price || 0).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="浮动率" width="120">
        <template #default="{ row }">{{ rateDisplay(row.category_float_rate) }}</template>
      </el-table-column>
      <el-table-column label="浮动后价格" width="130">
        <template #default="{ row }">
          <span v-if="row.floating_price != null">¥{{ Number(row.floating_price).toFixed(2) }}</span>
          <span v-else>--</span>
        </template>
      </el-table-column>
      <el-table-column label="我的报价" width="170">
        <template #default="{ row }">
          <el-input-number
            v-model="row.my_quote_price"
            :min="0"
            :precision="2"
            :step="0.1"
            controls-position="right"
            @change="markDirty(row)"
            @blur="normalizePrice(row)"
          />
        </template>
      </el-table-column>
      <el-table-column label="变更" width="90" align="center">
        <template #default="{ row }">
          <el-tag v-if="row._dirty" type="warning">待保存</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        @change="load"
      />
    </div>
  </el-card>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.status-tip {
  margin-top: 10px;
  font-size: 13px;
  color: #b45309;
}
</style>
