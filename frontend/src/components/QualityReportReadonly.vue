<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  /** 分单上的 quality_report 对象，缺省时展示「缺质检」 */
  qualityReport: { type: Object, default: null },
  periodicQualityReport: { type: Object, default: null },
  qualityReportMode: { type: String, default: 'batch' },
  qualityCoveredBy: { type: String, default: '' },
  /** 已出库仍缺质检时由后端打的异常标记 */
  missingQualityShipped: { type: Boolean, default: false },
})

function fileUrls(rep) {
  if (!rep) return []
  if (Array.isArray(rep.file_urls) && rep.file_urls.length) return rep.file_urls
  if (rep.file_url) return [rep.file_url]
  return []
}

function isPdfUrl(url) {
  const u = (url || '').split('?')[0].toLowerCase()
  return u.endsWith('.pdf')
}

const activeReport = computed(() =>
  props.qualityCoveredBy === 'periodic' ? props.periodicQualityReport : props.qualityReport,
)
const urls = computed(() => fileUrls(activeReport.value))

const galleryVisible = ref(false)
const galleryUrls = ref([])
const galleryIndex = ref(0)

const openGallery = (startIndex = 0) => {
  const list = urls.value
  if (!list.length) return
  galleryUrls.value = [...list]
  galleryIndex.value = Math.min(Math.max(0, startIndex), list.length - 1)
  galleryVisible.value = true
}

const openFirstInNewTab = () => {
  const u = urls.value[0]
  if (!u) return
  window.open(u, '_blank', 'noopener,noreferrer')
}
</script>

<template>
  <div class="qr-ro">
    <template v-if="activeReport">
      <div class="qr-ro-head">
        <el-tag :type="activeReport.status === '已通过' ? 'success' : 'info'" size="small">
          {{ qualityCoveredBy === 'periodic' ? '周期报告' : activeReport.status }}
        </el-tag>
        <span class="qr-ro-no">{{ activeReport.report_no }}</span>
      </div>
      <div v-if="qualityCoveredBy === 'periodic'" class="qr-ro-period">
        {{ activeReport.valid_from }} 至 {{ activeReport.valid_to }}
      </div>
      <template v-if="urls.length">
        <div class="qr-ro-strip" title="横向滑动可查看全部附件">
          <div
            v-for="(u, i) in urls"
            :key="i"
            class="qr-ro-hit"
            @click="openGallery(i)"
          >
            <img v-if="!isPdfUrl(u)" :src="u" class="qr-ro-thumb" alt="" />
            <span v-else class="qr-ro-thumb pdf">PDF</span>
          </div>
        </div>
        <div class="qr-ro-meta">
          <span class="qr-ro-count">共 {{ urls.length }} 张</span>
          <span class="qr-ro-actions">
            <el-button type="primary" link size="small" @click="openFirstInNewTab">打开</el-button>
            <el-button type="primary" link size="small" @click="openGallery(0)">预览</el-button>
          </span>
        </div>
      </template>
      <span v-else class="qr-ro-empty">暂无附件</span>
    </template>
    <template v-else>
      <el-tag type="danger" size="small">
        {{ qualityReportMode === 'periodic' ? '缺周期质检' : '缺质检' }}
      </el-tag>
      <el-tag
        v-if="missingQualityShipped"
        type="danger"
        effect="plain"
        size="small"
        class="qr-ro-exc"
      >异常</el-tag>
    </template>

    <el-dialog
      v-model="galleryVisible"
      title="质检附件预览（只读）"
      width="720px"
      append-to-body
      align-center
      destroy-on-close
      @closed="galleryUrls = []"
    >
      <div v-if="galleryUrls.length" class="gal-toolbar">
        <el-button size="small" :disabled="galleryIndex <= 0" @click="galleryIndex--">上一张</el-button>
        <span class="gal-counter">{{ galleryIndex + 1 }} / {{ galleryUrls.length }}</span>
        <el-button
          size="small"
          :disabled="galleryIndex >= galleryUrls.length - 1"
          @click="galleryIndex++"
        >下一张</el-button>
      </div>
      <div v-if="galleryUrls.length" class="gal-body">
        <iframe
          v-if="isPdfUrl(galleryUrls[galleryIndex])"
          :src="galleryUrls[galleryIndex]"
          class="gal-frame"
          title="pdf"
        />
        <img v-else :src="galleryUrls[galleryIndex]" class="gal-img-native" alt="" />
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.qr-ro {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
}

.qr-ro-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.qr-ro-no {
  font-size: 12px;
  color: #475569;
}

.qr-ro-period {
  font-size: 12px;
  color: #64748b;
}

.qr-ro-empty {
  font-size: 12px;
  color: #94a3b8;
}

.qr-ro-strip {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 2px;
  line-height: 0;
}

.qr-ro-hit {
  flex: 0 0 auto;
  cursor: pointer;
}

.qr-ro-thumb {
  width: 44px;
  height: 44px;
  max-width: 44px;
  max-height: 44px;
  object-fit: cover;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  display: block;
  vertical-align: top;
}

.qr-ro-thumb.pdf {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #f1f5f9;
  font-size: 10px;
  color: #64748b;
  box-sizing: border-box;
}

.qr-ro-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 12px;
}

.qr-ro-count {
  color: #64748b;
}

.qr-ro-actions {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}

.qr-ro-actions :deep(.el-button) {
  padding: 0 2px;
  height: auto;
  min-height: 22px;
}

.qr-ro-exc {
  margin-left: 6px;
}

.gal-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin-bottom: 12px;
}

.gal-counter {
  font-size: 13px;
  color: #475569;
  min-width: 4em;
}

.gal-body {
  min-height: 360px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f172a08;
  border-radius: 8px;
}

.gal-frame {
  width: 100%;
  height: 520px;
  border: none;
}

.gal-img-native {
  max-width: 100%;
  max-height: min(520px, 72vh);
  width: auto;
  height: auto;
  object-fit: contain;
  image-orientation: from-image;
}
</style>
