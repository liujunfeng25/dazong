<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createProductApi,
  deleteProductApi,
  listAccountsApi,
  listCategoriesApi,
  listProductsApi,
  uploadProductImageApi,
  updateProductApi,
} from '../../api/operation'

const list = ref([])
const categories = ref([])
const factoryOptions = ref([])
const keyword = ref('')
const category1Filter = ref(null)
const category2Filter = ref(null)
const hasFactoryFilter = ref(null)
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const tableKey = ref(0)
const drawerVisible = ref(false)
const isEditing = ref(false)
const imagePreviewVisible = ref(false)
const imagePreviewList = ref([])
const form = reactive({
  id: null,
  name: '',
  category1_id: null,
  category2_id: null,
  unit: 'kg',
  reference_price: 1,
  spec: '',
  origin: '',
  standard_type: 'standard',
  length_cm: null,
  width_cm: null,
  height_cm: null,
  unit_weight_kg: null,
  volume_adjust_factor: null,
  is_designated_factory: false,
  designated_factory_id: null,
  status: 'active',
  logo: '',
  image_list_json: [],
})

const productStatusLabel = (value) => ({ active: '启用', disabled: '停用' }[value] || value)
const productStandardTypeLabel = (value) =>
  ({ standard: '标品', non_standard: '非标品' }[value] || value)
const categoryNameMap = computed(() =>
  Object.fromEntries(categories.value.map((item) => [item.id, item.name])),
)
const factoryNameMap = computed(() =>
  Object.fromEntries(
    factoryOptions.value.map((item) => [item.id, item.company_name || item.username || `厂家#${item.id}`]),
  ),
)
const level1Options = computed(() => categories.value.filter((item) => item.level === 1))
const level2Options = computed(() =>
  categories.value.filter(
    (item) => item.level === 2 && item.parent_id === Number(form.category1_id || 0),
  ),
)
const level2FilterOptions = computed(() =>
  categories.value.filter(
    (item) => item.level === 2 && item.parent_id === Number(category1Filter.value || 0),
  ),
)

const resetForm = () => {
  Object.assign(form, {
    id: null,
    name: '',
    category1_id: null,
    category2_id: null,
    unit: 'kg',
    reference_price: 1,
    spec: '',
    origin: '',
    standard_type: 'standard',
    length_cm: null,
    width_cm: null,
    height_cm: null,
    unit_weight_kg: null,
    volume_adjust_factor: null,
    is_designated_factory: false,
    designated_factory_id: null,
    status: 'active',
    logo: '',
    image_list_json: [],
  })
}

const load = async () => {
  loading.value = true
  try {
    const res = await listProductsApi({
      keyword: keyword.value,
      category1_id: category1Filter.value,
      category2_id: category2Filter.value,
      has_factory: hasFactoryFilter.value,
      page: page.value,
      page_size: pageSize.value,
    })
    list.value = res.items || []
    total.value = Number(res.total || 0)
  } finally {
    loading.value = false
  }
}

const loadCategories = async () => {
  categories.value = await listCategoriesApi()
}
const loadFactories = async () => {
  factoryOptions.value = await listAccountsApi({ role: 'factory' })
}

const onCategory1Change = () => {
  form.category2_id = null
}
const onFilterCategory1Change = () => {
  category2Filter.value = null
  page.value = 1
}
const onDesignatedFactoryChange = (value) => {
  if (!value) form.designated_factory_id = null
}

const submit = async () => {
  if (!form.category1_id || !form.category2_id) {
    ElMessage.warning('请先选择所属分类')
    return
  }
  if (form.is_designated_factory && !form.designated_factory_id) {
    ElMessage.warning('请选择指定厂家')
    return
  }
  const payload = {
    name: form.name,
    category1_id: form.category1_id,
    category2_id: form.category2_id,
    unit: form.unit,
    reference_price: form.reference_price,
    spec: form.spec,
    origin: form.origin,
    standard_type: form.standard_type,
    length_cm: form.length_cm,
    width_cm: form.width_cm,
    height_cm: form.height_cm,
    unit_weight_kg: form.unit_weight_kg,
    volume_adjust_factor: form.volume_adjust_factor,
    is_designated_factory: form.is_designated_factory,
    designated_factory_id: form.designated_factory_id,
    status: form.status,
    logo: form.logo || null,
    image_list_json: (form.image_list_json || []).filter(Boolean),
    detail_images_json: [],
  }
  const saved = form.id ? await updateProductApi(form.id, payload) : await createProductApi(payload)
  ElMessage.success(isEditing.value ? '保存成功' : '新增成功')
  const idx = list.value.findIndex((item) => item.id === saved.id)
  if (idx >= 0) list.value[idx] = saved
  else list.value.unshift(saved)
  tableKey.value += 1
  resetForm()
  drawerVisible.value = false
  // 再拉一次后端数据，保证与服务端最终一致
  await load()
  tableKey.value += 1
  await Promise.allSettled([loadCategories(), loadFactories()])
}
const openCreate = () => {
  isEditing.value = false
  resetForm()
  drawerVisible.value = true
}
const edit = (row) => {
  isEditing.value = true
  Object.assign(form, {
    ...row,
    logo: row.logo || '',
    image_list_json: Array.isArray(row.image_list_json) ? [...row.image_list_json] : [],
  })
  drawerVisible.value = true
}
const remove = async (id) => {
  await ElMessageBox.confirm('确认删除该商品吗？', '删除确认', { type: 'warning' })
  await deleteProductApi(id)
  await load()
}
const onSearch = async () => {
  page.value = 1
  await load()
}
const onPageChange = async (value) => {
  page.value = value
  await load()
}
const onPageSizeChange = async (value) => {
  pageSize.value = value
  page.value = 1
  await load()
}
const previewImages = (row) => {
  const mains = Array.isArray(row.image_list_json) ? row.image_list_json : []
  imagePreviewList.value = Array.from(new Set([...mains, row.logo].filter(Boolean)))
  imagePreviewVisible.value = imagePreviewList.value.length > 0
}
const addImageUrl = (field) => {
  form[field].push('')
}
const removeImageUrl = (field, idx) => {
  form[field].splice(idx, 1)
}
const uploadProductImage = async (rawFile) => {
  if (!rawFile) return null
  const fd = new FormData()
  fd.append('file', rawFile)
  const res = await uploadProductImageApi(fd)
  return res?.url || null
}
const onUploadMainLogo = async (uploadFile) => {
  const url = await uploadProductImage(uploadFile.raw)
  if (url) {
    form.logo = url
    ElMessage.success('主图上传成功')
  }
}
const onUploadGalleryImage = async (uploadFile) => {
  const url = await uploadProductImage(uploadFile.raw)
  if (url) {
    form.image_list_json.push(url)
    ElMessage.success('商品照片上传成功')
  }
}
onMounted(async () => {
  await Promise.all([load(), loadCategories(), loadFactories()])
})
</script>

<template>
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <el-form inline class="crud-form">
        <el-form-item><el-input v-model="keyword" placeholder="搜索商品" clearable /></el-form-item>
        <el-form-item>
          <el-select
            v-model="category1Filter"
            clearable
            placeholder="一级分类"
            style="width: 140px"
            @change="onFilterCategory1Change"
          >
            <el-option v-for="item in level1Options" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="category2Filter" clearable placeholder="二级分类" style="width: 160px">
            <el-option
              v-for="item in level2FilterOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-select v-model="hasFactoryFilter" clearable placeholder="所属厂家" style="width: 170px">
            <el-option :value="1" label="有所属厂家" />
            <el-option :value="0" label="无所属厂家" />
          </el-select>
        </el-form-item>
        <el-form-item><el-button @click="onSearch">搜索</el-button></el-form-item>
      </el-form>
      <div class="crud-actions">
        <el-button type="primary" @click="openCreate">新增商品</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <el-table :key="tableKey" v-loading="loading" :data="list" border>
      <el-table-column prop="id" label="编号" width="70" />
      <el-table-column prop="name" label="商品" />
      <el-table-column label="分类">
        <template #default="{ row }">
          {{ categoryNameMap[row.category1_id] || '—' }} / {{ categoryNameMap[row.category2_id] || '—' }}
        </template>
      </el-table-column>
      <el-table-column prop="reference_price" label="参考价">
        <template #default="{ row }">¥{{ Number(row.reference_price || 0).toLocaleString() }}</template>
      </el-table-column>
      <el-table-column label="图片" width="140" align="center">
        <template #default="{ row }">
          <img
            v-if="(row.logo || (row.image_list_json || [])[0])"
            :src="row.logo || (row.image_list_json || [])[0]"
            class="table-thumb"
            @click="previewImages(row)"
          />
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column prop="standard_type" label="品类类型" width="120">
        <template #default="{ row }">
          <el-tag :type="row.standard_type === 'standard' ? 'success' : 'warning'">
            {{ productStandardTypeLabel(row.standard_type) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="所属厂家" width="180">
        <template #default="{ row }">
          {{ !row.is_designated_factory ? '—' : (factoryNameMap[row.designated_factory_id] || '未设置') }}
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ productStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="edit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row.id)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager-wrap">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[20, 50, 100]"
        @current-change="onPageChange"
        @size-change="onPageSizeChange"
      />
    </div>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="isEditing ? '编辑商品' : '新增商品'" size="520px">
    <el-form label-width="100px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="所属一级分类">
        <el-select v-model="form.category1_id" placeholder="请选择一级分类" @change="onCategory1Change">
          <el-option v-for="item in level1Options" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="所属二级分类">
        <el-select v-model="form.category2_id" placeholder="请选择二级分类">
          <el-option v-for="item in level2Options" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="单位"><el-input v-model="form.unit" /></el-form-item>
      <el-form-item label="参考价"><el-input-number v-model="form.reference_price" :min="0" /></el-form-item>
      <el-form-item label="规格"><el-input v-model="form.spec" /></el-form-item>
      <el-form-item label="产地"><el-input v-model="form.origin" /></el-form-item>
      <el-form-item label="主图上传">
        <el-upload :show-file-list="false" :auto-upload="false" :on-change="onUploadMainLogo">
          <el-button>上传主图</el-button>
        </el-upload>
        <div class="field-tip" v-if="form.logo">
          已上传：<a :href="form.logo" target="_blank">查看主图</a>
        </div>
      </el-form-item>
      <el-form-item label="商品照片">
        <div class="img-url-list">
          <el-upload :show-file-list="false" :auto-upload="false" :on-change="onUploadGalleryImage">
            <el-button plain>上传商品照片</el-button>
          </el-upload>
          <div v-for="(_, idx) in form.image_list_json" :key="`main-${idx}`" class="img-url-row">
            <el-input v-model="form.image_list_json[idx]" readonly />
            <el-button type="danger" plain @click="removeImageUrl('image_list_json', idx)">删除</el-button>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="品类类型">
        <el-select v-model="form.standard_type">
          <el-option value="standard" label="标品" />
          <el-option value="non_standard" label="非标品" />
        </el-select>
        <div class="field-tip">标品尺寸较稳定；非标品尺寸可能波动。仅用于后续排线估算，不填也不影响下单。</div>
      </el-form-item>
      <el-form-item label="是否指定厂家">
        <el-select v-model="form.is_designated_factory" @change="onDesignatedFactoryChange">
          <el-option :value="false" label="非指定（默认）" />
          <el-option :value="true" label="指定厂家" />
        </el-select>
        <div class="field-tip">
          特殊品类（如牛奶）可选择“指定厂家”，配送方只能按指定厂家执行。
        </div>
      </el-form-item>
      <el-form-item v-if="form.is_designated_factory" label="指定厂家">
        <el-select v-model="form.designated_factory_id" placeholder="请选择固定厂家">
          <el-option
            v-for="item in factoryOptions"
            :key="item.id"
            :label="item.company_name || item.username"
            :value="item.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="长(cm)">
        <el-input-number v-model="form.length_cm" :min="0" :precision="2" />
        <div class="field-tip">单件商品长度。建议填写外包装尺寸，不填则不参与体积计算。</div>
      </el-form-item>
      <el-form-item label="宽(cm)">
        <el-input-number v-model="form.width_cm" :min="0" :precision="2" />
        <div class="field-tip">单件商品宽度。与长、高一起用于估算装车体积。</div>
      </el-form-item>
      <el-form-item label="高(cm)">
        <el-input-number v-model="form.height_cm" :min="0" :precision="2" />
        <div class="field-tip">单件商品高度。可填常见值，后续可逐步修正。</div>
      </el-form-item>
      <el-form-item label="单件重量(kg)">
        <el-input-number v-model="form.unit_weight_kg" :min="0" :precision="3" />
        <div class="field-tip">用于估算车辆载重占用。非必填，建议优先给高价值/大件商品填写。</div>
      </el-form-item>
      <el-form-item label="体积修正系数">
        <el-input-number v-model="form.volume_adjust_factor" :min="0" :precision="3" />
        <div class="field-tip">
          仅建议非标品填写。例如填 1.15 表示按体积上浮 15% 估算；不填默认按 1.0 计算。
        </div>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status">
          <el-option value="active" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-button type="primary" @click="submit">{{ isEditing ? '保存修改' : '确认新增' }}</el-button>
    </el-form>
  </el-drawer>

  <el-dialog v-model="imagePreviewVisible" title="商品照片" width="720px">
    <el-carousel v-if="imagePreviewList.length" height="420px" indicator-position="outside">
      <el-carousel-item v-for="(url, idx) in imagePreviewList" :key="`${url}-${idx}`">
        <img :src="url" class="preview-image" />
      </el-carousel-item>
    </el-carousel>
    <div v-else>暂无图片</div>
  </el-dialog>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.crud-form {
  margin-bottom: 0;
}

.crud-actions {
  display: flex;
  align-items: center;
}

.op-btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.field-tip {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
.pager-wrap {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}
.preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #f8fafc;
}
.table-thumb {
  width: 56px;
  height: 56px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  cursor: zoom-in;
  background: #f8fafc;
}
.img-url-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.img-url-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}
</style>
