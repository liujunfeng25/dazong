<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  createOperationClientCanteenApi,
  deleteOperationClientCanteenApi,
  listAccountsApi,
  listOperationClientCanteensApi,
  updateOperationClientCanteenApi,
} from '../../api/operation'

const clients = ref([])
const list = ref([])
/** 食堂名称 / 采购方单位名 / 登录名 模糊搜索 */
const filterKeyword = ref('')
const drawerVisible = ref(false)
const isEditing = ref(false)
const form = reactive({
  id: null,
  school_client_id: '',
  name: '',
  address: '',
  lng: '',
  lat: '',
  status: 'active',
  sort_order: 0,
})

const clientLabelMap = computed(() =>
  Object.fromEntries(
    clients.value.map((u) => [
      u.id,
      `${u.company_name || u.username || '未命名采购方'}${u.username ? `（${u.username}）` : ''}`,
    ]),
  ),
)

const resetForm = () => {
  Object.assign(form, {
    id: null,
    school_client_id: '',
    name: '',
    address: '',
    lng: '',
    lat: '',
    status: 'active',
    sort_order: 0,
  })
}

const loadClients = async () => {
  clients.value = await listAccountsApi({ role: 'client' })
}

const load = async () => {
  const params = {}
  const k = (filterKeyword.value || '').trim()
  if (k) params.keyword = k
  list.value = await listOperationClientCanteensApi(params)
}

const statusTag = (status) => {
  if (status === 'active') return { type: 'success', text: '启用' }
  if (status === 'disabled') return { type: 'info', text: '停用' }
  return { type: 'warning', text: String(status || '—') }
}

const clientLabel = (row) => {
  if (row.client_name || row.client_username) {
    return `${row.client_name || row.client_username}${row.client_username ? `（${row.client_username}）` : ''}`
  }
  return clientLabelMap.value[row.school_client_id] || '未绑定采购方'
}

const buildPayload = () => {
  const lng = form.lng === '' || form.lng == null ? null : Number(form.lng)
  const lat = form.lat === '' || form.lat == null ? null : Number(form.lat)
  return {
    school_client_id: Number(form.school_client_id),
    name: (form.name || '').trim(),
    address: (form.address || '').trim(),
    lng: Number.isFinite(lng) ? lng : null,
    lat: Number.isFinite(lat) ? lat : null,
    status: form.status,
    sort_order: Number(form.sort_order) || 0,
  }
}

const submit = async () => {
  const payload = buildPayload()
  if (!payload.school_client_id) return
  if (!payload.name) return
  if (form.id) await updateOperationClientCanteenApi(form.id, payload)
  else await createOperationClientCanteenApi(payload)
  resetForm()
  drawerVisible.value = false
  await load()
}

const openCreate = () => {
  isEditing.value = false
  resetForm()
  drawerVisible.value = true
}

const edit = (row) => {
  isEditing.value = true
  Object.assign(form, {
    id: row.id,
    school_client_id: row.school_client_id,
    name: row.name,
    address: row.address || '',
    lng: row.lng != null ? String(row.lng) : '',
    lat: row.lat != null ? String(row.lat) : '',
    status: row.status,
    sort_order: row.sort_order ?? 0,
  })
  drawerVisible.value = true
}

const remove = async (row) => {
  await ElMessageBox.confirm(`删除食堂「${row.name}」？若已有订单将无法删除。`, '删除确认', {
    type: 'warning',
  })
  await deleteOperationClientCanteenApi(row.id)
  await load()
}

onMounted(async () => {
  await loadClients()
  await load()
})
</script>

<template>
  <el-alert
    class="mb-3"
    type="info"
    show-icon
    :closable="false"
    title="各采购方下属的食堂仅在本页由运营维护：绑定到采购方登录账号后，该单位登录客户端时须在选食堂中转页选用后方可进入业务功能。"
  />
  <el-card class="mb-3">
    <div class="cc-toolbar">
      <div class="cc-filters">
        <div class="cc-field cc-field-grow">
          <span class="cc-field-label">名称模糊搜索</span>
          <el-input
            v-model="filterKeyword"
            clearable
            placeholder="匹配食堂名称、采购方单位名或登录名"
            @clear="load"
            @keyup.enter="load"
          />
        </div>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
      <div class="cc-toolbar-actions">
        <el-button type="primary" @click="openCreate">新建食堂</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <el-table :data="list" border>
      <el-table-column label="采购方" min-width="160">
        <template #default="{ row }">{{ clientLabel(row) }}</template>
      </el-table-column>
      <el-table-column prop="name" label="食堂名称" min-width="140" />
      <el-table-column prop="address" label="地址" min-width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="108" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status).type" effect="light" round class="status-tag">
            {{ statusTag(row.status).text }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" align="center">
        <template #default="{ row }">
          <div class="op-btns">
            <el-button size="small" @click="edit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="remove(row)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
  </el-card>

  <el-drawer v-model="drawerVisible" :title="isEditing ? '编辑食堂' : '新建食堂'" size="480px">
    <el-form label-width="108px">
      <el-form-item label="采购方账号">
        <el-select v-model="form.school_client_id" filterable placeholder="请选择采购方登录账号" style="width: 100%">
          <el-option
            v-for="u in clients"
            :key="u.id"
            :label="`${u.company_name || u.username || '未命名采购方'}${u.username ? `（${u.username}）` : ''}`"
            :value="u.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="食堂名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="地址"><el-input v-model="form.address" type="textarea" :rows="2" /></el-form-item>
      <el-form-item label="经度"><el-input v-model="form.lng" placeholder="可选" /></el-form-item>
      <el-form-item label="纬度"><el-input v-model="form.lat" placeholder="可选" /></el-form-item>
      <el-form-item label="状态">
        <el-select v-model="form.status">
          <el-option value="active" label="启用" />
          <el-option value="disabled" label="停用" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="submit">{{ isEditing ? '保存' : '创建' }}</el-button>
      </el-form-item>
    </el-form>
  </el-drawer>
</template>

<style scoped>
.cc-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
}
.cc-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 12px;
  flex: 1;
  min-width: 0;
}
.cc-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.cc-field-grow {
  flex: 1;
  min-width: 200px;
  max-width: 420px;
}
.cc-field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.status-tag {
  font-weight: 600;
}
</style>
