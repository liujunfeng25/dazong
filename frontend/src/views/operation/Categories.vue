<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  Search,
  Plus,
  Edit,
  Delete,
  RefreshLeft,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  createCategoryApi,
  deleteCategoryApi,
  listCategoriesApi,
  updateCategoryApi,
  uploadCategoryImageApi,
} from '../../api/operation'
import { resolveCategoryImage, CATEGORY_EMOJI_PALETTE } from '../../utils/categoryImage'

const list = ref([])
const loading = ref(false)
const tableKey = ref(0)
const drawerVisible = ref(false)
const isEditing = ref(false)
const form = reactive({ id: null, name: '', level: 1, parent_id: null, sort_order: 0, max_float_rate: 1, image_url: null })

// —— 分类图片 ——
const emojiPalette = CATEGORY_EMOJI_PALETTE
const emojiPanelVisible = ref(false)
const uploadingImage = ref(false)
const catImage = (row) => resolveCategoryImage(row?.name, row?.image_url)
const formImage = computed(() => resolveCategoryImage(form.name, form.image_url))
const pickEmoji = (glyph) => {
  form.image_url = `emoji:${glyph}`
  emojiPanelVisible.value = false
}
const clearImage = () => { form.image_url = null }
const onUploadImage = async (e) => {
  const file = e?.target?.files?.[0]
  if (!file) return
  uploadingImage.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    const res = await uploadCategoryImageApi(fd)
    form.image_url = res?.url || res?.data?.url || null
    ElMessage.success('图片已上传')
  } finally {
    uploadingImage.value = false
    if (e?.target) e.target.value = ''
  }
}

// —— 筛选状态（纯前端，不触后端）——
const keyword = ref('')
const levelFilter = ref(null)
const parentFilter = ref(null)

const level1Options = computed(() => list.value.filter((item) => item.level === 1))
const categoryNameMap = computed(() => Object.fromEntries(list.value.map((item) => [item.id, item.name])))
const level1Count = computed(() => list.value.filter((i) => i.level === 1).length)
const level2Count = computed(() => list.value.filter((i) => i.level === 2).length)

const hasFilter = computed(
  () => !!keyword.value.trim() || levelFilter.value != null || parentFilter.value != null,
)
// 有筛选时展开命中项，便于看到二级匹配；无筛选时默认收起，页面更清爽
const expandAll = computed(() => hasFilter.value)

const byOrder = (a, b) => (a.sort_order - b.sort_order) || (a.id - b.id)

/** 扁平 → 过滤后的两级树（一级行挂 children=二级行） */
const treeData = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  const kwActive = kw !== ''
  const lvl = levelFilter.value
  const parent = parentFilter.value
  const nameHit = (n) => (n?.name || '').toLowerCase().includes(kw)

  const level1 = list.value.filter((i) => i.level === 1).slice().sort(byOrder)
  const level2 = list.value.filter((i) => i.level === 2)
  const childrenOf = (pid) => level2.filter((c) => c.parent_id === pid).slice().sort(byOrder)

  const rows = []
  for (const p of level1) {
    if (parent != null && p.id !== parent) continue
    const pMatch = !kwActive || nameHit(p)

    let kids = []
    if (lvl !== 1) {
      const raw = childrenOf(p.id)
      // 父级名命中关键词 → 展示其全部子类；否则只展示命中关键词的子类
      kids = !kwActive || pMatch ? raw : raw.filter(nameHit)
    }

    let include
    if (lvl === 1) include = pMatch
    else if (lvl === 2) include = kids.length > 0
    else include = pMatch || kids.length > 0

    if (include) rows.push({ ...p, children: kids })
  }

  // 脏数据兜底：父级缺失的二级，命中筛选时挂到根，避免丢行
  if (parent == null && lvl !== 1) {
    const known = new Set(level1.map((i) => i.id))
    for (const c of level2) {
      if (known.has(c.parent_id)) continue
      if (!kwActive || nameHit(c)) rows.push({ ...c })
    }
  }
  return rows
})

const fmtRate = (v) => `${(Number(v ?? 0) * 100).toFixed(2)}%`
const rowClass = ({ row }) => (row.level === 1 ? 'cat-row-l1' : 'cat-row-l2')

const resetFilters = () => {
  keyword.value = ''
  levelFilter.value = null
  parentFilter.value = null
}
// 筛选变化时强制 el-table 按当前 expandAll 重渲染（复用 Products 的 tableKey 手法）
watch([keyword, levelFilter, parentFilter], () => {
  tableKey.value += 1
})

const resetForm = () => {
  Object.assign(form, { id: null, name: '', level: 1, parent_id: null, sort_order: 0, max_float_rate: 1, image_url: null })
}

const load = async () => {
  loading.value = true
  try {
    list.value = await listCategoriesApi()
  } finally {
    loading.value = false
  }
}
const onLevelChange = (value) => {
  if (value === 1) form.parent_id = null
  if (value === 2) form.max_float_rate = 1
}
const submit = async () => {
  const payload = { ...form }
  if (payload.level === 1) payload.parent_id = null
  if (payload.level === 2) delete payload.max_float_rate
  if (form.id) await updateCategoryApi(form.id, payload)
  else await createCategoryApi(payload)
  resetForm()
  drawerVisible.value = false
  await load()
}
const openCreate = () => {
  isEditing.value = false
  resetForm()
  drawerVisible.value = true
}
// 一级行行内「+二级」：复用新增逻辑，仅预填 level/parent，不引入新业务
const addChild = (row) => {
  isEditing.value = false
  resetForm()
  form.level = 2
  form.parent_id = row.id
  drawerVisible.value = true
}
const edit = (row) => {
  isEditing.value = true
  const { children, ...rest } = row
  Object.assign(form, {
    ...rest,
    max_float_rate: row.level === 1 ? Number(row.max_float_rate ?? 1) : 1,
  })
  drawerVisible.value = true
}
const remove = async (id) => {
  await ElMessageBox.confirm('确认删除该分类吗？', '删除确认', { type: 'warning' })
  await deleteCategoryApi(id)
  await load()
}
onMounted(load)
</script>

<template>
  <div class="cat-page">
    <!-- 页头 -->
    <header class="cat-header">
      <div class="cat-title">
        <h2>商品分类</h2>
        <p class="cat-sub">维护两级商品分类树；一级分类的上浮率上限约束配送商投标报价。</p>
      </div>
      <div class="cat-summary">
        <span class="sum-pill"><b>{{ level1Count }}</b><i>一级</i></span>
        <span class="sum-sep" />
        <span class="sum-pill"><b>{{ level2Count }}</b><i>二级</i></span>
      </div>
    </header>

    <!-- 工具栏 -->
    <el-card class="cat-card cat-toolbar-card" shadow="never">
      <div class="crud-toolbar">
        <el-form inline class="crud-form">
          <el-form-item>
            <el-input
              v-model="keyword"
              placeholder="搜索分类名称"
              clearable
              :prefix-icon="Search"
              style="width: 220px"
            />
          </el-form-item>
          <el-form-item>
            <el-select v-model="levelFilter" clearable placeholder="层级" style="width: 130px">
              <el-option :value="1" label="一级分类" />
              <el-option :value="2" label="二级分类" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-select v-model="parentFilter" clearable placeholder="所属一级分类" style="width: 180px">
              <el-option v-for="item in level1Options" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button :icon="RefreshLeft" :disabled="!hasFilter" @click="resetFilters">重置</el-button>
          </el-form-item>
        </el-form>
        <div class="crud-actions">
          <el-button type="primary" :icon="Plus" @click="openCreate">新增分类</el-button>
        </div>
      </div>
    </el-card>

    <!-- 树形表格 -->
    <el-card class="cat-card cat-table-card" shadow="never">
      <el-table
        :key="tableKey"
        v-loading="loading"
        :data="treeData"
        row-key="id"
        :tree-props="{ children: 'children' }"
        :default-expand-all="expandAll"
        :indent="20"
        class="cat-table"
        :row-class-name="rowClass"
      >
        <el-table-column label="分类名称" min-width="300">
          <template #default="{ row }">
            <div class="cat-name" :class="row.level === 1 ? 'is-l1' : 'is-l2'">
              <span class="cat-thumb" :style="catImage(row).type === 'emoji' ? { background: catImage(row).bg } : null">
                <img v-if="catImage(row).type === 'photo'" :src="catImage(row).src" :alt="row.name" />
                <span v-else>{{ catImage(row).glyph }}</span>
              </span>
              <span class="cat-name-text">{{ row.name }}</span>
              <el-tag
                v-if="row.level === 1 && row.children && row.children.length"
                size="small"
                type="info"
                effect="plain"
                round
                class="cat-count"
              >{{ row.children.length }} 个子类</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="层级" width="110" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.level === 1 ? 'primary' : 'info'" effect="light" round>
              {{ row.level === 1 ? '一级' : '二级' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="上浮率上限" width="150" align="center">
          <template #default="{ row }">
            <span v-if="row.level === 1" class="rate-pill">{{ fmtRate(row.max_float_rate) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="排序" width="90" align="center">
          <template #default="{ row }"><span class="muted">{{ row.sort_order }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="right">
          <template #default="{ row }">
            <div class="op-btns">
              <el-button v-if="row.level === 1" link type="primary" :icon="Plus" @click="addChild(row)">
                二级
              </el-button>
              <el-button link type="primary" :icon="Edit" @click="edit(row)">编辑</el-button>
              <el-button link type="danger" :icon="Delete" @click="remove(row.id)">删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty
            :description="hasFilter ? '没有符合筛选条件的分类' : '还没有任何分类，点击右上角“新增分类”开始'"
          />
        </template>
      </el-table>
    </el-card>

    <!-- 新增 / 编辑抽屉 -->
    <el-drawer v-model="drawerVisible" :title="isEditing ? '编辑分类' : '新增分类'" size="460px">
      <el-form label-width="110px" class="cat-form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="请输入分类名称" />
        </el-form-item>
        <el-form-item label="分类图片">
          <div class="cat-img-field">
            <span
              class="cat-img-preview"
              :style="formImage.type === 'emoji' ? { background: formImage.bg } : null"
            >
              <img v-if="formImage.type === 'photo'" :src="formImage.src" alt="分类图片" />
              <span v-else>{{ formImage.glyph }}</span>
            </span>
            <div class="cat-img-ops">
              <div class="cat-img-btns">
                <el-button size="small" :loading="uploadingImage" @click="$refs.catImgInput.click()">上传图片</el-button>
                <el-button size="small" @click="emojiPanelVisible = !emojiPanelVisible">选 emoji</el-button>
                <el-button size="small" :disabled="!form.image_url" @click="clearImage">清除</el-button>
              </div>
              <div class="field-tip">不设置时按分类名自动匹配食材图标，呈现到客户端移动端。</div>
              <div v-if="emojiPanelVisible" class="cat-emoji-panel">
                <button
                  v-for="g in emojiPalette"
                  :key="g"
                  type="button"
                  class="cat-emoji-cell"
                  :class="{ 'is-active': form.image_url === `emoji:${g}` }"
                  @click="pickEmoji(g)"
                >{{ g }}</button>
              </div>
            </div>
            <input ref="catImgInput" type="file" accept="image/*" hidden @change="onUploadImage" />
          </div>
        </el-form-item>
        <el-form-item label="层级">
          <el-select v-model="form.level" style="width: 100%" @change="onLevelChange">
            <el-option :value="1" label="一级分类" />
            <el-option :value="2" label="二级分类" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.level === 2" label="所属分类">
          <el-select v-model="form.parent_id" placeholder="请选择所属一级分类" style="width: 100%">
            <el-option v-for="item in level1Options" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.level === 1" label="最高上浮率上限">
          <el-input-number v-model="form.max_float_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 100%" />
          <div class="field-tip">配送商投标时，每个一级分类的上浮率不得超过该值（与投标页小数形式一致，如 0.05 表示 5%）。</div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" style="width: 100%" />
          <div class="field-tip">数值越小越靠前。</div>
        </el-form-item>
        <div class="cat-form-actions">
          <el-button @click="drawerVisible = false">取消</el-button>
          <el-button type="primary" @click="submit">{{ isEditing ? '保存修改' : '确认新增' }}</el-button>
        </div>
      </el-form>
    </el-drawer>
  </div>
</template>

<style scoped>
.cat-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* —— 页头 —— */
.cat-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 2px 2px 0;
}
.cat-title h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: var(--el-text-color-primary);
}
.cat-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.cat-summary {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 16px;
  border-radius: 12px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.sum-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}
.sum-pill b {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-color-primary);
  line-height: 1;
}
.sum-pill i {
  font-style: normal;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.sum-sep {
  width: 1px;
  height: 18px;
  background: var(--el-border-color);
}

/* —— 卡片 —— */
.cat-card {
  border-radius: 14px;
  border: 1px solid var(--el-border-color-lighter);
}
.cat-toolbar-card :deep(.el-card__body) {
  padding: 14px 16px;
}
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.crud-form {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 0;
}
.crud-form :deep(.el-form-item) {
  margin-bottom: 0;
  margin-right: 12px;
}
.crud-actions {
  display: flex;
  align-items: center;
}

/* —— 树形表格 —— */
.cat-table :deep(.el-table__row) {
  transition: background-color 0.18s ease;
}
.cat-table :deep(.cat-row-l1) {
  background: var(--el-fill-color-lighter);
}
.cat-table :deep(.cat-row-l1 .el-table__cell) {
  --el-table-tr-bg-color: transparent;
}
.cat-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}
.cat-ic {
  font-size: 16px;
}
.is-l1 .cat-ic {
  color: var(--el-color-primary);
}
.is-l2 .cat-ic {
  color: var(--el-text-color-placeholder);
}
/* 分类缩略图 */
.cat-thumb {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  font-size: 17px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}
.cat-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.is-l2 .cat-thumb {
  width: 26px;
  height: 26px;
  font-size: 15px;
}
/* 抽屉图片字段 */
.cat-img-field {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
}
.cat-img-preview {
  flex: none;
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  font-size: 30px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
}
.cat-img-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cat-img-ops {
  flex: 1;
  min-width: 0;
}
.cat-img-btns {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.cat-emoji-panel {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-fill-color-lighter);
}
.cat-emoji-cell {
  border: none;
  background: transparent;
  border-radius: 8px;
  padding: 4px 0;
  font-size: 19px;
  cursor: pointer;
  transition: background 0.15s;
}
.cat-emoji-cell:hover { background: var(--el-fill-color); }
.cat-emoji-cell.is-active {
  background: var(--el-color-primary-light-8);
  outline: 1.5px solid var(--el-color-primary);
}
.cat-name-text {
  color: var(--el-text-color-primary);
}
.is-l1 .cat-name-text {
  font-weight: 600;
}
.is-l2 .cat-name-text {
  color: var(--el-text-color-regular);
}
.cat-count {
  margin-left: 4px;
  font-variant-numeric: tabular-nums;
}
.rate-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border: 1px solid var(--el-color-warning-light-7);
}
.muted {
  color: var(--el-text-color-placeholder);
  font-variant-numeric: tabular-nums;
}
.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  justify-content: flex-end;
}

/* —— 抽屉表单 —— */
.cat-form {
  padding: 4px 8px 0;
}
.field-tip {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}
.cat-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
</style>
