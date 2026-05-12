import { Color } from "three"

export class GradientShader {
  constructor(material, config) {
    this.shader = null
    this.config = Object.assign(
      {
        uColor1: 0x2a6f72,
        uColor2: 0x0d2025,
        size: 15.0,
        dir: "x", // 'x ,y,z'
        /** @type {{ bounds: import("three").Vector4, map: import("three").Texture, weight: { value: number } } | null} */
        satellite: null,
      },
      config,
    )
    this.init(material)
  }
  init(material) {
    let { uColor1, uColor2, dir, size, satellite } = this.config
    let dirMap = { x: 1.0, y: 2.0, z: 3.0 }
    const hasSat = Boolean(
      satellite?.bounds &&
        satellite?.map &&
        satellite?.weight &&
        typeof satellite.weight.value === "number",
    )

    material.onBeforeCompile = (shader) => {
      this.shader = shader

      const baseUniforms = {
        ...shader.uniforms,
        uColor1: { value: new Color(uColor1) },
        uColor2: { value: new Color(uColor2) },
        uDir: { value: dirMap[dir] },
        uSize: { value: size },
      }
      if (hasSat) {
        baseUniforms.uSatelliteB = { value: satellite.bounds }
        baseUniforms.uSatelliteMap = { value: satellite.map }
        baseUniforms.uSatelliteWeight = satellite.weight
      }
      shader.uniforms = baseUniforms

      const vertHead = hasSat
        ? `
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
              `
        : `
                attribute float alpha;
                varying vec3 vPosition;
                varying float vAlpha;
                void main() {
                  vAlpha = alpha;
                  vPosition = position;
              `

      const fragHead = hasSat
        ? `
                varying vec3 vPosition;
                varying float vAlpha;
                varying vec2 vSatUv;
                uniform vec3 uColor1;
                uniform vec3 uColor2;
                uniform float uDir;
                uniform float uSize;
                uniform sampler2D uSatelliteMap;
                uniform float uSatelliteWeight;
                void main() {
              `
        : `
                varying vec3 vPosition;
                varying float vAlpha;
                uniform vec3 uColor1;
                uniform vec3 uColor2;
                uniform float uDir;
                uniform float uSize;
              
                void main() {
              `

      const fragTail = hasSat
        ? `
              vec3 gradient = vec3(0.0,0.0,0.0);
              if(uDir==1.0){
                gradient = mix(uColor1, uColor2, vPosition.x/ uSize); 
              }else if(uDir==2.0){
                gradient = mix(uColor1, uColor2, vPosition.z/ uSize); 
              }else if(uDir==3.0){
                gradient = mix(uColor1, uColor2, vPosition.y/ uSize); 
              }
              vec3 lit = outgoingLight * gradient;
              vec2 suv = clamp(vSatUv, vec2(0.002), vec2(0.998));
              vec4 satC = texture2D( uSatelliteMap, vec2(suv.x, 1.0 - suv.y) );
              vec4 satX = texture2D( uSatelliteMap, vec2(suv.x + 0.0028, 1.0 - suv.y) );
              vec4 satY = texture2D( uSatelliteMap, vec2(suv.x, 1.0 - (suv.y + 0.0028)) );
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
              vec3 withRelief = lit * shade * ridge * tone + bump;
              outgoingLight = mix(lit, withRelief, uSatelliteWeight);
              gl_FragColor = vec4( outgoingLight, diffuseColor.a  );
              `
        : `
              vec3 gradient = vec3(0.0,0.0,0.0);
              if(uDir==1.0){
                gradient = mix(uColor1, uColor2, vPosition.x/ uSize); 
              }else if(uDir==2.0){
                gradient = mix(uColor1, uColor2, vPosition.z/ uSize); 
              }else if(uDir==3.0){
                gradient = mix(uColor1, uColor2, vPosition.y/ uSize); 
              }
              outgoingLight = outgoingLight * gradient;
              
              
              gl_FragColor = vec4( outgoingLight, diffuseColor.a  );
              `

      shader.vertexShader = shader.vertexShader.replace(
        "void main() {",
        vertHead,
      )
      shader.fragmentShader = shader.fragmentShader.replace(
        "void main() {",
        fragHead,
      )
      shader.fragmentShader = shader.fragmentShader.replace(
        "#include <opaque_fragment>",
        /* glsl */ `
              #ifdef OPAQUE
              diffuseColor.a = 1.0;
              #endif
              
              // https://github.com/mrdoob/three.js/pull/22425
              #ifdef USE_TRANSMISSION
              diffuseColor.a *= transmissionAlpha + 0.1;
              #endif
              ${fragTail}
              `,
      )
    }
  }
}
