<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { createCategoryApi, deleteCategoryApi, listCategoriesApi, updateCategoryApi } from '../../api/operation'

const list = ref([])
const drawerVisible = ref(false)
const isEditing = ref(false)
const form = reactive({ id: null, name: '', level: 1, parent_id: null, sort_order: 0, max_float_rate: 1 })

const level1Options = computed(() => list.value.filter((item) => item.level === 1))
const categoryNameMap = computed(() => Object.fromEntries(list.value.map((item) => [item.id, item.name])))

const resetForm = () => {
  Object.assign(form, { id: null, name: '', level: 1, parent_id: null, sort_order: 0, max_float_rate: 1 })
}

const load = async () => {
  list.value = await listCategoriesApi()
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
const edit = (row) => {
  isEditing.value = true
  Object.assign(form, {
    ...row,
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
  <el-card class="mb-3">
    <div class="crud-toolbar">
      <div />
      <div class="crud-actions">
        <el-button type="primary" @click="openCreate">新增分类</el-button>
      </div>
    </div>
  </el-card>
  <el-card>
    <el-table :data="list" border>
      <el-table-column prop="id" label="编号" width="80" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="最高上浮率上限" width="130" align="right">
        <template #default="{ row }">
          {{ row.level === 1 ? Number(row.max_float_rate ?? 1).toFixed(4) : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="层级" width="100">
        <template #default="{ row }">{{ row.level === 1 ? '一级分类' : '二级分类' }}</template>
      </el-table-column>
      <el-table-column label="所属分类" width="140">
        <template #default="{ row }">{{ categoryNameMap[row.parent_id] || '—' }}</template>
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
  </el-card>

  <el-drawer v-model="drawerVisible" :title="isEditing ? '编辑分类' : '新增分类'" size="480px">
    <el-form label-width="100px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="层级">
        <el-select v-model="form.level" @change="onLevelChange">
          <el-option :value="1" label="一级分类" />
          <el-option :value="2" label="二级分类" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.level === 2" label="所属分类">
        <el-select v-model="form.parent_id" placeholder="请选择所属一级分类">
          <el-option v-for="item in level1Options" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.level === 1" label="最高上浮率上限">
        <el-input-number v-model="form.max_float_rate" :min="0" :max="1" :step="0.01" :precision="4" style="width: 100%" />
        <div class="field-tip">配送商投标时，每个一级分类的上浮率不得超过该值（与投标页小数形式一致，如 0.05 表示 5%）。</div>
      </el-form-item>
      <el-form-item label="排序"><el-input-number v-model="form.sort_order" :min="0" /></el-form-item>
      <el-button type="primary" @click="submit">{{ isEditing ? '保存修改' : '确认新增' }}</el-button>
    </el-form>
  </el-drawer>
</template>

<style scoped>
.crud-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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
  line-height: 1.5;
}
</style>
