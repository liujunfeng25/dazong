<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listClientCanteensApi } from '../../api/clientPortal'
import { useUserStore } from '../../stores/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const list = ref([])
const loading = ref(false)
const submittingId = ref(null)

const load = async () => {
  loading.value = true
  try {
    list.value = await listClientCanteensApi()
  } finally {
    loading.value = false
  }
}

const choose = async (row) => {
  if (!row?.id) return
  submittingId.value = row.id
  try {
    await userStore.applyCanteenSession(row.id)
    ElMessage.success(`已进入「${row.name}」`)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/client/contracts'
    router.replace(redirect || '/client/contracts')
  } finally {
    submittingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page-wrap">
    <el-card class="hero">
      <h2 class="title">选择履约食堂</h2>
      <p class="hint">
        食堂档案由<strong>运营端</strong>在「客户食堂」中维护并挂到采购方账号下。须先选定履约食堂后方可进入业务功能；下单、订单与账单按所选食堂隔离。已进入系统后，可通过右上角头像菜单中的「切换食堂」回到本页重新选择。
      </p>
      <el-skeleton v-if="loading" animated :rows="4" />
      <div v-else-if="!list.length" class="empty">
        暂无可用食堂。请通知<strong>运营方</strong>在运营端「客户食堂」里为本校采购账号添加并启用食堂。
      </div>
      <div v-else class="grid">
        <el-card
          v-for="row in list"
          :key="row.id"
          shadow="hover"
          class="canteen-card"
          :class="{ disabled: row.status !== 'active' }"
        >
          <div class="name">{{ row.name }}</div>
          <div class="addr">{{ row.address || '—' }}</div>
          <el-button
            type="primary"
            class="mt-3"
            :disabled="row.status !== 'active'"
            :loading="submittingId === row.id"
            @click="choose(row)"
          >
            进入该食堂
          </el-button>
        </el-card>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.page-wrap {
  padding: 24px 24px 40px;
  min-height: 100%;
}
.hero {
  max-width: 960px;
  margin: 0 auto;
  background: rgba(30, 41, 59, 0.55);
  border: 1px solid rgba(148, 163, 184, 0.2);
}
:deep(.hero.el-card) {
  --el-card-bg-color: transparent;
}
.title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: #f8fafc;
}
.hint {
  margin: 0 0 20px;
  color: #cbd5e1;
  line-height: 1.6;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.canteen-card {
  border-radius: 12px;
}
.canteen-card.disabled {
  opacity: 0.55;
}
.canteen-card .name {
  font-weight: 600;
  font-size: 16px;
  color: #0f172a;
}
.canteen-card .addr {
  margin-top: 8px;
  font-size: 13px;
  color: #64748b;
}
.empty {
  padding: 24px 0;
  color: #94a3b8;
}
</style>
