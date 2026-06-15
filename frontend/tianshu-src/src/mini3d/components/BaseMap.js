import {
  Mesh,
  Vector2,
  Color,
  Group,
  Object3D,
  BufferAttribute,
  Shape,
  ExtrudeGeometry,
  MeshBasicMaterial,
  DoubleSide,
  ShapeGeometry,
  Vector3,
} from "three"
import { transfromMapGeoJSON, getBoundBox } from "@/mini3d"
import { geoMercator } from "d3-geo"
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils"
export class BaseMap {
  constructor({}, config = {}) {
    this.mapGroup = new Group()
    this.coordinates = []
    this.config = Object.assign(
      {
        position: new Vector3(0, 0, 0),
        geoProjectionCenter: new Vector2(0, 0),
        geoProjectionScale: 120,
        data: "",
        renderOrder: 1,
        merge: false,
        material: new MeshBasicMaterial({
          color: 0x18263b,
          transparent: true,
          opacity: 1,
        }),
      },
      config
    )
    this.mapGroup.position.copy(this.config.position)
    let mapData = transfromMapGeoJSON(this.config.data)
    this.create(mapData)
  }
  geoProjection(args) {
    if (!Array.isArray(args) || args.length < 2) return null
    const lng = Number(args[0])
    const lat = Number(args[1])
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
    const p = geoMercator()
      .center(this.config.geoProjectionCenter)
      .scale(this.config.geoProjectionScale)
      .translate([0, 0])([lng, lat])
    if (!Array.isArray(p) || p.length < 2) return null
    const x = Number(p[0])
    const y = Number(p[1])
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null
    return [x, y]
  }
  create(mapData) {
    let { merge } = this.config
    let shapes = []
    mapData.features.forEach((feature) => {
      const group = new Object3D()

      let { name, center = [], centroid = [] } = feature.properties
      this.coordinates.push({ name, center, centroid })
      group.userData.name = name
      feature.geometry.coordinates.forEach((multiPolygon) => {
        multiPolygon.forEach((polygon) => {
          const shape = new Shape()
          for (let i = 0; i < polygon.length; i++) {
            if (!polygon[i][0] || !polygon[i][1]) {
              return false
            }
            const projected = this.geoProjection(polygon[i])
            if (!projected) continue
            const [x, y] = projected
            if (i === 0) {
              shape.moveTo(x, -y)
            }
            shape.lineTo(x, -y)
          }

          const geometry = new ShapeGeometry(shape)
          if (merge) {
            shapes.push(geometry)
          } else {
            const mesh = new Mesh(geometry, this.config.material)
            mesh.renderOrder = this.config.renderOrder
            mesh.userData.name = name
            group.add(mesh)
          }
        })
      })
      if (!merge) {
        this.mapGroup.add(group)
      }
    })
    if (merge) {
      let geometry = mergeGeometries(shapes)
      const mesh = new Mesh(geometry, this.config.material)
      mesh.renderOrder = this.config.renderOrder
      this.mapGroup.add(mesh)
    }
  }

  getCoordinates() {
    return this.coordinates
  }
  setParent(parent) {
    parent.add(this.mapGroup)
  }
}
