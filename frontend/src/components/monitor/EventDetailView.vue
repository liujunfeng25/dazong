<script setup>
import { formatChinaDateTime } from '../../utils/datetime'

defineProps({
  // { title, badge, badgeTone: 'default'|'info'|'warn'|'danger', status }
  header: { type: Object, default: () => ({}) },
  // [{ label, value, sub? }]
  subjects: { type: Array, default: () => [] },
  // [{ label, value }] —— 调用方预格式化 value
  metrics: { type: Array, default: () => [] },
  // [{ label, value }] —— 整宽说明引用块
  texts: { type: Array, default: () => [] },
  // [url] —— 图片画廊
  images: { type: Array, default: () => [] },
  // [{ title, meta, note, at }] —— 流转/证据时间线
  timeline: { type: Array, default: () => [] },
  imagesTitle: { type: String, default: '图片凭证' },
  timelineTitle: { type: String, default: '处理流转' },
})

const toneClass = (tone) => `badge-${tone || 'default'}`
</script>

<template>
  <div class="event-detail">
    <header class="ed-hero">
      <div class="ed-hero-main">
        <span v-if="header.badge" class="ed-badge" :class="toneClass(header.badgeTone)">{{ header.badge }}</span>
        <strong>{{ header.title }}</strong>
      </div>
      <span v-if="header.status" class="ed-status">{{ header.status }}</span>
      <slot name="header-action" />
    </header>

    <div v-if="subjects.length" class="subject-grid">
      <article v-for="c in subjects" :key="c.label" class="subject-card">
        <span>{{ c.label }}</span>
        <strong>{{ c.value }}</strong>
        <small v-if="c.sub">{{ c.sub }}</small>
      </article>
    </div>

    <div v-if="metrics.length" class="metric-grid">
      <article v-for="m in metrics" :key="m.label" class="metric-tile">
        <span>{{ m.label }}</span><strong>{{ m.value }}</strong>
      </article>
    </div>

    <slot name="after-metrics" />

    <div v-for="b in texts" :key="b.label" class="ed-quote">
      <span>{{ b.label }}</span>
      <p>{{ b.value }}</p>
    </div>

    <div v-if="images.length" class="ed-section">
      <h4>{{ imagesTitle }}（{{ images.length }}）</h4>
      <div class="gallery">
        <el-image
          v-for="(img, i) in images"
          :key="i"
          :src="img"
          :preview-src-list="images"
          :initial-index="i"
          fit="cover"
          preview-teleported
          class="gallery-img"
        >
          <template #error><div class="img-fallback">图片加载失败</div></template>
        </el-image>
      </div>
    </div>

    <div v-if="timeline.length" class="ed-section">
      <h4>{{ timelineTitle }}</h4>
      <ol class="flow-timeline">
        <li v-for="(f, i) in timeline" :key="i" :class="{ last: i === timeline.length - 1 }">
          <i class="dot" />
          <div class="flow-body">
            <div class="flow-head">
              <strong>{{ f.title }}</strong>
              <time v-if="f.at">{{ formatChinaDateTime(f.at) }}</time>
            </div>
            <span v-if="f.meta" class="flow-meta">{{ f.meta }}</span>
            <p v-if="f.note" class="flow-note">{{ f.note }}</p>
          </div>
        </li>
      </ol>
    </div>

    <slot />
  </div>
</template>

<style scoped>
.event-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ed-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px 18px;
  border: 1px solid rgba(0, 229, 255, 0.18);
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(0, 229, 255, 0.1), rgba(5, 14, 26, 0.6));
}

.ed-hero-main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.ed-hero-main strong {
  color: #eaf8ff;
  font-size: 22px;
  font-weight: 800;
  overflow-wrap: anywhere;
}

.ed-badge {
  flex-shrink: 0;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 800;
  border: 1px solid currentColor;
}

.badge-default { color: #7fffee; background: rgba(0, 229, 255, 0.12); }
.badge-info { color: #8fb8ff; background: rgba(88, 130, 255, 0.16); }
.badge-warn { color: #ffcf7a; background: rgba(255, 170, 80, 0.16); }
.badge-danger { color: #ff8f9c; background: rgba(255, 90, 110, 0.16); }

.ed-status {
  flex-shrink: 0;
  padding: 5px 14px;
  border-radius: 999px;
  font-weight: 800;
  color: #03161b;
  background: linear-gradient(135deg, #7fffee, #00d5ff);
}

.subject-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}

.subject-card {
  padding: 14px 16px;
  border: 1px solid rgba(0, 229, 255, 0.16);
  border-radius: 10px;
  background: rgba(4, 12, 23, 0.56);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.subject-card span {
  color: rgba(130, 255, 231, 0.72);
  font-size: 12px;
  font-weight: 700;
}

.subject-card strong {
  color: #eaf8ff;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.subject-card small {
  color: rgba(221, 232, 241, 0.6);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
}

.metric-tile {
  padding: 12px 14px;
  border: 1px solid rgba(0, 229, 255, 0.12);
  border-radius: 8px;
  background: rgba(2, 10, 20, 0.5);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.metric-tile span {
  color: rgba(215, 235, 242, 0.55);
  font-size: 12px;
}

.metric-tile strong {
  color: #d8f3ff;
  font-size: 16px;
  overflow-wrap: anywhere;
}

.ed-quote {
  padding: 14px 16px;
  border-left: 3px solid rgba(0, 229, 255, 0.6);
  border-radius: 0 8px 8px 0;
  background: rgba(255, 255, 255, 0.035);
}

.ed-quote span {
  display: block;
  margin-bottom: 6px;
  color: rgba(130, 255, 231, 0.72);
  font-size: 12px;
  font-weight: 700;
}

.ed-quote p {
  margin: 0;
  color: #eaf8ff;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.ed-section h4 {
  margin: 0 0 10px;
  color: #bffcff;
  font-size: 15px;
}

.gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.gallery-img {
  width: 104px;
  height: 104px;
  border-radius: 8px;
  border: 1px solid rgba(0, 229, 255, 0.2);
  overflow: hidden;
  cursor: zoom-in;
}

.img-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 104px;
  height: 104px;
  color: rgba(221, 232, 241, 0.5);
  font-size: 12px;
  background: rgba(2, 10, 20, 0.6);
}

.flow-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
}

.flow-timeline li {
  position: relative;
  padding: 0 0 18px 22px;
}

.flow-timeline li::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 14px;
  bottom: -4px;
  width: 2px;
  background: rgba(0, 229, 255, 0.22);
}

.flow-timeline li.last::before {
  display: none;
}

.flow-timeline .dot {
  position: absolute;
  left: 0;
  top: 4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #00d5ff;
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.5);
}

.flow-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.flow-head strong {
  color: #eaf8ff;
  font-size: 14px;
}

.flow-head time {
  color: rgba(221, 232, 241, 0.5);
  font-size: 12px;
  white-space: nowrap;
}

.flow-meta {
  color: rgba(130, 255, 231, 0.66);
  font-size: 12px;
}

.flow-note {
  margin: 6px 0 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.04);
  color: #d8f3ff;
  overflow-wrap: anywhere;
}
</style>
