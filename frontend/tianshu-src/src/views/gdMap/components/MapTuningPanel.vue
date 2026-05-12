<template>
  <div class="map-tune">
    <div class="map-tune__head">
      <strong>地图视觉调色 / 挤出</strong>
      <span class="map-tune__hint">参数会写入 localStorage；满意后导出并替换 <code>mapVisualConfig.js</code></span>
    </div>
    <div class="map-tune__scroll">
      <section class="map-tune__sec">
        <h4>挤出高度</h4>
        <label class="map-tune__row">
          <span>extrudeDepth {{ local.extrudeDepth }}</span>
          <input v-model.number="local.extrudeDepth" type="range" min="0.35" max="1.25" step="0.01" @input="applySoon" />
        </label>
        <label class="map-tune__row">
          <span>mapTopZOffset</span>
          <input v-model.number="local.mapTopZOffset" type="number" step="0.01" class="map-tune__num" @change="applySoon" />
        </label>
        <label class="map-tune__row">
          <span>districtLineZOffset</span>
          <input v-model.number="local.districtLineZOffset" type="number" step="0.001" class="map-tune__num" @change="applySoon" />
        </label>
        <label class="map-tune__row">
          <span>districtLabelZOffset</span>
          <input v-model.number="local.districtLabelZOffset" type="number" step="0.01" class="map-tune__num" @change="applySoon" />
        </label>
      </section>

      <section class="map-tune__sec">
        <h4>雾与背景</h4>
        <div class="map-tune__row map-tune__row--color">
          <span>atmosphereColor</span>
          <input v-model="hex.atmosphereColor" type="color" @input="syncHex('atmosphereColor'); applySoon()" />
        </div>
        <label class="map-tune__row">
          <span>fogNear</span>
          <input v-model.number="local.fogNear" type="number" step="1" class="map-tune__num" @change="applySoon" />
        </label>
        <label class="map-tune__row">
          <span>fogFar</span>
          <input v-model.number="local.fogFar" type="number" step="1" class="map-tune__num" @change="applySoon" />
        </label>
      </section>

      <section class="map-tune__sec">
        <h4>环境光</h4>
        <div class="map-tune__row map-tune__row--color">
          <span>ambientColor</span>
          <input v-model="hex.ambientColor" type="color" @input="syncHex('ambientColor'); applySoon()" />
        </div>
        <label class="map-tune__row">
          <span>ambientIntensity</span>
          <input v-model.number="local.ambientIntensity" type="range" min="0" max="5" step="0.05" @input="applySoon" />
        </label>
        <div class="map-tune__row map-tune__row--color">
          <span>hemiSky</span>
          <input v-model="hex.hemiSky" type="color" @input="syncHex('hemiSky'); applySoon()" />
        </div>
        <div class="map-tune__row map-tune__row--color">
          <span>hemiGround</span>
          <input v-model="hex.hemiGround" type="color" @input="syncHex('hemiGround'); applySoon()" />
        </div>
        <label class="map-tune__row">
          <span>hemiIntensity</span>
          <input v-model.number="local.hemiIntensity" type="range" min="0" max="4" step="0.05" @input="applySoon" />
        </label>
      </section>

      <section class="map-tune__sec">
        <h4>平行光</h4>
        <div class="map-tune__row map-tune__row--color"><span>dirKey</span><input v-model="hex.dirKeyColor" type="color" @input="syncHex('dirKeyColor'); applySoon()" /></div>
        <label class="map-tune__row"><span>dirKey I</span><input v-model.number="local.dirKeyIntensity" type="range" min="0" max="4" step="0.05" @input="applySoon" /></label>
        <div class="map-tune__row map-tune__row--color"><span>dirFill</span><input v-model="hex.dirFillColor" type="color" @input="syncHex('dirFillColor'); applySoon()" /></div>
        <label class="map-tune__row"><span>dirFill I</span><input v-model.number="local.dirFillIntensity" type="range" min="0" max="4" step="0.05" @input="applySoon" /></label>
        <div class="map-tune__row map-tune__row--color"><span>dirRim</span><input v-model="hex.dirRimColor" type="color" @input="syncHex('dirRimColor'); applySoon()" /></div>
        <label class="map-tune__row"><span>dirRim I</span><input v-model.number="local.dirRimIntensity" type="range" min="0" max="4" step="0.05" @input="applySoon" /></label>
      </section>

      <section class="map-tune__sec">
        <h4>点光</h4>
        <label class="map-tune__row">
          <span>pointColor (#RRGGBB)</span>
          <input v-model="local.pointColor" type="text" class="map-tune__text" @change="applySoon" />
        </label>
        <label class="map-tune__row"><span>pointIntensity0</span><input v-model.number="local.pointIntensity0" type="range" min="0" max="500" step="5" @input="applySoon" /></label>
        <label class="map-tune__row"><span>pointIntensity1</span><input v-model.number="local.pointIntensity1" type="range" min="0" max="500" step="5" @input="applySoon" /></label>
      </section>

      <section class="map-tune__sec">
        <h4>全国底</h4>
        <label class="map-tune__row"><span>chinaBg</span><input v-model="local.chinaBg" type="text" class="map-tune__text" @change="applySoon" /></label>
        <label class="map-tune__row"><span>chinaBgOpacity</span><input v-model.number="local.chinaBgOpacity" type="range" min="0" max="1" step="0.02" @input="applySoon" /></label>
        <label class="map-tune__row"><span>chinaLine</span><input v-model="local.chinaLine" type="text" class="map-tune__text" @change="applySoon" /></label>
      </section>

      <section class="map-tune__sec">
        <h4>挤出顶 / 侧</h4>
        <div class="map-tune__row map-tune__row--color"><span>extrudeTopTint</span><input v-model="hex.extrudeTopTint" type="color" @input="syncHex('extrudeTopTint'); applySoon()" /></div>
        <label class="map-tune__row"><span>extrudeTopAlpha</span><input v-model.number="local.extrudeTopAlpha" type="range" min="0.2" max="1" step="0.01" @input="applySoon" /></label>
        <label class="map-tune__row">顶 RGB 加算 <input v-model.number="local.extrudeTopRgbBoost[0]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
          <input v-model.number="local.extrudeTopRgbBoost[1]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
          <input v-model.number="local.extrudeTopRgbBoost[2]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
        </label>
        <div class="map-tune__row map-tune__row--color"><span>extrudeSide1</span><input v-model="hex.extrudeSide1" type="color" @input="syncHex('extrudeSide1'); applySoon()" /></div>
        <div class="map-tune__row map-tune__row--color"><span>extrudeSide2</span><input v-model="hex.extrudeSide2" type="color" @input="syncHex('extrudeSide2'); applySoon()" /></div>
        <label class="map-tune__row"><span>extrudeSideZDiv</span><input v-model.number="local.extrudeSideZDiv" type="number" step="0.05" class="map-tune__num" @change="applySoon" /></label>
        <label class="map-tune__row">侧 RGB 加算
          <input v-model.number="local.extrudeSideRgbBoost[0]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
          <input v-model.number="local.extrudeSideRgbBoost[1]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
          <input v-model.number="local.extrudeSideRgbBoost[2]" type="number" step="0.02" class="map-tune__num sm" @change="applySoon" />
        </label>
      </section>

      <section class="map-tune__sec">
        <h4>顶面渐变片 (mapTop)</h4>
        <div class="map-tune__row map-tune__row--color"><span>mapTopGradient1</span><input v-model="hex.mapTopGradient1" type="color" @input="syncHex('mapTopGradient1'); applySoon()" /></div>
        <div class="map-tune__row map-tune__row--color"><span>mapTopGradient2</span><input v-model="hex.mapTopGradient2" type="color" @input="syncHex('mapTopGradient2'); applySoon()" /></div>
        <label class="map-tune__row"><span>mapTopOpacity</span><input v-model.number="local.mapTopOpacity" type="range" min="0" max="1" step="0.02" @input="applySoon" /></label>
        <label class="map-tune__row"><span>mapTopGradientSize</span><input v-model.number="local.mapTopGradientSize" type="number" step="1" class="map-tune__num" @change="applySoon" /></label>
        <div class="map-tune__row map-tune__row--color"><span>mapHoverTint</span><input v-model="hex.mapHoverTint" type="color" @input="syncHex('mapHoverTint'); applySoon()" /></div>
        <label class="map-tune__row"><span>mapHoverOpacity</span><input v-model.number="local.mapHoverOpacity" type="range" min="0" max="1" step="0.02" @input="applySoon" /></label>
      </section>

      <section class="map-tune__sec">
        <h4>区县界线</h4>
        <div class="map-tune__row map-tune__row--color"><span>districtLineColor</span><input v-model="hex.districtLineColor" type="color" @input="syncHex('districtLineColor'); applySoon()" /></div>
        <label class="map-tune__row"><span>districtLineWidth</span><input v-model.number="local.districtLineWidth" type="range" min="0.5" max="6" step="0.1" @input="applySoon" /></label>
        <label class="map-tune__row"><span>districtLineOpacity</span><input v-model.number="local.districtLineOpacity" type="range" min="0" max="1" step="0.02" @input="applySoon" /></label>
      </section>
    </div>

    <div class="map-tune__actions">
      <button type="button" class="map-tune__btn" @click="pullFromWorld">从场景拉取</button>
      <button type="button" class="map-tune__btn" @click="resetDefaults">恢复代码默认</button>
      <button type="button" class="map-tune__btn" @click="copyConfigModule">复制 mapVisualConfig.js</button>
      <button type="button" class="map-tune__btn is-ghost" @click="$emit('close')">关闭</button>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch, onMounted } from "vue"
import { MAP_VISUAL_DEFAULTS } from "../mapVisualConfig.js"
import { clearMapVisualStorage, saveMapVisualSnapshot } from "../mapVisualStorage.js"
import { formatMapVisualAsConfigModule } from "../mapVisualExport.js"

const props = defineProps({
  getWorld: { type: Function, required: true },
})

defineEmits(["close"])

const HEX_FIELDS = [
  "atmosphereColor",
  "ambientColor",
  "hemiSky",
  "hemiGround",
  "dirKeyColor",
  "dirFillColor",
  "dirRimColor",
  "extrudeTopTint",
  "extrudeSide1",
  "extrudeSide2",
  "mapTopGradient1",
  "mapTopGradient2",
  "mapHoverTint",
  "districtLineColor",
]

function numToHex(n) {
  const x = Math.max(0, Math.min(0xffffff, Number(n) || 0))
  return `#${Math.floor(x).toString(16).padStart(6, "0")}`
}

function hexToNum(h) {
  if (typeof h !== "string") return 0
  const s = h.trim().replace(/^#/, "")
  return parseInt(s.length === 3 ? s.split("").map((c) => c + c).join("") : s, 16) || 0
}

function cloneState(src) {
  return JSON.parse(JSON.stringify(src))
}

const local = reactive(cloneState(MAP_VISUAL_DEFAULTS))
const hex = reactive({})

function refreshHexFromLocal() {
  for (const k of HEX_FIELDS) {
    hex[k] = numToHex(local[k])
  }
}

function syncHex(key) {
  local[key] = hexToNum(hex[key])
}

let persistTimer = null
function applySoon() {
  const w = props.getWorld()
  if (!w?.applyMapVisualPatch) return
  const patch = { ...local }
  w.applyMapVisualPatch(patch, { persist: false })
  if (persistTimer) clearTimeout(persistTimer)
  persistTimer = setTimeout(() => {
    persistTimer = null
    saveMapVisualSnapshot(w.getMapVisualSnapshot?.() ?? { ...local })
  }, 600)
}

function pullFromWorld() {
  const w = props.getWorld()
  const snap = w?.getMapVisualSnapshot?.()
  if (!snap) return
  Object.assign(local, cloneState(snap))
  refreshHexFromLocal()
}

function resetDefaults() {
  clearMapVisualStorage()
  Object.assign(local, cloneState(MAP_VISUAL_DEFAULTS))
  refreshHexFromLocal()
  const w = props.getWorld()
  w?.applyMapVisualPatch?.(cloneState(MAP_VISUAL_DEFAULTS), { persist: false })
  saveMapVisualSnapshot(cloneState(MAP_VISUAL_DEFAULTS))
}

async function copyConfigModule() {
  const w = props.getWorld()
  const snap = w?.getMapVisualSnapshot?.() ?? { ...local }
  const text = formatMapVisualAsConfigModule(snap)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    window.prompt("复制以下内容到 mapVisualConfig.js：", text)
  }
}

onMounted(() => {
  refreshHexFromLocal()
  pullFromWorld()
})

defineExpose({ pullFromWorld })
</script>

<style scoped>
.map-tune {
  width: min(420px, 92vw);
  max-height: min(88vh, 900px);
  display: flex;
  flex-direction: column;
  background: rgba(6, 14, 26, 0.94);
  border: 1px solid rgba(56, 189, 248, 0.35);
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
  color: #cfe8f5;
  font-size: 12px;
}
.map-tune__head {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(56, 189, 248, 0.2);
}
.map-tune__head strong {
  display: block;
  font-size: 13px;
  margin-bottom: 4px;
}
.map-tune__hint {
  opacity: 0.82;
  line-height: 1.35;
}
.map-tune__hint code {
  font-size: 11px;
  color: #7dd3fc;
}
.map-tune__scroll {
  overflow: auto;
  padding: 8px 10px;
  flex: 1;
}
.map-tune__sec {
  margin-bottom: 12px;
}
.map-tune__sec h4 {
  margin: 0 0 6px;
  font-size: 12px;
  color: #7dd3fc;
  font-weight: 600;
}
.map-tune__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.map-tune__row span {
  flex: 1 1 120px;
  min-width: 100px;
}
.map-tune__row--color span {
  flex: 1 1 140px;
}
.map-tune__row input[type="range"] {
  flex: 2 1 140px;
}
.map-tune__num {
  width: 88px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: #e0f2fe;
  border-radius: 4px;
  padding: 2px 6px;
}
.map-tune__num.sm {
  width: 62px;
}
.map-tune__text {
  flex: 2 1 120px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(56, 189, 248, 0.25);
  color: #e0f2fe;
  border-radius: 4px;
  padding: 2px 6px;
}
.map-tune__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid rgba(56, 189, 248, 0.2);
}
.map-tune__btn {
  flex: 1 1 auto;
  min-width: 120px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid rgba(56, 189, 248, 0.45);
  background: rgba(14, 116, 144, 0.35);
  color: #e0f2fe;
  cursor: pointer;
  font-size: 12px;
}
.map-tune__btn:hover {
  background: rgba(14, 116, 144, 0.55);
}
.map-tune__btn.is-ghost {
  background: transparent;
  opacity: 0.9;
}
</style>
