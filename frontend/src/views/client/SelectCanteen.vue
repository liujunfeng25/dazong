<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listClientCanteensApi } from '../../api/clientPortal'
import { useUserStore } from '../../stores/user'
import { useIsMobile } from '../../composables/useIsMobile'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const { isMobile } = useIsMobile()
const searchKeyword = ref('')
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
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/client/dashboard'
    router.replace(redirect || '/client/dashboard')
  } finally {
    submittingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <!-- ── Mobile ── -->
  <div v-if="isMobile" class="m-select-page">
    <div class="m-select-header">
      <div class="m-select-header__title">选择食堂</div>
      <div class="m-select-header__sub">请选择您要进入的履约食堂</div>
    </div>

    <div class="m-select-body">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索食堂名称..."
        clearable
        prefix-icon="Search"
        class="m-search"
      />

      <el-skeleton v-if="loading" animated :rows="3" style="padding:16px" />
      <div v-else-if="!list.length" class="m-empty">
        暂无可用食堂，请联系运营方添加。
      </div>
      <div v-else class="m-canteen-list">
        <div
          v-for="row in list.filter(r => !searchKeyword || r.name?.includes(searchKeyword))"
          :key="row.id"
          class="m-canteen-card"
          :class="{ disabled: row.status !== 'active' }"
          @click="row.status === 'active' && choose(row)"
        >
          <div class="m-canteen-card__icon">
            <span class="material-symbols-outlined">restaurant</span>
          </div>
          <div class="m-canteen-card__info">
            <div class="m-canteen-card__name">{{ row.name }}</div>
            <div class="m-canteen-card__addr">{{ row.address || '—' }}</div>
            <div v-if="row.status !== 'active'" class="m-canteen-card__disabled">暂不可用</div>
          </div>
          <el-button
            v-if="row.status === 'active'"
            :loading="submittingId === row.id"
            type="primary"
            size="small"
            @click.stop="choose(row)"
          >进入</el-button>
        </div>
      </div>
    </div>
  </div>

  <!-- ── PC ── -->
  <div v-else class="page-wrap">
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

/* ── Mobile styles ── */
.m-select-page {
  min-height: 100vh;
  background: var(--m-surface);
  display: flex;
  flex-direction: column;
  font-family: var(--m-font-body);
}
.m-select-header {
  background: linear-gradient(135deg, var(--m-primary) 0%, var(--m-primary-container) 100%);
  color: var(--m-on-primary);
  padding: 40px 20px 28px;
}
.m-select-header__title {
  font-family: var(--m-font-display);
  font-size: 26px;
  font-weight: 800;
  margin-bottom: 6px;
}
.m-select-header__sub {
  font-size: 14px;
  opacity: 0.8;
}
.m-select-body {
  flex: 1;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.m-search {
  width: 100%;
}
.m-canteen-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.m-canteen-card {
  background: var(--m-surface-container-lowest);
  border: 1.5px solid var(--m-outline-variant);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: border-color 0.18s, box-shadow 0.18s;
}
.m-canteen-card:active { border-color: var(--m-primary); box-shadow: 0 2px 12px rgba(0,50,134,0.12); }
.m-canteen-card.disabled { opacity: 0.55; cursor: not-allowed; }
.m-canteen-card__icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: var(--m-secondary-fixed);
  color: var(--m-primary);
  display: grid;
  place-items: center;
  flex: none;
}
.m-canteen-card__info {
  flex: 1;
  min-width: 0;
}
.m-canteen-card__name {
  font-size: 15px;
  font-weight: 700;
  color: var(--m-on-surface);
  margin-bottom: 3px;
}
.m-canteen-card__addr {
  font-size: 12px;
  color: var(--m-on-surface-variant);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-canteen-card__disabled {
  font-size: 11px;
  color: var(--m-error);
  margin-top: 2px;
  font-weight: 600;
}
.m-empty {
  text-align: center;
  color: var(--m-on-surface-variant);
  padding: 32px 0;
  font-size: 14px;
}
</style>
