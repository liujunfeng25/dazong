import { Resource } from "@/mini3d"
import { FileLoader } from "three"

import pathLine3 from "@/assets/texture/pathLine2.png"

import side from "@/assets/texture/side.png"
import ocean from "@/assets/texture/ocean-bg.png"
import rotationBorder1 from "@/assets/texture/rotationBorder1.png"
import rotationBorder2 from "@/assets/texture/rotationBorder2.png"
import chinaBlurLine from "@/assets/texture/chinaBlurLine.png"
import guangquan1 from "@/assets/texture/guangquan01.png"
import guangquan2 from "@/assets/texture/guangquan02.png"
import huiguang from "@/assets/texture/huiguang.png"
import arrow from "@/assets/texture/arrow.png"
import point from "@/assets/texture/point1.png"
import mapFlyline from "@/assets/texture/flyline6.png"
// 焦点贴图
import focusArrowsTexture from "@/assets/texture/focus/focus_arrows.png"
import focusBarTexture from "@/assets/texture/focus/focus_bar.png"
import focusBgTexture from "@/assets/texture/focus/focus_bg.png"
import focusMidQuanTexture from "@/assets/texture/focus/focus_mid_quan.png"
import focusMoveBgTexture from "@/assets/texture/focus/focus_move_bg.png"
export class Assets {
  constructor() {
    this.instance = new Resource()
    this.instance.addLoader(FileLoader, "FileLoader")
  }

  /** 资源清单（在注册 onProgress/onLoad 之后再调用 loadAll，避免缓存极快时错过 onLoad） */
  getAssetList() {
    let base_url = import.meta.env.BASE_URL
    return [
      { type: "Texture", name: "pathLine3", path: pathLine3 },

      {
        type: "File",
        name: "china",
        path: base_url + "assets/json/中华人民共和国.json",
      },

      {
        type: "File",
        name: "mapJson",
        path: base_url + "assets/json/北京市.json",
      },
      {
        type: "File",
        name: "mapStroke",
        path: base_url + "assets/json/北京市-轮廓.json",
      },
      {
        type: "File",
        name: "xiongAnMapJson",
        path: base_url + "assets/json/雄安新区.json",
      },

      { type: "Texture", name: "huiguang", path: huiguang },
      { type: "Texture", name: "rotationBorder1", path: rotationBorder1 },
      { type: "Texture", name: "rotationBorder2", path: rotationBorder2 },
      { type: "Texture", name: "guangquan1", path: guangquan1 },
      { type: "Texture", name: "guangquan2", path: guangquan2 },
      { type: "Texture", name: "chinaBlurLine", path: chinaBlurLine },
      { type: "Texture", name: "ocean", path: ocean },
      { type: "Texture", name: "side", path: side },
      { type: "Texture", name: "mapFlyline", path: mapFlyline },
      { type: "Texture", name: "arrow", path: arrow },
      { type: "Texture", name: "point", path: point },

      { type: "Texture", name: "focusArrows", path: focusArrowsTexture },
      { type: "Texture", name: "focusBar", path: focusBarTexture },
      { type: "Texture", name: "focusBg", path: focusBgTexture },
      { type: "Texture", name: "focusMidQuan", path: focusMidQuanTexture },
      { type: "Texture", name: "focusMoveBg", path: focusMoveBgTexture },
    ]
  }

  startLoad() {
    return this.instance.loadAll(this.getAssetList())
  }
}
