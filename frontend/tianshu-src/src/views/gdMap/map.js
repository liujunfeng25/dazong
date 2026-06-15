import {
  Fog,
  Group,
  MeshBasicMaterial,
  DirectionalLight,
  AmbientLight,
  HemisphereLight,
  PointLight,
  Vector3,
  Vector4,
  MeshLambertMaterial,
  LineBasicMaterial,
  Color,
  MeshStandardMaterial,
  PlaneGeometry,
  Mesh,
  DoubleSide,
  RepeatWrapping,
  SRGBColorSpace,
  AdditiveBlending,
  VideoTexture,
  NearestFilter,
  BoxGeometry,
  TubeGeometry,
  QuadraticBezierCurve3,
  PointsMaterial,
  CanvasTexture,
  DataTexture,
  RGBAFormat,
  Sprite,
  SpriteMaterial,
  CustomBlending,
  AddEquation,
  DstColorFactor,
  OneFactor,
  TextureLoader,
  BufferGeometry,
} from "three";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import tianshuAtmosphereBg from "@/assets/images/tianshu-map-atmosphere-bg.png";
import {
  Mini3d,
  ExtrudeMap,
  BaseMap,
  Line,
  Grid,
  Label3d,
  Plane,
  Particles,
  GradientShader,
  DiffuseShader,
  Focus,
} from "@/mini3d";

import { geoMercator } from "d3-geo";
import labelIcon from "@/assets/texture/label-icon.png";
import chinaData from "./map/chinaData";
import provincesData from "./map/provincesData";
import scatterData from "./map/scatter";
import infoData from "./map/infoData";
import gsap from "gsap";
import emitter from "@/utils/emitter";
import { InteractionManager } from "three.interactive";
import { MAP_VISUAL_DEFAULTS } from "./mapVisualConfig.js";
import {
  mergeMapVisual,
  loadMapVisualOverrides,
  saveMapVisualSnapshot,
} from "./mapVisualStorage.js";
import { computeShapeSpaceBounds } from "./mapGeoBounds.js";
import { loadAmapSatelliteTexture } from "./amapSatelliteTexture.js";

function installGeometryNaNGuard() {
  const proto = BufferGeometry?.prototype;
  if (!proto || proto.__tianshuNaNGuardInstalled) return;
  const raw = proto.computeBoundingSphere;
  proto.computeBoundingSphere = function computeBoundingSphereWithTianshuGuard() {
    const pos = this?.attributes?.position;
    const arr = pos?.array;
    if (arr && typeof arr.length === "number") {
      let touched = false;
      for (let i = 0; i < arr.length; i += 1) {
        if (!Number.isFinite(Number(arr[i]))) {
          arr[i] = 0;
          touched = true;
        }
      }
      if (touched && pos) pos.needsUpdate = true;
    }
    return raw.call(this);
  };
  proto.__tianshuNaNGuardInstalled = true;
}

installGeometryNaNGuard();

/** 与 createDistrictLabels 内 this.districtLabelStyle 同步的默认绘制参数 */
const DISTRICT_LABEL_DEFAULT = {
  fontSize: 15,
  fontWeight: 500,
  scaleK: 0.058,
  strokeOuter: 2,
  strokeInner: 1,
  shadowBlur: 4,
};

/** 东西城质心过近时略向两侧拉开（投影坐标） */
const DISTRICT_LABEL_OFFSET = {
  东城区: { dx: 0.68, dy: 0.22 },
  110101: { dx: 0.68, dy: 0.22 },
  西城区: { dx: -0.68, dy: -0.22 },
  110102: { dx: -0.68, dy: -0.22 },
};

/** 雄安新区三县 adcode（DataV 县级边界，与 `雄安新区.json` 一致） */
const XIONGAN_DISTRICT_ADCODES = new Set([130629, 130632, 130638]);

/** 区县名 WebGL Sprite（无衬底，描边 + 渐变字 + 轻发光） */
function createDistrictNameSprite(text, scaleFactor, style = {}) {
  const st = { ...DISTRICT_LABEL_DEFAULT, ...style };
  const {
    fontSize,
    fontWeight,
    strokeOuter,
    strokeInner,
    shadowBlur,
  } = st;
  const padX = Math.max(5, Math.round(fontSize * 0.4));
  const padY = Math.max(4, Math.round(fontSize * 0.28));
  const fontFamily = '"PingFang SC","Microsoft YaHei",sans-serif';
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Canvas 2D unsupported");
  }
  ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`;
  const textW = Math.ceil(ctx.measureText(text).width);
  const w = textW + padX * 2;
  const h = fontSize + padY * 2;
  const pr =
    typeof window !== "undefined" ? Math.min(window.devicePixelRatio || 1, 3) : 1;
  canvas.width = Math.ceil(w * pr);
  canvas.height = Math.ceil(h * pr);
  ctx.setTransform(pr, 0, 0, pr, 0, 0);
  ctx.font = `${fontWeight} ${fontSize}px ${fontFamily}`;

  const tx = w / 2;
  const ty = h / 2;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";

  ctx.lineWidth = strokeOuter;
  ctx.strokeStyle = "rgba(6, 18, 32, 0.78)";
  ctx.strokeText(text, tx, ty);
  ctx.lineWidth = strokeInner;
  ctx.strokeStyle = "rgba(72, 210, 255, 0.35)";
  ctx.strokeText(text, tx, ty);

  ctx.save();
  ctx.fillStyle = "#ffffff";
  ctx.shadowColor = "rgba(0, 0, 0, 0.42)";
  ctx.shadowBlur = Math.max(2, shadowBlur * 0.45);
  ctx.fillText(text, tx, ty);
  ctx.restore();

  const tg = ctx.createLinearGradient(
    tx - textW * 0.55,
    ty - fontSize * 0.35,
    tx + textW * 0.55,
    ty + fontSize * 0.35,
  );
  tg.addColorStop(0, "#ffffff");
  tg.addColorStop(0.55, "#f2fbff");
  tg.addColorStop(1, "#d8f4ff");
  ctx.fillStyle = tg;
  ctx.fillText(text, tx, ty);

  const tex = new CanvasTexture(canvas);
  tex.colorSpace = SRGBColorSpace;
  tex.needsUpdate = true;
  tex.anisotropy = 4;
  const mat = new SpriteMaterial({
    map: tex,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    fog: false,
  });
  const sprite = new Sprite(mat);
  sprite.center.set(0.5, 0.5);
  sprite.renderOrder = 50;
  sprite.scale.set(w * scaleFactor, h * scaleFactor, 1);
  return sprite;
}

function sortByValue(data) {
  data.sort((a, b) => b.value - a.value);
  return data;
}

/** 订单飞线（配送商→客户）参数：条数上限、拱高、线径（与模板 createFlyLine 同纹理） */
const HQ_FLYLINE_MAX = 48;
const HQ_FLYLINE_ARCH_Z = 3.55;
const HQ_FLYLINE_RADIUS = 0.072;
/** 外晕管半径倍率（Additive + 暗底上更易读出轨迹） */
const HQ_FLYLINE_GLOW_RADIUS_MUL = 2.45;
/** 外层光晕色调（偏电青） */
const HQ_FLYLINE_GLOW_COLOR = 0x38c8ff;
/** 内芯更亮，与 mapFlyline 流动纹理相乘后仍清晰 */
const HQ_FLYLINE_CORE_COLOR = 0xeeffff;

export class World extends Mini3d {
  constructor(canvas, assets) {
    super(canvas);
    // 中心坐标（决定网格/扩散圈等效果的原点位置）
    this.geoProjectionCenter = [116.4157645, 39.9163385];
    // 北京市 JSON 需较大 scale 才能在场景中有可辨尺度（模板省域常用 120，此处保留本项目可用比例）
    this.geoProjectionScale = 2800;
    // 飞线中心
    this.flyLineCenter = [116.4157645, 39.9163385];
    this.mapVisual = mergeMapVisual(
      MAP_VISUAL_DEFAULTS,
      loadMapVisualOverrides(),
    );
    /** 区县挤出逻辑高度（与光柱/飞线等 this.depth + * 联动） */
    this.depth = this.mapVisual.extrudeDepth;
    this._extrudeGeometryDepth = this.mapVisual.extrudeDepth;
    this._extrudeMapInstance = null;
    this._mapTopBaseMap = null;
    this._districtLineInstance = null;
    this._chinaBgMaterial = null;
    this._chinaLineMaterial = null;
    this._extrudeTopShaderUniforms = null;
    this._extrudeSideShaderUniforms = null;
    this._mapTopFaceGradient = null;
    this._cityFocusMarker = null;
    this._ambientLight = null;
    this._hemiLight = null;
    this._dirKey = null;
    this._dirFill = null;
    this._dirRim = null;
    this._visualPointLights = [];
    // 是否点击
    this.clicked = false;
    /** 与食迅指挥台氛围图一致：深海军 + 电青雾（TextureLoader 成功后覆盖纯色） */
    const atmosphereFallback = this.mapVisual.atmosphereColor;
    this.scene.fog = new Fog(
      atmosphereFallback,
      this.mapVisual.fogNear,
      this.mapVisual.fogFar,
    );
    this.scene.background = new Color(atmosphereFallback);
    new TextureLoader().load(
      tianshuAtmosphereBg,
      (tex) => {
        tex.colorSpace = SRGBColorSpace;
        this.scene.background = tex;
      },
      undefined,
      () => {},
    );

    // 开场拉远：略抬高，避免推进过程里长时间「贴地扁带」观感
    this.camera.instance.position.set(-16, 58, 345);
    this.camera.instance.near = 1;
    this.camera.instance.far = 10000;
    // 鸟瞰平面：适中 FOV + 高 Y、较短水平距离，视线以俯视为主（避免 y≪z 的侧向透视）
    this.camera.instance.fov = 45;
    this.camera.instance.updateProjectionMatrix();
    // 观察点略向北（-Z），构图略下移，减轻顶栏遮挡
    this.camera.controls.target.set(0, 0, -6);
    this.camera.controls.update();
    // 创建交互管理
    this.interactionManager = new InteractionManager(
      this.renderer.instance,
      this.camera.instance,
      this.canvas,
    );

    this.assets = assets;
    this.districtLabelStyle = { ...DISTRICT_LABEL_DEFAULT };
    /** 开场结束后的全市视角（与 gsap 落点一致，用于下钻后恢复） */
    this._cityViewCamera = {
      position: new Vector3(-0.0955, 97.0488, 79.9121),
      target: new Vector3(0, 0, -6),
    };
    this._drilledDistrict = null;
    this._drillTween = null;
    /** 与 index.vue districtDrillDataSeq 对齐，丢弃被 kill 的旧 tween 的 data 回调 */
    this._drillDataSeq = 0;
    this._cityViewReady = false;
    /** 今日订单光柱（与 createBar 同源质感） */
    this.orderPillarGroup = null;
    this._orderPillarInteractives = [];
    /** 为 true 时跳过开场末尾对散点/信息点的默认显示（已与订单光柱互斥） */
    this._useOrderPillars = false;
    /** 订单柱底部动态波纹：与 createFocus 同源 `Focus`（省级 provincesData 为空时场上本无 createQuan 柱） */
    this._orderFocusMarkers = [];
    /** 总部→订单 业务飞线：内芯 + 外晕两套材质（销毁时分别 dispose） */
    this._hqFlyLineMaterial = null;
    this._hqFlyLineGlowMaterial = null;
    /** 高德卫星拼贴（挤出顶 + mapTop 共用） */
    this._geoMercatorInstance = null;
    this._satelliteState = {
      bounds: new Vector4(0, 0, 1, 1),
      map: null,
      weight: { value: 0 },
    };
    this._satelliteLoadAbort = null;
    // 创建环境光
    this.initEnvironment();
    this.init();
  }

  /** 合并多个 GeoJSON FeatureCollection（字符串或已解析对象），供挤出/顶面/界线共用 */
  _mergeGeoJsonFeatureCollections(rawList) {
    const features = [];
    for (const raw of rawList) {
      if (raw == null || raw === "") continue;
      const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
      if (obj?.features?.length) {
        for (const f of obj.features) features.push(f);
      }
    }
    return JSON.stringify({ type: "FeatureCollection", features });
  }

  /** 北京市 + 雄安新区县级面数据 */
  getFocusMapGeoJsonString() {
    return this._mergeGeoJsonFeatureCollections([
      this.assets.instance.getResource("mapJson"),
      this.assets.instance.getResource("xiongAnMapJson"),
    ]);
  }

  /** 北京市轮廓数据 + 雄安边界（流光管线） */
  getFocusMapStrokeGeoJsonString() {
    return this._mergeGeoJsonFeatureCollections([
      this.assets.instance.getResource("mapStroke"),
      this.assets.instance.getResource("xiongAnMapJson"),
    ]);
  }

  init() {
    // 标签组
    this.labelGroup = new Group();
    this.label3d = new Label3d(this);
    this.labelGroup.rotation.x = -Math.PI / 2;
    this.scene.add(this.labelGroup);
    this._districtSprites = [];
    // 飞线焦点光圈组
    this.flyLineFocusGroup = new Group();
    this.flyLineFocusGroup.visible = false;
    this.flyLineFocusGroup.rotation.x = -Math.PI / 2;
    this.scene.add(this.flyLineFocusGroup);
    // 区域事件元素
    this.eventElement = [];
    // 鼠标移上移除的材质
    this.defaultMaterial = null; // 默认材质
    this.defaultLightMaterial = null; // 高亮材质
    // 创建底部高亮
    this.createBottomBg();
    // 模糊边线
    this.createChinaBlurLine();

    // 展会级视觉：去掉透视地面方格（mini3d Grid），避免底部「棋盘格」抢主体
    // 旋转圆环
    this.createRotateBorder();
    // 创建标签
    this.createLabel();
    // 创建地图
    this.createMap();
    // 添加事件
    this.createEvent();
    // 创建飞线
    this.createFlyLine();
    // 创建飞线焦点
    this.createFocus();
    // 创建粒子
    this.createParticles();
    // 创建散点图
    this.createScatter();
    // 创建信息点
    this.createInfoPoint();
    // 创建轮廓
    this.createStorke();
    // this.time.on("tick", () => {
    //   console.log(this.camera.instance.position);
    // });
    // 创建动画时间线
    let tl = gsap.timeline({
      onComplete: () => {},
    });
    tl.pause();
    this.animateTl = tl;
    tl.addLabel("focusMap", 1.5);
    tl.addLabel("focusMapOpacity", 2);
    tl.addLabel("bar", 3);
    tl.to(this.camera.instance.position, {
      duration: 2,
      x: -0.0955,
      y: 97.0488,
      z: 79.9121,
      ease: "circ.out",
      onStart: () => {
        this.flyLineFocusGroup.visible = false;
      },
    });
    tl.to(
      this.focusMapGroup.position,
      {
        duration: 1,
        x: 0,
        y: 0,
        z: 0,
      },
      "focusMap",
    );

    // 保底：focusMapGroup 初始 scale 已为 1，这里只触发后续可见性，不再 tween scale
    tl.call(
      () => {
        this.flyLineGroup.visible = true;
        if (this.orderFlyLineGroup?.children?.length) {
          this.orderFlyLineGroup.visible = true;
        }
        if (this.scatterGroup) this.scatterGroup.visible = false;
        if (this.InfoPointGroup) this.InfoPointGroup.visible = false;
      },
      [],
      "focusMap",
    );

    // 保底：focusMap 顶/侧材质 opacity 初始即为 1（见 createProvinceMaterial），不再依赖 timeline tween
    tl.call(
      () => {
        if (this.focusMapSideMaterial) this.focusMapSideMaterial.transparent = false;
      },
      [],
      "focusMapOpacity",
    );
    this.otherLabel.map((item, index) => {
      let element = item.element.querySelector(".other-label");
      if (!element) return;
      tl.to(
        element,
        {
          duration: 1,
          delay: 0.1 * index,
          translateY: 0,
          opacity: 1,
          ease: "circ.out",
        },
        "focusMapOpacity",
      );
    });
    tl.to(
      this.mapLineMaterial,
      {
        duration: 0.55,
        delay: 0.18,
        opacity: this.mapVisual.districtLineOpacity,
        ease: "circ.out",
      },
      "focusMapOpacity",
    );
    tl.to(
      this.rotateBorder1.scale,
      {
        delay: 0.3,
        duration: 1,
        x: 1,
        y: 1,
        z: 1,
        ease: "circ.out",
      },
      "focusMapOpacity",
    );
    tl.to(
      this.rotateBorder2.scale,
      {
        duration: 1,
        delay: 0.5,
        x: 1,
        y: 1,
        z: 1,
        ease: "circ.out",
        onComplete: () => {
          this.flyLineFocusGroup.visible = true;
          this._cityViewReady = true;
          emitter.$emit("mapPlayComplete");
        },
      },
      "focusMapOpacity",
    );
    this.allBar.map((item, index) => {
      if (item.userData.name === "广州市") {
        return false;
      }
      tl.to(
        item.scale,
        {
          duration: 1,
          delay: 0.1 * index,
          x: 1,
          y: 1,
          z: 1,
          ease: "circ.out",
        },
        "bar",
      );
    });
    this.allBarMaterial.map((item, index) => {
      tl.to(
        item,
        {
          duration: 1,
          delay: 0.1 * index,
          opacity: 1,
          ease: "circ.out",
        },
        "bar",
      );
    });

    this.allProvinceLabel.map((item, index) => {
      let element = item.element.querySelector(".provinces-label-wrap");
      let number = item.element.querySelector(".number .value");
      let numberVal = Number(number.innerText);
      let numberAnimate = {
        score: 0,
      };
      tl.to(
        element,
        {
          duration: 1,
          delay: 0.2 * index,
          translateY: 0,
          opacity: 1,
          ease: "circ.out",
        },
        "bar",
      );
      tl.to(
        numberAnimate,
        {
          duration: 1,
          delay: 0.2 * index,
          score: numberVal,
          onUpdate: showScore,
        },
        "bar",
      );
      function showScore() {
        number.innerText = numberAnimate.score.toFixed(0);
      }
    });
    this.allGuangquan.map((item, index) => {
      tl.to(
        item.children[0].scale,
        {
          duration: 1,
          delay: 0.1 * index,
          x: 1,
          y: 1,
          z: 1,
          ease: "circ.out",
        },
        "bar",
      );
      tl.to(
        item.children[1].scale,
        {
          duration: 1,
          delay: 0.1 * index,
          x: 1,
          y: 1,
          z: 1,
          ease: "circ.out",
        },
        "bar",
      );
    });
  }

  initEnvironment() {
    const v = this.mapVisual;
    this._ambientLight = new AmbientLight(v.ambientColor, v.ambientIntensity);
    this.scene.add(this._ambientLight);
    this._hemiLight = new HemisphereLight(
      v.hemiSky,
      v.hemiGround,
      v.hemiIntensity,
    );
    this.scene.add(this._hemiLight);
    this._dirKey = new DirectionalLight(v.dirKeyColor, v.dirKeyIntensity);
    this._dirKey.position.set(0, 48, 10);
    this._dirKey.castShadow = false;
    this.scene.add(this._dirKey);
    this._dirFill = new DirectionalLight(v.dirFillColor, v.dirFillIntensity);
    this._dirFill.position.set(36, 22, -8);
    this.scene.add(this._dirFill);
    this._dirRim = new DirectionalLight(v.dirRimColor, v.dirRimIntensity);
    this._dirRim.position.set(-22, 14, 18);
    this.scene.add(this._dirRim);
    this._visualPointLights = [];
    this._visualPointLights.push(
      this.createPointLight({
        color: v.pointColor,
        intensity: v.pointIntensity0,
        distance: 10000,
        x: -6,
        y: 14,
        z: 4,
      }),
    );
    this._visualPointLights.push(
      this.createPointLight({
        color: v.pointColor,
        intensity: v.pointIntensity1,
        distance: 10000,
        x: 10,
        y: 12,
        z: -4,
      }),
    );
  }
  createPointLight(pointParams) {
    const c = new Color(pointParams.color || "#2a5580");
    const pointLight = new PointLight(
      c.getHex(),
      pointParams.intensity,
      pointParams.distance,
    );
    pointLight.position.set(pointParams.x, pointParams.y, pointParams.z);
    this.scene.add(pointLight);
    return pointLight;
  }
  createMap() {
    let mapGroup = new Group();
    let focusMapGroup = new Group();
    this.focusMapGroup = focusMapGroup;
    let { china, chinaTopLine } = this.createChina();
    let { map, mapTop, mapLine } = this.createProvince();
    china.setParent(mapGroup);
    chinaTopLine.setParent(mapGroup);
    // 创建扩散
    this.createDiffuse();
    map.setParent(focusMapGroup);
    mapTop.setParent(focusMapGroup);
    mapLine.setParent(focusMapGroup);
    focusMapGroup.position.set(0, 0, -0.01);
    // 保底：scale 初始即为 1，地图始终可见；开场缩放动画走 mapGroup.scale 而非压扁 focusMapGroup
    focusMapGroup.scale.set(1, 1, 1);
    mapGroup.add(focusMapGroup);
    mapGroup.rotation.x = -Math.PI / 2;
    mapGroup.position.set(0, 0.2, 0);
    this.scene.add(mapGroup);
    this.mapGroup = mapGroup;
    // 与 mapGroup 同偏移，避免 CSS3D 省份标签与地图错位
    this.labelGroup.position.set(0, 0.2, 0);
    this.createBar();
    this.createDistrictLabels();
  }

  _clearDistrictSprites() {
    if (!this._districtSprites?.length) return;
    for (const s of this._districtSprites) {
      this.focusMapGroup?.remove(s);
      s.material.map?.dispose();
      s.material.dispose();
    }
    this._districtSprites = [];
  }

  /** 区县名：挂在 focusMapGroup，与挤出地图同一局部坐标系 */
  createDistrictLabels() {
    if (!this.focusMapGroup) return;
    this._clearDistrictSprites();
    const mapJsonRaw = this.getFocusMapGeoJsonString();
    const mapJsonData =
      typeof mapJsonRaw === "string"
        ? JSON.parse(mapJsonRaw)
        : mapJsonRaw;
    if (!mapJsonData?.features?.length) return;
    const feats = [...mapJsonData.features].filter((f) => {
      const ad = f.properties?.adcode;
      const adNum = ad != null ? Number(ad) : NaN;
      return (
        f.properties?.level === "district" &&
        ad != null &&
        (String(ad).startsWith("1101") ||
          XIONGAN_DISTRICT_ADCODES.has(adNum))
      );
    });
    feats.sort(
      (a, b) => Number(a.properties?.adcode) - Number(b.properties?.adcode),
    );
    const scaleK =
      this.districtLabelStyle.scaleK ?? DISTRICT_LABEL_DEFAULT.scaleK;
    const style = this.districtLabelStyle;
    for (const f of feats) {
      const name = f.properties?.name;
      const c = f.properties?.centroid || f.properties?.center;
      if (!name || !Array.isArray(c) || c.length < 2) continue;
      const [x, y] = this.geoProjection(c);
      const ad = f.properties?.adcode;
      const adKey = ad != null ? String(ad) : "";
      const off =
        DISTRICT_LABEL_OFFSET[name] ??
        DISTRICT_LABEL_OFFSET[adKey] ??
        { dx: 0, dy: 0 };
      const sprite = createDistrictNameSprite(name, scaleK, style);
      sprite.position.set(
        x + off.dx,
        -y + off.dy,
        this.depth + this.mapVisual.districtLabelZOffset,
      );
      this.focusMapGroup.add(sprite);
      this._districtSprites.push(sprite);
    }
  }

  createChina() {
    const v = this.mapVisual;
    let params = {
      chinaBgMaterialColor: v.chinaBg,
      lineColor: v.chinaLine,
    };
    let chinaData = this.assets.instance.getResource("china");
    let chinaBgMaterial = new MeshLambertMaterial({
      color: new Color(params.chinaBgMaterialColor),
      transparent: true,
      opacity: v.chinaBgOpacity,
    });
    this._chinaBgMaterial = chinaBgMaterial;
    let china = new BaseMap(this, {
      //position: new Vector3(0, 0, -0.03),
      data: chinaData,
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      merge: true,
      material: chinaBgMaterial,
      renderOrder: 2,
    });
    let chinaTopLineMaterial = new LineBasicMaterial({
      color: params.lineColor,
    });
    this._chinaLineMaterial = chinaTopLineMaterial;
    let chinaTopLine = new Line(this, {
      // position: new Vector3(0, 0, -0.02),
      data: chinaData,
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      material: chinaTopLineMaterial,
      renderOrder: 3,
    });
    chinaTopLine.lineGroup.position.z += 0.01;
    return { china, chinaTopLine };
  }
  createProvince() {
    let mapJsonData = this.getFocusMapGeoJsonString();
    const v0 = this.mapVisual;
    const shapeBounds = computeShapeSpaceBounds(mapJsonData, (pt) =>
      this.geoProjection(pt),
    );
    const ix = 1 / Math.max(shapeBounds.maxX - shapeBounds.minX, 1e-6);
    const iy = 1 / Math.max(shapeBounds.maxY - shapeBounds.minY, 1e-6);
    this._satelliteState.bounds.set(
      shapeBounds.minX,
      shapeBounds.minY,
      ix,
      iy,
    );
    this._satelliteState.weight.value = 0;
    this._ensureSatellitePlaceholder();

    this._satelliteLoadAbort?.abort();
    this._satelliteLoadAbort = new AbortController();
    const satSignal = this._satelliteLoadAbort.signal;

    let [topMaterial, sideMaterial] = this.createProvinceMaterial();
    this.focusMapTopMaterial = topMaterial;
    this.focusMapSideMaterial = sideMaterial;
    let map = new ExtrudeMap(this, {
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      position: new Vector3(0, 0, 0.11),
      data: mapJsonData,
      depth: this._extrudeGeometryDepth,
      topFaceMaterial: topMaterial,
      sideMaterial: sideMaterial,
      renderOrder: 9,
    });
    this._extrudeMapInstance = map;
    let faceMaterial = new MeshStandardMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: v0.mapTopOpacity,
    });
    let faceGradientShader = new GradientShader(faceMaterial, {
      uColor1: v0.mapTopGradient1,
      uColor2: v0.mapTopGradient2,
      dir: "y",
      size: v0.mapTopGradientSize,
      satellite: this._satelliteState,
    });
    this._mapTopFaceGradient = faceGradientShader;
    this.defaultMaterial = faceMaterial;
    this.defaultLightMaterial = this.defaultMaterial.clone();
    this.defaultLightMaterial.color = new Color(v0.mapHoverTint);
    this.defaultLightMaterial.opacity = v0.mapHoverOpacity;
    // this.defaultLightMaterial.emissive.setHex(new Color("rgba(115,208,255,1)"));
    // this.defaultLightMaterial.emissiveIntensity = 3.5;
    let mapTop = new BaseMap(this, {
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      position: new Vector3(
        0,
        0,
        this.depth + v0.mapTopZOffset,
      ),
      data: mapJsonData,
      material: faceMaterial,
      renderOrder: 2,
    });
    this._mapTopBaseMap = mapTop;
    mapTop.mapGroup.children.map((group) => {
      group.children.map((mesh) => {
        if (mesh.type === "Mesh") {
          this.eventElement.push(mesh);
        }
      });
    });
    // 区界：mockup 式细亮线 + 轻微霓虹感（单层 Line2，避免粗双线）
    const rw = this.sizes?.width ?? 1920;
    const rh = this.sizes?.height ?? 1080;
    this.mapLineMaterial = new LineMaterial({
      color: v0.districtLineColor,
      linewidth: v0.districtLineWidth,
      transparent: true,
      opacity: 0,
      depthTest: true,
      depthWrite: false,
      fog: false,
    });
    this.mapLineMaterial.resolution.set(rw, rh);
    let mapLine = new Line(this, {
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      data: mapJsonData,
      material: this.mapLineMaterial,
      type: "Line2",
      renderOrder: 4,
    });
    mapLine.lineGroup.position.z = this.depth + v0.districtLineZOffset;
    this._districtLineInstance = mapLine;
    this._applyExtrudeScaleForDepth();

    const merc = this.getGeoMercator();
    loadAmapSatelliteTexture(
      mapJsonData,
      (pt) => this.geoProjection(pt),
      merc,
      { signal: satSignal },
    )
      .then((tex) => {
        if (!tex || satSignal.aborted) {
          tex?.dispose?.();
          return;
        }
        const old = this._satelliteState.map;
        if (old && old !== tex) {
          old.dispose();
        }
        this._satelliteState.map = tex;
        const w = 0.88;
        this._satelliteState.weight.value = w;
        const eu = this._extrudeTopShaderUniforms;
        if (eu?.uSatelliteMap) {
          eu.uSatelliteMap.value = tex;
          eu.uSatelliteWeight.value = w;
        }
        const gs = this._mapTopFaceGradient?.shader;
        if (gs?.uniforms?.uSatelliteMap) {
          gs.uniforms.uSatelliteMap.value = tex;
          gs.uniforms.uSatelliteWeight.value = w;
        }
      })
      .catch(() => {});

    return {
      map,
      mapTop,
      mapLine,
    };
  }

  _ensureSatellitePlaceholder() {
    if (this._satelliteState.map) {
      return;
    }
    const data = new Uint8Array([255, 255, 255, 255]);
    const t = new DataTexture(data, 1, 1, RGBAFormat);
    t.needsUpdate = true;
    t.colorSpace = SRGBColorSpace;
    this._satelliteState.map = t;
  }

  createProvinceMaterial() {
    const vm = this.mapVisual;
    const topBoost = vm.extrudeTopRgbBoost;
    const sideBoost = vm.extrudeSideRgbBoost;
    const st = this._satelliteState;
    let topMaterial = new MeshLambertMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 1,
      fog: false,
      side: DoubleSide,
    });
    topMaterial.onBeforeCompile = (shader) => {
      shader.uniforms.uColor1 = {
        value: new Color(vm.extrudeTopTint),
      };
      shader.uniforms.uTopAlpha = { value: vm.extrudeTopAlpha };
      shader.uniforms.uTopRgbBoost = {
        value: new Vector3(topBoost[0], topBoost[1], topBoost[2]),
      };
      shader.uniforms.uSatelliteB = { value: st.bounds };
      shader.uniforms.uSatelliteMap = { value: st.map };
      shader.uniforms.uSatelliteWeight = st.weight;
      const vertHead = `
        attribute float alpha;
        varying vec3 vPosition;
        varying float vAlpha;
        uniform vec4 uSatelliteB;
        varying vec2 vSatUv;
        void main() {
          vAlpha = alpha;
          vPosition = position;
          vSatUv = vec2(
            (position.x - uSatelliteB.x) * uSatelliteB.z,
            (position.y - uSatelliteB.y) * uSatelliteB.w
          );
      `;
      const fragHead = `
        varying vec3 vPosition;
        varying float vAlpha;
        varying vec2 vSatUv;
        uniform vec3 uColor1;
        uniform float uTopAlpha;
        uniform vec3 uTopRgbBoost;
        uniform sampler2D uSatelliteMap;
        uniform float uSatelliteWeight;
        void main() {
      `;
      const fragTail = /* glsl */ `
      #ifdef OPAQUE
      diffuseColor.a = 1.0;
      #endif
            #ifdef USE_TRANSMISSION
      diffuseColor.a *= transmissionAlpha + 0.1;
      #endif
      vec3 gradient = uColor1;
      vec3 base = outgoingLight * gradient + gradient * uTopRgbBoost;
      vec2 suv = clamp(vSatUv, vec2(0.002), vec2(0.998));
      vec4 satC = texture2D(uSatelliteMap, vec2(suv.x, 1.0 - suv.y));
      vec4 satX = texture2D(uSatelliteMap, vec2(suv.x + 0.0028, 1.0 - suv.y));
      vec4 satY = texture2D(uSatelliteMap, vec2(suv.x, 1.0 - (suv.y + 0.0028)));
      float lc = dot(satC.rgb, vec3(0.299, 0.587, 0.114));
      float lx = dot(satX.rgb, vec3(0.299, 0.587, 0.114));
      float ly = dot(satY.rgb, vec3(0.299, 0.587, 0.114));
      float slope = abs(lx - lc) + abs(ly - lc);
      slope = pow(clamp(slope * 7.0, 0.0, 1.0), 0.62);
      float l = pow(clamp(lc, 0.0, 1.0), 0.48);
      float shade = mix(0.48, 1.82, l);
      float ridge = 1.0 + slope * 0.95;
      float hi = smoothstep(0.38, 0.92, l);
      vec3 tone = mix(vec3(0.88, 0.94, 1.0), vec3(0.58, 0.88, 1.06), hi * 0.9);
      vec3 bump = vec3(0.04, 0.12, 0.2) * (slope * 0.55);
      vec3 withRelief = base * shade * ridge * tone + bump;
      outgoingLight = mix(base, withRelief, uSatelliteWeight);
      if(vPosition.z>0.3){
        diffuseColor.a *= uTopAlpha;
      }
      gl_FragColor = vec4( outgoingLight, diffuseColor.a  );
      `;
      shader.vertexShader = shader.vertexShader.replace(
        "void main() {",
        vertHead,
      );
      shader.fragmentShader = shader.fragmentShader.replace(
        "void main() {",
        fragHead,
      );
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <opaque_fragment>",
        fragTail,
      );
      this._extrudeTopShaderUniforms = shader.uniforms;
    };
    let sideMap = this.assets.instance.getResource("side");
    sideMap.wrapS = RepeatWrapping;
    sideMap.wrapT = RepeatWrapping;
    sideMap.repeat.set(1, 1.5);
    sideMap.offset.y += 0.065;
    let sideMaterial = new MeshStandardMaterial({
      color: 0xffffff,
      map: sideMap,
      fog: false,
      transparent: true,
      opacity: 1,
      side: DoubleSide,
    });
    this.time.on("tick", () => {
      sideMap.offset.y += 0.005;
    });
    sideMaterial.onBeforeCompile = (shader) => {
      shader.uniforms.uColor1 = {
        value: new Color(vm.extrudeSide1),
      };
      shader.uniforms.uColor2 = {
        value: new Color(vm.extrudeSide2),
      };
      shader.uniforms.uSideZDiv = { value: vm.extrudeSideZDiv };
      shader.uniforms.uSideRgbBoost = {
        value: new Vector3(sideBoost[0], sideBoost[1], sideBoost[2]),
      };
      shader.vertexShader = shader.vertexShader.replace(
        "void main() {",
        `
        attribute float alpha;
        varying vec3 vPosition;
        varying float vAlpha;
        void main() {
          vAlpha = alpha;
          vPosition = position;
      `,
      );
      shader.fragmentShader = shader.fragmentShader.replace(
        "void main() {",
        `
        varying vec3 vPosition;
        varying float vAlpha;
        uniform vec3 uColor1;
        uniform vec3 uColor2;
        uniform float uSideZDiv;
        uniform vec3 uSideRgbBoost;
        void main() {
      `,
      );
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <opaque_fragment>",
        /* glsl */ `
      #ifdef OPAQUE
      diffuseColor.a = 1.0;
      #endif
            #ifdef USE_TRANSMISSION
      diffuseColor.a *= transmissionAlpha + 0.1;
      #endif
      vec3 gradient = mix(uColor1, uColor2, clamp(vPosition.z/uSideZDiv, 0.0, 1.0));
      outgoingLight = outgoingLight * gradient + mix(uColor1, uColor2, 0.5) * uSideRgbBoost;
      gl_FragColor = vec4( outgoingLight, diffuseColor.a  );
      `,
      );
      this._extrudeSideShaderUniforms = shader.uniforms;
    };
    return [topMaterial, sideMaterial];
  }
  createBar() {
    let self = this;
    let data = sortByValue([...provincesData]).filter((item, index) => index < 7);
    const barGroup = new Group();
    this.barGroup = barGroup;
    const factor = 0.7;
    const height = 4.0 * factor;
    if (!data.length) {
      this.allBar = [];
      this.allBarMaterial = [];
      this.allGuangquan = [];
      this.allProvinceLabel = [];
      this.scene.add(barGroup);
      return;
    }
    const max = data[0].value;
    this.allBar = [];
    this.allBarMaterial = [];
    this.allGuangquan = [];
    this.allProvinceLabel = [];
    data.map((item, index) => {
      let geoHeight = height * (item.value / max);
      let material = new MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0,
        depthTest: false,
        fog: false,
      });
      new GradientShader(material, {
        uColor1: index > 3 ? 0xfbdf88 : 0x50bbfe,
        uColor2: index > 3 ? 0xfffef4 : 0x77fbf5,
        size: geoHeight,
        dir: "y",
      });
      const geo = new BoxGeometry(0.1 * factor, 0.1 * factor, geoHeight);
      geo.translate(0, 0, geoHeight / 2);
      const mesh = new Mesh(geo, material);
      mesh.renderOrder = 5;
      let areaBar = mesh;
      let [x, y] = this.geoProjection(item.centroid);
      areaBar.position.set(x, -y, this.depth + 0.45);
      areaBar.scale.set(1, 1, 0);
      areaBar.userData = { ...item };
      let guangQuan = this.createQuan(new Vector3(x, this.depth + 0.44, y));
      let hg = this.createHUIGUANG(geoHeight, index > 3 ? 0xfffef4 : 0x77fbf5);
      areaBar.add(...hg);
      barGroup.add(areaBar);
      barGroup.rotation.x = -Math.PI / 2;
      let barLabel = labelStyle04(
        item,
        index,
        new Vector3(x, -y, this.depth + 1.1 + geoHeight),
      );
      this.allBar.push(areaBar);
      this.allBarMaterial.push(material);
      this.allGuangquan.push(guangQuan);
      this.allProvinceLabel.push(barLabel);
    });
    this.scene.add(barGroup);
    function labelStyle04(data, index, position) {
      let label = self.label3d.create("", "provinces-label", false);
      label.init(
        `<div class="provinces-label ${index > 4 ? "yellow" : ""}">
      <div class="provinces-label-wrap">
        <div class="number"><span class="value">${data.value}</span><span class="unit">万人</span></div>
        <div class="name">
          <span class="zh">${data.name}</span>
          <span class="en">${data.enName.toUpperCase()}</span>
        </div>
        <div class="no">${index + 1}</div>
      </div>
    </div>`,
        position,
      );
      self.label3d.setLabelStyle(label, 0.01, "x");
      label.setParent(self.labelGroup);
      return label;
    }
  }
  /** 区县质心在场景中的世界坐标（与 mapTop 顶面同高，供下钻对焦） */
  districtWorldCenter(districtName) {
    const mapJsonRaw = this.getFocusMapGeoJsonString();
    const mapJsonData =
      typeof mapJsonRaw === "string"
        ? JSON.parse(mapJsonRaw)
        : mapJsonRaw;
    const f = mapJsonData?.features?.find(
      (x) => x.properties?.name === districtName,
    );
    if (!f) return null;
    const c = f.properties?.centroid || f.properties?.center;
    if (!Array.isArray(c) || c.length < 2) return null;
    const [px, py] = this.geoProjection(c);
    this.focusMapGroup.updateMatrixWorld(true);
    const v = new Vector3(
      px,
      -py,
      this.depth + this.mapVisual.mapTopZOffset,
    );
    v.applyMatrix4(this.focusMapGroup.matrixWorld);
    return v;
  }

  /**
   * 与地图 mesh 点击一致：同一区县则退出下钻，否则进入/切换下钻。
   * 供「区域分布」柱状图等外部调用。
   */
  toggleDistrictDrill(districtName) {
    if (!districtName || !this._cityViewReady) return;
    if (this._drilledDistrict === districtName) {
      this.drillResetCityView();
      return;
    }
    this.drillIntoDistrict(districtName);
  }

  /**
   * 点击区县下钻：沿「全市基准视角」视线方向拉近到质心（切换区县时尺度平级，不累积拉近）。
   * 再点同一区或「返回全市」恢复。
   */
  drillIntoDistrict(districtName) {
    if (!districtName || !this.focusMapGroup) return;
    const targetPos = this.districtWorldCenter(districtName);
    if (!targetPos) return;
    this._drilledDistrict = districtName;
    const cam = this.camera.instance;
    const ctrl = this.camera.controls;
    const c = this._cityViewCamera;
    const baseDir = new Vector3().subVectors(c.position, c.target);
    const baseDist = baseDir.length();
    if (baseDist < 1e-6) return;
    baseDir.normalize();
    const drillDist = baseDist * 0.36;
    const newCamPos = targetPos.clone().add(baseDir.multiplyScalar(drillDist));
    if (this._drillTween) {
      this._drillTween.kill();
    }
    this._drillDataSeq += 1;
    const dataSeq = this._drillDataSeq;
    emitter.$emit("districtDrill", { active: true, name: districtName, seq: dataSeq });
    this._drillTween = gsap.timeline({
      onUpdate: () => ctrl.update(),
      onComplete: () => {
        emitter.$emit("districtDrillData", {
          active: true,
          name: districtName,
          seq: dataSeq,
        });
      },
    });
    this._drillTween.to(
      cam.position,
      {
        x: newCamPos.x,
        y: newCamPos.y,
        z: newCamPos.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
    this._drillTween.to(
      ctrl.target,
      {
        x: targetPos.x,
        y: targetPos.y,
        z: targetPos.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
  }

  drillResetCityView() {
    if (!this._drilledDistrict) {
      this._drillDataSeq += 1;
      const dataSeq = this._drillDataSeq;
      emitter.$emit("districtDrill", { active: false, name: "", seq: dataSeq });
      emitter.$emit("districtDrillData", { active: false, name: "", seq: dataSeq });
      return;
    }
    this._drilledDistrict = null;
    this._drillDataSeq += 1;
    const dataSeq = this._drillDataSeq;
    const cam = this.camera.instance;
    const ctrl = this.camera.controls;
    const c = this._cityViewCamera;
    if (this._drillTween) {
      this._drillTween.kill();
    }
    emitter.$emit("districtDrill", { active: false, name: "", seq: dataSeq });
    this._drillTween = gsap.timeline({
      onUpdate: () => ctrl.update(),
      onComplete: () => {
        emitter.$emit("districtDrillData", { active: false, name: "", seq: dataSeq });
      },
    });
    this._drillTween.to(
      cam.position,
      {
        x: c.position.x,
        y: c.position.y,
        z: c.position.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
    this._drillTween.to(
      ctrl.target,
      {
        x: c.target.x,
        y: c.target.y,
        z: c.target.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
  }

  /**
   * 回到进入页面、开场动画结束后的默认全市视角（与 gsap 落点及「返回全市」一致）。
   * 若处于区县下钻，会一并退出下钻状态。
   */
  resetToInitialCameraView() {
    let drillDataSeq = null;
    if (this._drilledDistrict) {
      this._drilledDistrict = null;
      this._drillDataSeq += 1;
      drillDataSeq = this._drillDataSeq;
      emitter.$emit("districtDrill", { active: false, name: "", seq: drillDataSeq });
    }
    this._drillTween?.kill();
    const cam = this.camera.instance;
    const ctrl = this.camera.controls;
    const c = this._cityViewCamera;
    const DEFAULT_FOV = 45;
    this._drillTween = gsap.timeline({
      onComplete: () => {
        this._drillTween = null;
        if (drillDataSeq != null) {
          emitter.$emit("districtDrillData", {
            active: false,
            name: "",
            seq: drillDataSeq,
          });
        }
      },
      onUpdate: () => {
        cam.updateProjectionMatrix();
        ctrl.update();
      },
    });
    this._drillTween.to(
      cam.position,
      {
        x: c.position.x,
        y: c.position.y,
        z: c.position.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
    this._drillTween.to(
      ctrl.target,
      {
        x: c.target.x,
        y: c.target.y,
        z: c.target.z,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
    this._drillTween.to(
      cam,
      {
        fov: DEFAULT_FOV,
        duration: 1.15,
        ease: "power2.inOut",
      },
      0,
    );
  }

  /**
   * 订单光柱与区县顶面重叠时，射线常先命中顶面；若光柱在视觉上更近或与顶面几乎同深，则不要触发下钻。
   */
  _shouldDeferDistrictClickForOrderPillar(ev) {
    if (!this._orderPillarInteractives?.length) return false;
    const ray = this.interactionManager.raycaster;
    ray.setFromCamera(ev.coords, this.camera.instance);
    const hits = ray.intersectObjects(this._orderPillarInteractives, true);
    if (!hits.length) return false;
    const pDist = hits[0].distance;
    const mDist = typeof ev.distance === "number" ? ev.distance : Infinity;
    return pDist <= mDist + 0.12;
  }

  /** 明确点到顶面且顶面近于光柱时，不触发订单明细（避免与下钻抢事件）。 */
  _shouldIgnorePillarClickForMapTop(ev, pillarMesh) {
    if (!this.eventElement?.length) return false;
    const ray = this.interactionManager.raycaster;
    ray.setFromCamera(ev.coords, this.camera.instance);
    const mapHits = ray.intersectObjects(this.eventElement, true);
    if (!mapHits.length) return false;
    const ph = ray.intersectObjects([pillarMesh], true);
    if (!ph.length) return false;
    return mapHits[0].distance + 0.004 < ph[0].distance;
  }

  createEvent() {
    let objectsHover = [];
    const reset = (mesh) => {
      mesh.traverse((obj) => {
        if (obj.isMesh) {
          obj.material = this.defaultMaterial;
        }
      });
    };
    const move = (mesh) => {
      mesh.traverse((obj) => {
        if (obj.isMesh) {
          obj.material = this.defaultLightMaterial;
        }
      });
    };
    this.eventElement.map((mesh) => {
      this.interactionManager.add(mesh);
      mesh.addEventListener("mousedown", (ev) => {
        if (!this._cityViewReady) return;
        if (this._shouldDeferDistrictClickForOrderPillar(ev)) return;
        const districtName = ev.target.userData?.name;
        if (!districtName) return;
        this.toggleDistrictDrill(districtName);
      });
      mesh.addEventListener("mouseover", (event) => {
        if (!objectsHover.includes(event.target.parent)) {
          objectsHover.push(event.target.parent);
        }
        document.body.style.cursor = "pointer";
        move(event.target.parent);
      });
      mesh.addEventListener("mouseout", (event) => {
        objectsHover = objectsHover.filter(
          (n) => n.userData.name !== event.target.parent.userData.name,
        );
        if (objectsHover.length > 0) {
          const mesh = objectsHover[objectsHover.length - 1];
        }
        reset(event.target.parent);
        document.body.style.cursor = "default";
      });
    });
  }
  createHUIGUANG(h, color) {
    let geometry = new PlaneGeometry(0.35, h);
    geometry.translate(0, h / 2, 0);
    const texture = this.assets.instance.getResource("huiguang");
    texture.colorSpace = SRGBColorSpace;
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    let material = new MeshBasicMaterial({
      color: color,
      map: texture,
      transparent: true,
      opacity: 0.4,
      depthWrite: false,
      side: DoubleSide,
      blending: AdditiveBlending,
    });
    let mesh = new Mesh(geometry, material);
    mesh.renderOrder = 10;
    mesh.rotateX(Math.PI / 2);
    let mesh2 = mesh.clone();
    let mesh3 = mesh.clone();
    mesh2.rotateY((Math.PI / 180) * 60);
    mesh3.rotateY((Math.PI / 180) * 120);
    return [mesh, mesh2, mesh3];
  }
  /**
   * 模板 createQuan 的唯一几何/材质实现；省级柱与订单柱共用，避免两套代码漂移。
   * @returns {{ group: Group, mesh1: Mesh, mesh2: Mesh }}
   */
  _makeQuanGroupAt(position) {
    const guangquan1 = this.assets.instance.getResource("guangquan1");
    const guangquan2 = this.assets.instance.getResource("guangquan2");
    const geometry = new PlaneGeometry(0.5, 0.5);
    const material1 = new MeshBasicMaterial({
      color: 0xffffff,
      map: guangquan1,
      alphaMap: guangquan1,
      opacity: 1,
      transparent: true,
      depthTest: false,
      fog: false,
      blending: AdditiveBlending,
    });
    const material2 = new MeshBasicMaterial({
      color: 0xffffff,
      map: guangquan2,
      alphaMap: guangquan2,
      opacity: 1,
      transparent: true,
      depthTest: false,
      fog: false,
      blending: AdditiveBlending,
    });
    const mesh1 = new Mesh(geometry, material1);
    const mesh2 = new Mesh(geometry, material2);
    mesh1.renderOrder = 6;
    mesh2.renderOrder = 6;
    mesh1.rotateX(-Math.PI / 2);
    mesh2.rotateX(-Math.PI / 2);
    mesh1.position.copy(position);
    mesh2.position.copy(position);
    mesh2.position.y -= 0.001;
    mesh1.scale.set(0, 0, 0);
    mesh2.scale.set(0, 0, 0);
    const group = new Group();
    group.add(mesh1, mesh2);
    return { group, mesh1, mesh2 };
  }

  /** 省级光柱：与历史模板一致，每柱单独 tick 旋转（仅 7 根，开销可忽略） */
  createQuan(position) {
    const { group, mesh1 } = this._makeQuanGroupAt(position);
    this.quanGroup = group;
    this.scene.add(group);
    this.time.on("tick", () => {
      mesh1.rotation.z += 0.05;
    });
    return group;
  }
  // 创建扩散
  createDiffuse() {
    let geometry = new PlaneGeometry(200, 200);
    let material = new MeshBasicMaterial({
      color: 0x000000,
      depthWrite: false,
      // depthTest: false,
      transparent: true,
      blending: CustomBlending,
    });
    // 使用CustomBlending  实现混合叠加
    material.blendEquation = AddEquation;
    material.blendSrc = DstColorFactor;
    material.blendDst = OneFactor;
    let diffuse = new DiffuseShader({
      material,
      time: this.time,
      size: 60,
      diffuseSpeed: 8.0,
      diffuseColor: 0x5a9aaa,
      diffuseWidth: 2.0,
      callback: (pointShader) => {
        setTimeout(() => {
          gsap.to(pointShader.uniforms.uTime, {
            value: 4,
            repeat: -1,
            duration: 6,
            ease: "power1.easeIn",
          });
        }, 3);
      },
    });
    let mesh = new Mesh(geometry, material);
    mesh.renderOrder = 3;
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(0, 0.21, 0);
    this.scene.add(mesh);
  }
  createGrid() {
    new Grid(this, {
      gridSize: 50,
      gridDivision: 20,
      gridColor: 0x143d5c,
      shapeSize: 0.5,
      shapeColor: 0x1f5580,
      pointSize: 0.1,
      pointColor: 0x0f3a5c,
    });
  }
  createBottomBg() {
    let geometry = new PlaneGeometry(20, 20);
    const texture = this.assets.instance.getResource("ocean");
    texture.colorSpace = SRGBColorSpace;
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.repeat.set(1, 1);
    let material = new MeshBasicMaterial({
      map: texture,
      color: 0x0c1f36,
      transparent: true,
      opacity: 0.38,
      fog: false,
    });
    let mesh = new Mesh(geometry, material);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(0, -0.7, 0);
    this.scene.add(mesh);
  }
  createChinaBlurLine() {
    let geometry = new PlaneGeometry(147, 147);
    const texture = this.assets.instance.getResource("chinaBlurLine");
    texture.colorSpace = SRGBColorSpace;
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.generateMipmaps = false;
    texture.minFilter = NearestFilter;
    texture.repeat.set(1, 1);
    let material = new MeshBasicMaterial({
      color: 0x2e6ba8,
      alphaMap: texture,
      transparent: true,
      opacity: 0.34,
    });
    let mesh = new Mesh(geometry, material);
    mesh.rotateX(-Math.PI / 2);
    mesh.position.set(-19.3, -0.5, -19.7);
    this.scene.add(mesh);
  }

  createLabel() {
    let self = this;
    let labelGroup = this.labelGroup;
    let label3d = this.label3d;
    let otherLabel = [];
    chinaData.map((province) => {
      if (province.hide == true) return false;
      let label = labelStyle01(province, label3d, labelGroup);
      otherLabel.push(label);
    });
    let iconLabel1 = labelStyle03(
      {
        icon: labelIcon,
        center: [118.280637, 21.625178],
        width: "40px",
        height: "40px",
        reflect: true,
      },
      label3d,
      labelGroup,
    );
    let iconLabel2 = labelStyle03(
      {
        icon: labelIcon,
        center: [106.280637, 25.625178],
        width: "20px",
        height: "20px",
        reflect: false,
      },
      label3d,
      labelGroup,
    );
    otherLabel.push(iconLabel1);
    otherLabel.push(iconLabel2);
    this.otherLabel = otherLabel;
    function labelStyle01(province, label3d, labelGroup) {
      let label = label3d.create(
        "",
        `china-label ${province.blur ? " blur" : ""}`,
        false,
      );
      const [x, y] = self.geoProjection(province.center);
      label.init(
        `<div class="other-label"><img class="label-icon" src="${labelIcon}">${province.name}</div>`,
        new Vector3(x, -y, 0.4),
      );
      label3d.setLabelStyle(label, 0.02, "x");
      label.setParent(labelGroup);
      return label;
    }
    function labelStyle03(data, label3d, labelGroup) {
      let label = label3d.create(
        "",
        `decoration-label  ${data.reflect ? " reflect" : ""}`,
        false,
      );
      const [x, y] = self.geoProjection(data.center);
      label.init(
        `<div class="other-label"><img class="label-icon" style="width:${data.width};height:${data.height}" src="${data.icon}">`,
        new Vector3(x, -y, 0.4),
      );
      label3d.setLabelStyle(label, 0.02, "x");
      label.setParent(labelGroup);
      return label;
    }
    function labelStyle04(data, label3d, labelGroup, index) {
      let label = label3d.create("", "provinces-label", false);
      const [x, y] = self.geoProjection(data.center);
      label.init(
        `<div class="provinces-label">
      <div class="provinces-label-wrap">
        <div class="number">${data.value}<span>万人</span></div>
        <div class="name">
          <span class="zh">${data.name}</span>
          <span class="en">${data.enName.toUpperCase()}</span>
        </div>
        <div class="no">${index + 1}</div>
      </div>
    </div>`,
        new Vector3(x, -y, 2.4),
      );
      label3d.setLabelStyle(label, 0.02, "x");
      label.setParent(labelGroup);
      return label;
    }
  }
  createRotateBorder() {
    let max = 12;
    let rotationBorder1 = this.assets.instance.getResource("rotationBorder1");
    let rotationBorder2 = this.assets.instance.getResource("rotationBorder2");
    let plane01 = new Plane(this, {
      width: max * 1.178,
      needRotate: true,
      rotateSpeed: 0.00065,
      material: new MeshBasicMaterial({
        map: rotationBorder1,
        color: 0x5cc8ff,
        transparent: true,
        opacity: 0.11,
        side: DoubleSide,
        depthWrite: false,
        blending: AdditiveBlending,
      }),
      position: new Vector3(0, 0.28, 0),
    });
    plane01.instance.rotation.x = -Math.PI / 2;
    plane01.instance.renderOrder = 6;
    plane01.instance.scale.set(0, 0, 0);
    plane01.setParent(this.scene);
    let plane02 = new Plane(this, {
      width: max * 1.116,
      needRotate: true,
      rotateSpeed: -0.0028,
      material: new MeshBasicMaterial({
        map: rotationBorder2,
        color: 0x5cc8ff,
        transparent: true,
        opacity: 0.22,
        side: DoubleSide,
        depthWrite: false,
        blending: AdditiveBlending,
      }),
      position: new Vector3(0, 0.3, 0),
    });
    plane02.instance.rotation.x = -Math.PI / 2;
    plane02.instance.renderOrder = 6;
    plane02.instance.scale.set(0, 0, 0);
    plane02.setParent(this.scene);
    this.rotateBorder1 = plane01.instance;
    this.rotateBorder2 = plane02.instance;
  }
  createFlyLine() {
    this.flyLineGroup = new Group();
    this.flyLineGroup.visible = false;
    this.scene.add(this.flyLineGroup);
    this.orderFlyLineGroup = new Group();
    this.orderFlyLineGroup.visible = false;
    this.scene.add(this.orderFlyLineGroup);
    const texture = this.assets.instance.getResource("mapFlyline");
    texture.wrapS = texture.wrapT = RepeatWrapping;
    texture.repeat.set(0.42, 2.35);
    texture.colorSpace = SRGBColorSpace;
    const tubeRadius = 0.1;
    const tubeSegments = 32;
    const tubeRadialSegments = 2;
    const closed = false;
    let [centerX, centerY] = this.geoProjection(this.flyLineCenter);
    let centerPoint = new Vector3(centerX, -centerY, 0);
    const material = new MeshBasicMaterial({
      map: texture,
      color: 0x6ef0ff,
      transparent: true,
      fog: false,
      opacity: 1,
      depthTest: false,
      depthWrite: false,
      blending: AdditiveBlending,
      toneMapped: false,
    });
    this.time.on("tick", () => {
      texture.offset.x -= 0.008;
    });
    provincesData
      .filter((item, index) => index < 7)
      .map((city) => {
        let [x, y] = this.geoProjection(city.centroid);
        let point = new Vector3(x, -y, 0);
        const center = new Vector3();
        center.addVectors(centerPoint, point).multiplyScalar(0.5);
        center.setZ(3);
        const curve = new QuadraticBezierCurve3(centerPoint, center, point);
        const tubeGeometry = new TubeGeometry(
          curve,
          tubeSegments,
          tubeRadius,
          tubeRadialSegments,
          closed,
        );
        const mesh = new Mesh(tubeGeometry, material);
        mesh.rotation.x = -Math.PI / 2;
        mesh.position.set(0, this.depth + 0.44, 0);
        mesh.renderOrder = 21;
        this.flyLineGroup.add(mesh);
      });
  }
  // 创建焦点
  createFocus() {
    let focusObj = new Focus(this, { color1: 0xbdfdfd, color2: 0xbdfdfd });
    let [x, y] = this.geoProjection(this.flyLineCenter);
    focusObj.position.set(x, -y, this.depth + 0.44);
    focusObj.scale.set(1, 1, 1);
    this.flyLineFocusGroup.add(focusObj);
    this._cityFocusMarker = focusObj;
  }
  // 创建粒子
  createParticles() {
    this.particles = new Particles(this, {
      num: 10,
      range: 30,
      dir: "up",
      speed: 0.05,
      material: new PointsMaterial({
        map: Particles.createTexture(),
        size: 1,
        color: 0x00eeee,
        transparent: true,
        opacity: 1,
        depthTest: false,
        depthWrite: false,
        vertexColors: true,
        blending: AdditiveBlending,
        sizeAttenuation: true,
      }),
    });
    this.particleGroup = new Group();
    this.scene.add(this.particleGroup);
    this.particleGroup.rotation.x = -Math.PI / 2;
    this.particles.setParent(this.particleGroup);
    this.particles.enable = true;
    this.particleGroup.visible = true;
  }
  createScatter() {
    this.scatterGroup = new Group();
    this.scatterGroup.visible = false;
    this.scatterGroup.rotation.x = -Math.PI / 2;
    this.scene.add(this.scatterGroup);
    const texture = this.assets.instance.getResource("arrow");
    const material = new SpriteMaterial({
      map: texture,
      color: 0xfffef4,
      fog: false,
      transparent: true,
      depthTest: false,
    });
    let scatterAllData = sortByValue(scatterData);
    let max = scatterAllData[0].value;
    scatterAllData.map((data) => {
      const sprite = new Sprite(material);
      sprite.renderOrder = 23;
      let scale = 0.1 + (data.value / max) * 0.2;
      sprite.scale.set(scale, scale, scale);
      let [x, y] = this.geoProjection([data.lng, data.lat]);
      sprite.position.set(x, -y, this.depth + 0.45);
      sprite.userData.position = [x, -y, this.depth + 0.45];
      this.scatterGroup.add(sprite);
    });
  }
  createInfoPoint() {
    let self = this;
    this.InfoPointGroup = new Group();
    this.scene.add(this.InfoPointGroup);
    this.InfoPointGroup.visible = false;
    this.InfoPointGroup.rotation.x = -Math.PI / 2;
    this.infoPointIndex = 0;
    this.infoPointLabelTime = null;
    this.infoLabelElement = [];
    let label3d = this.label3d;
    const texture = this.assets.instance.getResource("point");
    let colors = [0xfffef4, 0x77fbf5];
    let infoAllData = sortByValue(infoData);
    let max = infoAllData[0].value;
    infoAllData.map((data, index) => {
      const material = new SpriteMaterial({
        map: texture,
        color: colors[index % colors.length],
        fog: false,
        transparent: true,
        depthTest: false,
      });
      const sprite = new Sprite(material);
      sprite.renderOrder = 23;
      let scale = 0.7 + (data.value / max) * 0.4;
      sprite.scale.set(scale, scale, scale);
      let [x, y] = this.geoProjection([data.lng, data.lat]);
      let position = [x, -y, this.depth + 0.7];
      sprite.position.set(...position);
      sprite.userData.position = [...position];
      sprite.userData = {
        position: [x, -y, this.depth + 0.7],
        name: data.name,
        value: data.value,
        level: data.level,
        index: index,
      };
      this.InfoPointGroup.add(sprite);
      let label = infoLabel(data, label3d, this.InfoPointGroup);
      this.infoLabelElement.push(label);
      this.interactionManager.add(sprite);
      sprite.addEventListener("mousedown", (ev) => {
        if (this.clicked || !this.InfoPointGroup.visible) return false;
        this.clicked = true;
        this.infoPointIndex = ev.target.userData.index;
        this.infoLabelElement.map((label) => {
          label.visible = false;
        });
        label.visible = true;
        this.createInfoPointLabelLoop();
      });
      sprite.addEventListener("mouseup", (ev) => {
        this.clicked = false;
      });
      sprite.addEventListener("mouseover", (event) => {
        document.body.style.cursor = "pointer";
      });
      sprite.addEventListener("mouseout", (event) => {
        document.body.style.cursor = "default";
      });
    });
    function infoLabel(data, label3d, labelGroup) {
      let label = label3d.create("", "info-point", true);
      const [x, y] = self.geoProjection([data.lng, data.lat]);
      label.init(
        ` <div class="info-point-wrap">
          <div class="info-point-wrap-inner">
            <div class="info-point-line">
              <div class="line"></div>
              <div class="line"></div>
              <div class="line"></div>
            </div>
            <div class="info-point-content">
              <div class="content-item"><span class="label">名称</span><span class="value">${data.name}</span></div>
              <div class="content-item"><span class="label">PM2.5</span><span class="value">${data.value}ug/m²</span></div>
              <div class="content-item"><span class="label">等级</span><span class="value">${data.level}</span></div>
            </div>
          </div>
        </div>
      `,
        new Vector3(x, -y, self.depth + 1.9),
      );
      label3d.setLabelStyle(label, 0.015, "x");
      label.setParent(labelGroup);
      label.visible = false;
      return label;
    }
  }
  createInfoPointLabelLoop() {
    clearInterval(this.infoPointLabelTime);
    this.infoPointLabelTime = setInterval(() => {
      this.infoPointIndex++;
      if (this.infoPointIndex >= this.infoLabelElement.length) {
        this.infoPointIndex = 0;
      }
      this.infoLabelElement.map((label, i) => {
        if (this.infoPointIndex === i) {
          label.visible = true;
        } else {
          label.visible = false;
        }
      });
    }, 3000);
  }

  _setDemoMapDecorVisible(visible) {
    if (this.barGroup) this.barGroup.visible = visible;
    if (this.flyLineGroup) this.flyLineGroup.visible = visible;
    if (this.scatterGroup) this.scatterGroup.visible = false;
    if (this.InfoPointGroup) {
      this.InfoPointGroup.visible = false;
      if (this.infoLabelElement?.length) {
        this.infoLabelElement.forEach((l) => {
          l.visible = false;
        });
      }
      clearInterval(this.infoPointLabelTime);
      this.infoPointLabelTime = null;
    }
  }

  _clearOrderPillarHoverPanel() {
    emitter.$emit("tianshuOrderPillarHover", null);
  }

  /** 悬停信息改由大屏固定区位展示（index.vue），避免 CSS3D 随视距过小 */
  _showOrderPillarHover(payload) {
    emitter.$emit("tianshuOrderPillarHover", {
      role: payload.role,
      risk_type: payload.risk_type,
      risk_level: payload.risk_level,
      stage: payload.stage,
      cold_type: payload.cold_type,
      industry_type: payload.industry_type,
      product_name: payload.product_name,
      category_name: payload.category_name,
      change_pct: payload.change_pct,
      forecast_price: payload.forecast_price,
      confidence: payload.confidence,
      profile_type: payload.profile_type,
      district_name: payload.district_name,
      client_count: payload.client_count,
      canteen_count: payload.canteen_count,
      risk_count: payload.risk_count,
      vehicle_id: payload.vehicle_id,
      warehouse_id: payload.warehouse_id,
      temperature: payload.temperature,
      humidity: payload.humidity,
      trip_id: payload.trip_id,
      route_no: payload.route_no,
      status: payload.status,
      description: payload.description,
      order_sn: payload.order_sn,
      order_id: payload.order_id,
      address: String(payload.address || "").trim(),
      customer_name: payload.customer_name,
      order_count: Number(payload.order_count) || 0,
      gmv: Number(payload.gmv) || 0,
    });
  }

  /**
   * 订单落点底部：与地图中心 `createFocus` 完全相同的 `Focus`（focusMidQuan / focusMoveBg 等），缩放入场。
   * 说明：当前 `provincesData` 为空，省级 createBar/createQuan 不会生成；东城附近「厚波纹」实为该 Focus，不是 guangquan。
   */
  _createOrderFocusMarker(px, py, staggerIndex, heightNorm, focusColors) {
    if (!this.flyLineFocusGroup) return;
    const fc = focusColors || { color1: 0xbdfdfd, color2: 0xbdfdfd };
    const focusObj = new Focus(this, { color1: fc.color1, color2: fc.color2 });
    focusObj.position.set(px, -py, this.depth + 0.44);
    /** 与 createFocus 默认 scale 1 同量级；此前 0.4 级在鸟瞰下几乎只剩「细针」观感 */
    const s = 0.96 + 0.08 * Math.min(1, Math.max(0, heightNorm));
    focusObj.scale.setScalar(0.01);
    this.flyLineFocusGroup.add(focusObj);
    this._orderFocusMarkers.push(focusObj);
    const delay = Math.min(0.85, 0.02 * (staggerIndex % 45));
    gsap.to(focusObj.scale, {
      duration: 1,
      delay,
      x: s,
      y: s,
      z: s,
      ease: "circ.out",
    });
  }

  _clearOrderFlyLines() {
    if (this._hqFlyLineMaterial) {
      try {
        this._hqFlyLineMaterial.dispose();
      } catch {
        /* ignore */
      }
      this._hqFlyLineMaterial = null;
    }
    if (this._hqFlyLineGlowMaterial) {
      try {
        this._hqFlyLineGlowMaterial.dispose();
      } catch {
        /* ignore */
      }
      this._hqFlyLineGlowMaterial = null;
    }
    if (!this.orderFlyLineGroup) return;
    while (this.orderFlyLineGroup.children.length) {
      const ch = this.orderFlyLineGroup.children[0];
      this.orderFlyLineGroup.remove(ch);
      if (ch.geometry) ch.geometry.dispose();
    }
    this.orderFlyLineGroup.visible = false;
  }

  /**
   * 业务语义：金色光柱（配送商）→ 蓝色光柱（客户）。
   * 入参 lines：[{ from_lng, from_lat, to_lng, to_lat, gmv, order_count }]，
   * 由 /api/insights/business/cockpit-flylines 提供；mock 模式可叠加 mock flylines。
   */
  _safeGeoProject(lng, lat) {
    const xLng = Number(lng);
    const xLat = Number(lat);
    if (!Number.isFinite(xLng) || !Number.isFinite(xLat)) return null;
    if (xLng < 70 || xLng > 140 || xLat < 15 || xLat > 55) return null;
    const projected = this.geoProjection([xLng, xLat]);
    if (!Array.isArray(projected) || projected.length < 2) return null;
    const x = Number(projected[0]);
    const y = Number(projected[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return [x, y];
  }

  setFlylines(lines) {
    this._clearOrderFlyLines();
    if (!Array.isArray(lines) || !lines.length || !this.orderFlyLineGroup) return;

    const tex = this.assets.instance.getResource("mapFlyline");
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.repeat.set(0.38, 2.5);
    tex.colorSpace = SRGBColorSpace;

    const glowMat = new MeshBasicMaterial({
      map: tex,
      color: HQ_FLYLINE_GLOW_COLOR,
      transparent: true,
      opacity: 0.58,
      depthTest: false,
      depthWrite: false,
      fog: false,
      blending: AdditiveBlending,
      toneMapped: false,
    });
    const coreMat = new MeshBasicMaterial({
      map: tex,
      color: HQ_FLYLINE_CORE_COLOR,
      transparent: true,
      opacity: 1,
      depthTest: false,
      depthWrite: false,
      fog: false,
      blending: AdditiveBlending,
      toneMapped: false,
    });
    this._hqFlyLineGlowMaterial = glowMat;
    this._hqFlyLineMaterial = coreMat;

    const sorted = [...lines].sort(
      (a, b) => (Number(b.gmv) || 0) - (Number(a.gmv) || 0),
    );
    const slice = sorted.slice(0, HQ_FLYLINE_MAX);

    const archZ = HQ_FLYLINE_ARCH_Z;
    const tubeSegments = 48;
    const rad = HQ_FLYLINE_RADIUS;
    const radSeg = 5;
    const flyY = this.depth + 0.52;

    for (const line of slice) {
      const from = this._safeGeoProject(line.from_lng, line.from_lat);
      const to = this._safeGeoProject(line.to_lng, line.to_lat);
      if (!from || !to) continue;
      const [fx, fy] = from;
      const [tx, ty] = to;
      const start = new Vector3(fx, -fy, 0);
      const end = new Vector3(tx, -ty, 0);
      if (start.distanceToSquared(end) < 1e-10) continue;
      const mid = new Vector3().addVectors(start, end).multiplyScalar(0.5);
      mid.setZ(archZ);
      const curve = new QuadraticBezierCurve3(start, mid, end);

      const geomGlow = new TubeGeometry(curve, tubeSegments, rad * HQ_FLYLINE_GLOW_RADIUS_MUL, radSeg, false);
      const meshGlow = new Mesh(geomGlow, glowMat);
      meshGlow.rotation.x = -Math.PI / 2;
      meshGlow.position.set(0, flyY, 0);
      meshGlow.renderOrder = 19;
      this.orderFlyLineGroup.add(meshGlow);

      const geomCore = new TubeGeometry(curve, tubeSegments, rad, radSeg, false);
      const meshCore = new Mesh(geomCore, coreMat);
      meshCore.rotation.x = -Math.PI / 2;
      meshCore.position.set(0, flyY, 0);
      meshCore.renderOrder = 22;
      this.orderFlyLineGroup.add(meshCore);
    }
    this.orderFlyLineGroup.visible = this.orderFlyLineGroup.children.length > 0;
  }

  _clearOrderPillars() {
    this._clearOrderPillarHoverPanel();
    // 飞线 group 独立 lifecycle，由 setFlylines 自身管理；这里清柱子时不连带清飞线，
    // 否则 loadFlylines 与 loadTodayOrderPillars 异步并行时飞线会被刷掉。
    for (const f of this._orderFocusMarkers) {
      try {
        this.flyLineFocusGroup?.remove(f);
        f.destroy?.();
      } catch {
        /* ignore */
      }
    }
    this._orderFocusMarkers = [];
    for (const m of this._orderPillarInteractives) {
      try {
        this.interactionManager.remove(m);
      } catch {
        /* ignore */
      }
    }
    this._orderPillarInteractives = [];
    if (this.orderPillarGroup) {
      this.orderPillarGroup.traverse((obj) => {
        if (obj.geometry) obj.geometry.dispose();
        const mat = obj.material;
        if (mat) {
          if (Array.isArray(mat)) mat.forEach((mm) => mm.dispose?.());
          else mat.dispose?.();
        }
      });
      this.scene.remove(this.orderPillarGroup);
      this.orderPillarGroup = null;
    }
  }

  /**
   * 智能驾驶舱同源落点：lng/lat 已由后端 geocode；与模板 createBar 一致：Box+渐变+辉光+底部波纹圈
   * @param {Array<{address:string,customer_name?:string,order_count?:number,gmv?:number,lng:number,lat:number,member_id?:number}>} points
   */
  setOrderPillars(points) {
    this._clearOrderPillars();
    // 模板 createFocus 落在 flyLineCenter（近东城）；订单模式以真实地址柱为准，避免与「城市中心 demo 光圈」混淆
    if (this._cityFocusMarker) this._cityFocusMarker.visible = false;
    const raw = Array.isArray(points) ? points : [];
    // 业务约束：不再前置注入硬编码"监管指挥中心"——数据库无该坐标。
    // 金光柱（高大金色）= 后端返回的真实 delivery 点位本身。
    const filtered = raw.filter((p) => {
      return Boolean(this._safeGeoProject(p.lng, p.lat));
    });
    const merged = filtered;

    this._useOrderPillars = true;
    this._setDemoMapDecorVisible(false);

    const factor = 0.7;
    const heightBase = 4.0 * factor;
    const counts = filtered.map((p) => Number(p.order_count) || 0);
    const maxC = Math.max(1, ...counts);

    const barGroup = new Group();
    barGroup.rotation.x = -Math.PI / 2;
    this.orderPillarGroup = barGroup;
    this.scene.add(barGroup);

    let pillarIdx = 0;
    for (const item of merged) {
      const lng = Number(item.lng);
      const lat = Number(item.lat);
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
      const roleLc = typeof item.role === "string" ? item.role.toLowerCase() : "";
      const isDelivery = roleLc === "delivery";
      const isRisk = roleLc === "risk";
      const isFulfillment = roleLc === "fulfillment";
      const isColdChain = roleLc === "cold_chain";
      const isIndustry = roleLc === "industry";
      const isCityProfile = roleLc === "city_profile";
      const riskLevel = String(item.risk_level || "").toLowerCase();
      const isHighRisk = isRisk && (riskLevel === "high" || riskLevel === "高");
      const fulfillmentStage = String(item.stage || "").toLowerCase();
      const isFulfillmentBlocked = isFulfillment && fulfillmentStage === "blocked";
      const isFulfillmentTransit = isFulfillment && fulfillmentStage === "in_transit";
      const coldStage = String(item.stage || "").toLowerCase();
      const isColdAlert = isColdChain && coldStage === "alert";
      const isColdWarehouse = isColdChain && String(item.cold_type || "").toLowerCase() === "warehouse";
      const isIndustryVolatile = isIndustry && String(item.stage || "").toLowerCase() === "volatile";
      const isCityRisk = isCityProfile && String(item.stage || "").toLowerCase() === "risk";
      const isCityThin = isCityProfile && String(item.stage || "").toLowerCase() === "thin";
      const oc = Number(item.order_count) || 0;
      // 配送商（金光柱）直接复用原"总部"高大柱视觉：高度/粗细/颜色/光晕/焦点环全部对齐
      const geoHeight = isDelivery
        ? heightBase * 0.94
        : isRisk
          ? heightBase * (isHighRisk ? 1.08 : 0.82)
        : isFulfillment
          ? heightBase * (isFulfillmentBlocked ? 0.96 : isFulfillmentTransit ? 0.86 : 0.72)
        : isColdChain
          ? heightBase * (isColdAlert ? 1.02 : isColdWarehouse ? 0.68 : 0.9)
        : isIndustry
          ? heightBase * (isIndustryVolatile ? 1.02 : 0.76)
        : isCityProfile
          ? heightBase * (isCityRisk ? 0.96 : isCityThin ? 0.68 : 0.82)
        : Math.max(
            0.38 * factor,
            heightBase * (0.12 + (0.88 * oc) / maxC),
          );

      const material = new MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 1,
        depthTest: false,
        fog: false,
      });
      // delivery=金（用原总部那套橙金渐变），client=蓝
      new GradientShader(material, {
        uColor1: isRisk
          ? (isHighRisk ? 0xff2d2d : 0xff7a1a)
          : isFulfillment
            ? (isFulfillmentBlocked ? 0xf59e0b : isFulfillmentTransit ? 0x22d3ee : 0x38bdf8)
            : isColdChain
              ? (isColdAlert ? 0x7c3aed : isColdWarehouse ? 0x7dd3fc : 0xa7f3ff)
            : isIndustry
              ? (isIndustryVolatile ? 0xfacc15 : 0xa855f7)
            : isCityProfile
              ? (isCityRisk ? 0xf97316 : isCityThin ? 0xfbbf24 : 0x22d3ee)
            : isDelivery ? 0xff9f43 : 0x50bbfe,
        uColor2: isRisk
          ? (isHighRisk ? 0xfff1b8 : 0xffd56a)
          : isFulfillment
            ? (isFulfillmentBlocked ? 0xfff0b8 : 0xc8ffff)
            : isColdChain
              ? (isColdAlert ? 0xfbcfe8 : 0xffffff)
            : isIndustry
              ? (isIndustryVolatile ? 0x67e8f9 : 0xf0abfc)
            : isCityProfile
              ? (isCityRisk ? 0xffedd5 : 0xcffafe)
            : isDelivery ? 0xfff8e8 : 0x77fbf5,
        size: geoHeight,
        dir: "y",
      });
      const thick = isRisk
        ? (isHighRisk ? 2.15 : 1.65)
        : isFulfillment
          ? (isFulfillmentBlocked ? 1.95 : 1.45)
          : isColdChain
            ? (isColdAlert ? 2.05 : isColdWarehouse ? 1.35 : 1.7)
          : isIndustry
            ? (isIndustryVolatile ? 1.9 : 1.45)
          : isCityProfile
            ? (isCityRisk ? 1.85 : isCityThin ? 1.25 : 1.55)
          : isDelivery ? 2.35 : 1;
      const geo = new BoxGeometry(
        0.1 * factor * thick,
        0.1 * factor * thick,
        geoHeight,
      );
      geo.translate(0, 0, geoHeight / 2);
      const mesh = new Mesh(geo, material);
      mesh.renderOrder = isDelivery ? 6 : 5;
      const projected = this._safeGeoProject(lng, lat);
      if (!projected) continue;
      const [x, y] = projected;
      mesh.position.set(x, -y, this.depth + 0.45);
      const hg = this.createHUIGUANG(
        geoHeight,
        isRisk
          ? (isHighRisk ? 0xff5b3a : 0xff9c38)
          : isFulfillment
            ? (isFulfillmentBlocked ? 0xffc45a : 0x67e8f9)
            : isColdChain
              ? (isColdAlert ? 0xf0abfc : 0xcffafe)
            : isIndustry
              ? (isIndustryVolatile ? 0xfde68a : 0xd8b4fe)
            : isCityProfile
              ? (isCityRisk ? 0xf97316 : 0x67e8f9)
            : isDelivery ? 0xffe2b0 : 0x77fbf5,
      );
      mesh.add(...hg);
      const hNorm = (geoHeight - 0.38 * factor) / (heightBase - 0.38 * factor + 1e-6);
      this._createOrderFocusMarker(
        x,
        y,
        pillarIdx,
        hNorm,
        isRisk
          ? { color1: isHighRisk ? 0xff4d2e : 0xff8a2a, color2: isHighRisk ? 0xffe0a3 : 0xffcc66 }
          : isFulfillment
            ? { color1: isFulfillmentBlocked ? 0xf59e0b : 0x22d3ee, color2: isFulfillmentBlocked ? 0xfff0b8 : 0xc8ffff }
          : isColdChain
            ? { color1: isColdAlert ? 0xc084fc : 0x67e8f9, color2: isColdAlert ? 0xfbcfe8 : 0xffffff }
          : isIndustry
            ? { color1: isIndustryVolatile ? 0xfacc15 : 0xa855f7, color2: isIndustryVolatile ? 0x67e8f9 : 0xf0abfc }
          : isCityProfile
            ? { color1: isCityRisk ? 0xf97316 : 0x22d3ee, color2: isCityRisk ? 0xffedd5 : 0xcffafe }
          : isDelivery
            ? { color1: 0xffcc66, color2: 0xffeecc }
            : null,
      );
      // 保底：scale=1 + material.opacity=1 立刻可见，不依赖 GSAP tween
      mesh.scale.set(1, 1, 1);
      pillarIdx += 1;
      mesh.userData = {
        orderPillar: true,
        role: roleLc || "client",
        risk_type: item.risk_type,
        risk_level: item.risk_level,
        stage: item.stage,
        cold_type: item.cold_type,
        industry_type: item.industry_type,
        product_name: item.product_name,
        category_name: item.category_name,
        change_pct: item.change_pct,
        forecast_price: item.forecast_price,
        confidence: item.confidence,
        profile_type: item.profile_type,
        district_name: item.district_name,
        client_count: item.client_count,
        canteen_count: item.canteen_count,
        risk_count: item.risk_count,
        vehicle_id: item.vehicle_id,
        warehouse_id: item.warehouse_id,
        temperature: item.temperature,
        humidity: item.humidity,
        trip_id: item.trip_id,
        route_no: item.route_no,
        status: item.status,
        description: item.description,
        order_sn: item.order_sn,
        order_id: item.order_id,
        _mockId: typeof item._mockId === "string" ? item._mockId : null,
        address: String(item.address || "").trim(),
        customer_name: item.customer_name,
        order_count: oc,
        gmv: Number(item.gmv) || 0,
        member_id: item.member_id,
        member_key: item.member_key,
        _pillarH: geoHeight,
        _px: x,
        _py: y,
      };
      barGroup.add(mesh);
      this.interactionManager.add(mesh);
      this._orderPillarInteractives.push(mesh);

      mesh.addEventListener("mouseover", () => {
        document.body.style.cursor = "pointer";
        this._showOrderPillarHover(mesh.userData);
      });
      mesh.addEventListener("mouseout", () => {
        document.body.style.cursor = "default";
        this._clearOrderPillarHoverPanel();
      });
      mesh.addEventListener("mousedown", (ev) => {
        if (this._shouldIgnorePillarClickForMapTop(ev, mesh)) return;
        const u = mesh.userData;
        emitter.$emit("tianshuOrderPillarClick", {
          role: u.role,
          risk_type: u.risk_type,
          risk_level: u.risk_level,
          stage: u.stage,
          cold_type: u.cold_type,
          industry_type: u.industry_type,
          product_name: u.product_name,
          category_name: u.category_name,
          change_pct: u.change_pct,
          forecast_price: u.forecast_price,
          confidence: u.confidence,
          profile_type: u.profile_type,
          district_name: u.district_name,
          client_count: u.client_count,
          canteen_count: u.canteen_count,
          risk_count: u.risk_count,
          vehicle_id: u.vehicle_id,
          warehouse_id: u.warehouse_id,
          temperature: u.temperature,
          humidity: u.humidity,
          trip_id: u.trip_id,
          route_no: u.route_no,
          status: u.status,
          description: u.description,
          order_sn: u.order_sn,
          order_id: u.order_id,
          _mockId: u._mockId,
          address: u.address,
          customer_name: u.customer_name,
          order_count: u.order_count,
          gmv: u.gmv,
          member_id: u.member_id,
          member_key: u.member_key,
        });
      });
    }

    // 飞线由 index.vue loadFlylines() 调用 setFlylines() 注入（业务语义：配送商→客户）
  }

  createStorke() {
    const mapStroke = this.getFocusMapStrokeGeoJsonString();
    const texture = this.assets.instance.getResource("pathLine3");
    texture.wrapS = texture.wrapT = RepeatWrapping;
    texture.repeat.set(2, 1);

    let pathLine = new Line(this, {
      geoProjectionCenter: this.geoProjectionCenter,
      geoProjectionScale: this.geoProjectionScale,
      position: new Vector3(0, 0, this.depth + 0.24),
      data: mapStroke,
      material: new MeshBasicMaterial({
        color: 0x4a9eb5,
        map: texture,
        alphaMap: texture,
        fog: false,
        transparent: true,
        opacity: 0.82,
        blending: AdditiveBlending,
      }),
      type: "Line3",
      renderOrder: 22,
      tubeRadius: 0.011,
    });
    // 设置父级
    this.focusMapGroup.add(pathLine.lineGroup);
    this.time.on("tick", () => {
      texture.offset.x += 0.005;
    });
  }

  geoProjection(args) {
    if (!Array.isArray(args) || args.length < 2) return [0, 0];
    const lng = Number(args[0]);
    const lat = Number(args[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return [0, 0];
    const projected = this.getGeoMercator()([lng, lat]);
    if (!Array.isArray(projected) || projected.length < 2) return [0, 0];
    const x = Number(projected[0]);
    const y = Number(projected[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return [0, 0];
    return [x, y];
  }

  /** 与挤出/顶面一致的 d3 投影实例（供卫星包络反算） */
  getGeoMercator() {
    if (!this._geoMercatorInstance) {
      this._geoMercatorInstance = geoMercator()
        .center(this.geoProjectionCenter)
        .scale(this.geoProjectionScale)
        .translate([0, 0]);
    }
    return this._geoMercatorInstance;
  }

  _applyExtrudeScaleForDepth() {
    if (!this._extrudeMapInstance?.mapGroup || !this._extrudeGeometryDepth) return;
    const ratio = this.depth / this._extrudeGeometryDepth;
    this._extrudeMapInstance.mapGroup.scale.set(1, 1, Math.max(0.08, ratio));
  }

  _syncDependentZFromDepth() {
    const d = this.depth;
    const v = this.mapVisual;
    if (this._mapTopBaseMap?.mapGroup) {
      this._mapTopBaseMap.mapGroup.position.z = d + v.mapTopZOffset;
    }
    if (this._districtLineInstance?.lineGroup) {
      this._districtLineInstance.lineGroup.position.z =
        d + v.districtLineZOffset;
    }
    if (this._districtSprites?.length) {
      for (const s of this._districtSprites) {
        s.position.z = d + v.districtLabelZOffset;
      }
    }
    if (this.allBar?.length) {
      for (const bar of this.allBar) {
        bar.position.z = d + 0.45;
      }
    }
    if (this.allGuangquan?.length) {
      for (const g of this.allGuangquan) {
        g.position.y = d + 0.44;
      }
    }
    for (const m of this._orderPillarInteractives || []) {
      m.position.z = d + 0.45;
    }
    for (const f of this._orderFocusMarkers || []) {
      f.position.z = d + 0.44;
    }
    if (this._cityFocusMarker) {
      this._cityFocusMarker.position.z = d + 0.44;
    }
  }

  /**
   * 调试面板：合并参数、可选写入 localStorage，并刷新场景。
   * @param {Partial<typeof MAP_VISUAL_DEFAULTS>} patch
   */
  applyMapVisualPatch(patch, { persist = true } = {}) {
    Object.assign(this.mapVisual, patch);
    if (patch.extrudeDepth != null) {
      this.depth = this.mapVisual.extrudeDepth;
    }
    if (persist) saveMapVisualSnapshot(this.mapVisual);
    this._refreshMapVisualInScene();
  }

  getMapVisualSnapshot() {
    return JSON.parse(
      JSON.stringify({
        ...this.mapVisual,
        extrudeTopRgbBoost: [...this.mapVisual.extrudeTopRgbBoost],
        extrudeSideRgbBoost: [...this.mapVisual.extrudeSideRgbBoost],
      }),
    );
  }

  _refreshMapVisualInScene() {
    const v = this.mapVisual;
    if (this.scene.fog) {
      this.scene.fog.color.setHex(v.atmosphereColor);
      this.scene.fog.near = v.fogNear;
      this.scene.fog.far = v.fogFar;
    }
    if (this.scene.background instanceof Color) {
      this.scene.background.setHex(v.atmosphereColor);
    }

    if (this._ambientLight) {
      this._ambientLight.color.setHex(v.ambientColor);
      this._ambientLight.intensity = v.ambientIntensity;
    }
    if (this._hemiLight) {
      this._hemiLight.color.setHex(v.hemiSky);
      this._hemiLight.groundColor.setHex(v.hemiGround);
      this._hemiLight.intensity = v.hemiIntensity;
    }
    if (this._dirKey) {
      this._dirKey.color.setHex(v.dirKeyColor);
      this._dirKey.intensity = v.dirKeyIntensity;
    }
    if (this._dirFill) {
      this._dirFill.color.setHex(v.dirFillColor);
      this._dirFill.intensity = v.dirFillIntensity;
    }
    if (this._dirRim) {
      this._dirRim.color.setHex(v.dirRimColor);
      this._dirRim.intensity = v.dirRimIntensity;
    }
    const pc = new Color(v.pointColor);
    const ph = pc.getHex();
    if (this._visualPointLights[0]) {
      this._visualPointLights[0].color.setHex(ph);
      this._visualPointLights[0].intensity = v.pointIntensity0;
    }
    if (this._visualPointLights[1]) {
      this._visualPointLights[1].color.setHex(ph);
      this._visualPointLights[1].intensity = v.pointIntensity1;
    }

    if (this._chinaBgMaterial) {
      this._chinaBgMaterial.color.set(v.chinaBg);
      this._chinaBgMaterial.opacity = v.chinaBgOpacity;
      this._chinaBgMaterial.needsUpdate = true;
    }
    if (this._chinaLineMaterial) {
      this._chinaLineMaterial.color.set(v.chinaLine);
    }

    if (this._extrudeTopShaderUniforms) {
      this._extrudeTopShaderUniforms.uColor1.value.setHex(v.extrudeTopTint);
      this._extrudeTopShaderUniforms.uTopAlpha.value = v.extrudeTopAlpha;
      const tb = v.extrudeTopRgbBoost;
      this._extrudeTopShaderUniforms.uTopRgbBoost.value.set(
        tb[0],
        tb[1],
        tb[2],
      );
    }
    if (this._extrudeSideShaderUniforms) {
      this._extrudeSideShaderUniforms.uColor1.value.setHex(v.extrudeSide1);
      this._extrudeSideShaderUniforms.uColor2.value.setHex(v.extrudeSide2);
      this._extrudeSideShaderUniforms.uSideZDiv.value = v.extrudeSideZDiv;
      const sb = v.extrudeSideRgbBoost;
      this._extrudeSideShaderUniforms.uSideRgbBoost.value.set(
        sb[0],
        sb[1],
        sb[2],
      );
    }

    const gShader = this._mapTopFaceGradient?.shader;
    if (gShader?.uniforms?.uColor1) {
      gShader.uniforms.uColor1.value.setHex(v.mapTopGradient1);
      gShader.uniforms.uColor2.value.setHex(v.mapTopGradient2);
      gShader.uniforms.uSize.value = v.mapTopGradientSize;
    }
    if (this.defaultMaterial) {
      this.defaultMaterial.opacity = v.mapTopOpacity;
      this.defaultMaterial.needsUpdate = true;
    }
    if (this.defaultLightMaterial) {
      this.defaultLightMaterial.color.setHex(v.mapHoverTint);
      this.defaultLightMaterial.opacity = v.mapHoverOpacity;
    }

    if (this.mapLineMaterial) {
      this.mapLineMaterial.color.setHex(v.districtLineColor);
      this.mapLineMaterial.linewidth = v.districtLineWidth;
      this.mapLineMaterial.opacity = v.districtLineOpacity;
    }

    this._applyExtrudeScaleForDepth();
    this._syncDependentZFromDepth();
  }

  resize() {
    super.resize();
    if (this.mapLineMaterial?.resolution) {
      this.mapLineMaterial.resolution.set(this.sizes.width, this.sizes.height);
    }
  }

  /** 开发调试用：暂停开场时间线并跳到最后一帧，便于 Orbit 调整视角 */
  setCameraDebugMode(on) {
    this._cameraDebugMode = Boolean(on);
    if (on) {
      if (this.animateTl) {
        this.animateTl.pause();
        this.animateTl.progress(1);
      }
      this._cityViewReady = true;
      this.camera.controls.enabled = true;
      this.camera.controls.enableDamping = true;
    }
  }

  /** 便于截图/粘贴回 map.js 的相机参数文本 */
  getCameraParamsText() {
    const cam = this.camera.instance;
    const t = this.camera.controls.target;
    const r = (n) => (Number.isFinite(n) ? Number(n.toFixed(4)) : n);
    return [
      "// 将下列数值贴回 map.js：",
      `this.camera.instance.position.set(${r(cam.position.x)}, ${r(cam.position.y)}, ${r(cam.position.z)});`,
      `this.camera.controls.target.set(${r(t.x)}, ${r(t.y)}, ${r(t.z)});`,
      `this.camera.instance.fov = ${r(cam.fov)};`,
      "// gsap 落点（若仍用动画收尾，与 position 保持一致）：",
      `// x: ${r(cam.position.x)}, y: ${r(cam.position.y)}, z: ${r(cam.position.z)}`,
    ].join("\n");
  }

  update() {
    super.update();
    this.interactionManager && this.interactionManager.update();
  }
  destroy() {
    this._drillTween?.kill();
    this._drillTween = null;
    this._satelliteLoadAbort?.abort();
    this._satelliteLoadAbort = null;
    if (this._satelliteState.map) {
      this._satelliteState.map.dispose();
      this._satelliteState.map = null;
    }
    this._clearOrderPillars();
    this._clearDistrictSprites();
    super.destroy();
    this.label3d && this.label3d.destroy();
  }
}
