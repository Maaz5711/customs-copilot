import {
  BoxGeometry, BufferGeometry, CanvasTexture, Color, DoubleSide, EdgesGeometry, Float32BufferAttribute, Fog, Group, LineBasicMaterial, LineSegments,
  Material, MathUtils, Mesh, MeshBasicMaterial, Object3D, PerspectiveCamera, PlaneGeometry, Points, PointsMaterial, Scene, ShaderMaterial,
  SRGBColorSpace, Texture, Vector3, WebGLRenderer,
} from "three";
import { EXAMPLE, ramp } from "./chapters";

// A customs gate, drawn in code (no downloaded models). One abstract crate arrives, is scanned and coded, a stack of duty layers rises above it,
// source sheets fan out, the gate light turns amber when the tool is unsure and green when it is done. Everything is driven by one number: scroll progress 0..1.
// No trucks, ships or maps on purpose: this is about a decision and its paperwork, not about moving goods. On the home page it is drawn as a see-through
// wireframe over the port photos (the canvas is transparent and blended with "screen").

type Tokens = { dark: boolean; ink: string; blue: string; gold: string; ok: string; warn: string; bg: string; surface: string };

// Colours come from the element's CSS tokens (the story section sets its own dark set and --is-dark: 1).
const readTokens = (el: Element): Tokens => {
  const cs = getComputedStyle(el);
  const v = (n: string, d: string) => cs.getPropertyValue(n).trim() || d;
  const t = document.documentElement.dataset.theme;
  const dark = cs.getPropertyValue("--is-dark").trim() === "1" || t === "dark" || (t !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return { dark, ink: v("--ink", "#0b1324"), blue: v("--blue", "#1e3a8a"), gold: v("--gold", "#8a5a05"), ok: v("--ok", "#17663b"), warn: v("--warn", "#8a4b00"), bg: v("--bg", "#f6f8fb"), surface: v("--surface", "#ffffff") };
};

const SLAB_LIGHT = ["#1e3a8a", "#4663b8", "#7b8aa3", "#8a5a05", "#b9801f", "#0f172a"];
const SLAB_DARK = ["#8fb0ff", "#6f8fe0", "#9fb0c9", "#e2ae45", "#c99532", "#e7edf8"];

type Key = { p: number; pos: [number, number, number]; look: [number, number, number] };
const CAMERA: Key[] = [
  { p: 0, pos: [0, 2.6, 12.5], look: [0, 1.8, -8] },
  { p: 0.14, pos: [1.2, 2.4, 9.5], look: [0, 1.8, -2] },
  { p: 0.3, pos: [-2.2, 2.6, 8.2], look: [0, 2.0, -0.4] },
  { p: 0.52, pos: [2.6, 3.6, 8.6], look: [0, 3.4, -0.4] },
  { p: 0.68, pos: [0, 3.4, 8.4], look: [0, 2.8, -0.4] },
  { p: 0.82, pos: [-1.6, 2.8, 8.8], look: [0, 2.4, -0.4] },
  { p: 1, pos: [0, 2.4, 13.5], look: [0, 2.0, 2] },
];

const lerp = MathUtils.lerp;
const bump = (p: number, a: number, b: number, c: number, d: number) => ramp(p, a, b) * (1 - ramp(p, c, d));

function drawTexture(w: number, h: number, draw: (ctx: CanvasRenderingContext2D) => void): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  const ctx = c.getContext("2d")!;
  draw(ctx);
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

const FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';

function wrap(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, maxW: number, lh: number) {
  const words = text.split(" ");
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width > maxW && line) { ctx.fillText(line, x, y); line = w; y += lh; } else line = test;
  }
  ctx.fillText(line, x, y);
}

export class GateScene {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(38, 1, 0.1, 80);
  private world = new Group();
  private textures: Texture[] = [];
  private target = 0;
  private cur = 0;
  private last = 0;
  private running = false;
  private visible = false;
  private t0 = performance.now();
  private w = 1; private h = 1;
  private t!: Tokens;
  onLost?: () => void;

  // parts
  private crate = new Group();
  private crateFill!: Mesh;
  private crateEdges!: LineSegments;
  private label!: Mesh;
  private labelA!: Texture; private labelB!: Texture;
  private beam!: Mesh;
  private beamMat!: ShaderMaterial;
  private light!: Mesh;
  private lightMat!: MeshBasicMaterial;
  private barrier = new Group();
  private slabs: { mesh: Mesh; edges: LineSegments; h: number; y: number }[] = [];
  private papers: Mesh[] = [];
  private tags: Mesh[] = [];
  private dust!: Points;

  static supported(): boolean {
    try {
      const c = document.createElement("canvas");
      return !!(c.getContext("webgl2") || c.getContext("webgl"));
    } catch {
      return false;
    }
  }

  constructor(private canvas: HTMLCanvasElement) {
    const small = window.innerWidth < 760;
    this.renderer = new WebGLRenderer({ canvas, antialias: !small, alpha: true, powerPreference: "default" });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2));
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.stop(); this.onLost?.(); });
    this.scene.add(this.world);
    this.build();
  }

  // ------------------------------------------------------------------------------------------------ building
  private tex(t: CanvasTexture) { this.textures.push(t); return t; }

  private edgeBox(w: number, h: number, d: number, color: string, fill: number, line = 0.9) {
    const g = new BoxGeometry(w, h, d);
    const grp = new Group();
    const mesh = new Mesh(g, new MeshBasicMaterial({ color: new Color(color), transparent: true, opacity: fill, depthWrite: false }));
    const edges = new LineSegments(new EdgesGeometry(g), new LineBasicMaterial({ color: new Color(color), transparent: true, opacity: line }));
    grp.add(mesh, edges);
    return { grp, mesh, edges };
  }

  private build() {
    this.t = readTokens(this.canvas);
    const T = this.t;
    this.scene.fog = new Fog(new Color(T.bg), 14, 46);

    // floor grid: lines receding toward the gate
    const pts: number[] = [];
    for (let x = -16; x <= 16; x += 2) pts.push(x, 0, -44, x, 0, 14);
    for (let z = -44; z <= 14; z += 2) pts.push(-16, 0, z, 16, 0, z);
    const gg = new BufferGeometry();
    gg.setAttribute("position", new Float32BufferAttribute(pts, 3));
    this.world.add(new LineSegments(gg, new LineBasicMaterial({ color: new Color(T.blue), transparent: true, opacity: T.dark ? 0.12 : 0.16 })));

    // gate: two pylons, a lintel, a light, a barrier arm
    const gate = new Group();
    for (const sx of [-1, 1]) {
      const p = this.edgeBox(0.5, 3.7, 0.8, T.blue, T.dark ? 0.1 : 0.08);
      p.grp.position.set(sx * 2.9, 1.85, 0);
      gate.add(p.grp);
    }
    const lintel = this.edgeBox(6.3, 0.55, 0.8, T.blue, T.dark ? 0.1 : 0.08);
    lintel.grp.position.set(0, 3.95, 0);
    gate.add(lintel.grp);
    this.lightMat = new MeshBasicMaterial({ color: new Color(T.blue) });
    this.light = new Mesh(new BoxGeometry(0.7, 0.2, 0.2), this.lightMat);
    this.light.position.set(0, 3.95, 0.45);
    gate.add(this.light);
    this.barrier.position.set(-2.65, 1.15, 0.1);
    const arm = this.edgeBox(5.3, 0.14, 0.14, T.gold, 0.5, 1);
    arm.grp.position.set(2.65, 0, 0);
    this.barrier.add(arm.grp);
    gate.add(this.barrier);
    this.world.add(gate);

    // scan beam: a plane with a bright band that sweeps up the crate
    this.beamMat = new ShaderMaterial({
      transparent: true, depthWrite: false, side: DoubleSide,
      uniforms: { uY: { value: 0 }, uA: { value: 0 }, uC: { value: new Color(T.dark ? T.blue : T.blue) } },
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
      fragmentShader: "varying vec2 vUv; uniform float uY; uniform float uA; uniform vec3 uC; void main(){ float d = abs(vUv.y - uY); float band = smoothstep(0.12, 0.0, d); float grid = 0.06 * step(0.92, fract(vUv.y * 28.0)); gl_FragColor = vec4(uC, (band * 0.85 + grid) * uA); }",
    });
    this.beam = new Mesh(new PlaneGeometry(5.1, 3.6), this.beamMat);
    this.beam.position.set(0, 1.9, 0.02);
    this.world.add(this.beam);

    // crate: an abstract container (box, edges, ribs) with a tag on its front face
    const cw = 2.5, ch = 2.5, cd = 5.8;
    const g = new BoxGeometry(cw, ch, cd);
    this.crateFill = new Mesh(g, new MeshBasicMaterial({ color: new Color(T.blue), transparent: true, opacity: T.dark ? 0.12 : 0.09, depthWrite: false }));
    this.crateEdges = new LineSegments(new EdgesGeometry(g), new LineBasicMaterial({ color: new Color(T.ink), transparent: true, opacity: 0.95 }));
    this.crate.add(this.crateFill, this.crateEdges);
    const ribs: number[] = [];
    for (let z = -cd / 2 + 0.5; z < cd / 2; z += 0.5) ribs.push(-cw / 2, -ch / 2, z, -cw / 2, ch / 2, z, cw / 2, -ch / 2, z, cw / 2, ch / 2, z);
    const rg = new BufferGeometry();
    rg.setAttribute("position", new Float32BufferAttribute(ribs, 3));
    this.crate.add(new LineSegments(rg, new LineBasicMaterial({ color: new Color(T.blue), transparent: true, opacity: 0.35 })));
    this.labelA = this.tex(drawTexture(640, 640, (c) => this.paintLabel(c, EXAMPLE.product, "", false)));
    this.labelB = this.tex(drawTexture(640, 640, (c) => this.paintLabel(c, EXAMPLE.code, EXAMPLE.codeName, true)));
    this.label = new Mesh(new PlaneGeometry(2.1, 2.1), new MeshBasicMaterial({ map: this.labelA, transparent: true, depthWrite: false }));
    this.label.position.set(0, 0, cd / 2 + 0.02);
    this.crate.add(this.label);
    this.crate.position.set(0, ch / 2, -34);
    this.world.add(this.crate);

    // duty layers: height follows the amount (square root, so small layers stay visible)
    const palette = T.dark ? SLAB_DARK : SLAB_LIGHT;
    const max = Math.sqrt(Math.max(...EXAMPLE.lines.map((l) => l.amount)));
    let y = ch + 0.5;
    EXAMPLE.lines.forEach((l, i) => {
      const hgt = Math.max(0.07, (Math.sqrt(l.amount) / max) * 0.95);
      const b = this.edgeBox(2.2, 1, 2.2, palette[i] ?? T.blue, T.dark ? 0.28 : 0.22, 1);
      b.grp.position.set(0, y + hgt / 2, 0);
      b.grp.scale.set(1, 0.001, 1);
      b.grp.visible = false;
      this.world.add(b.grp);
      this.slabs.push({ mesh: b.mesh, edges: b.edges, h: hgt, y });
      this.slabHolders.push(b.grp);
      y += hgt + 0.14;
    });

    // source sheets
    const sheetTex = this.tex(drawTexture(256, 340, (c) => {
      c.fillStyle = T.dark ? "#16223d" : "#ffffff"; c.fillRect(0, 0, 256, 340);
      c.strokeStyle = T.blue; c.lineWidth = 3; c.strokeRect(2, 2, 252, 336);
      c.fillStyle = T.gold; c.fillRect(22, 24, 90, 12);
      c.fillStyle = T.dark ? "#9fb0c9" : "#7b8aa3";
      for (let i = 0; i < 9; i++) c.fillRect(22, 64 + i * 26, i % 3 === 2 ? 130 : 210, 8);
    }));
    for (let i = 0; i < 9; i++) {
      const m = new Mesh(new PlaneGeometry(0.95, 1.26), new MeshBasicMaterial({ map: sheetTex, transparent: true, opacity: 0, side: DoubleSide, depthWrite: false }));
      m.visible = false;
      this.world.add(m);
      this.papers.push(m);
    }

    // candidate tags for the "not sure" beat
    EXAMPLE.candidates.forEach((code, i) => {
      const tex = this.tex(drawTexture(420, 160, (c) => {
        c.fillStyle = T.dark ? "#36270d" : "#fbe9cf"; c.fillRect(0, 0, 420, 160);
        c.strokeStyle = T.warn; c.lineWidth = 6; c.strokeRect(3, 3, 414, 154);
        c.fillStyle = T.warn; c.font = `600 54px ${MONO}`; c.textBaseline = "middle"; c.fillText(code, 28, 62);
        c.font = `500 28px ${FONT}`; c.fillText(i === 0 ? "candidate 1" : i === 1 ? "candidate 2" : "candidate 3", 30, 120);
      }));
      const m = new Mesh(new PlaneGeometry(1.7, 0.65), new MeshBasicMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false }));
      m.visible = false;
      this.world.add(m);
      this.tags.push(m);
    });

    // dust
    const n = 420, arr: number[] = [];
    for (let i = 0; i < n; i++) arr.push((Math.random() - 0.5) * 26, Math.random() * 9, -34 + Math.random() * 44);
    const dg = new BufferGeometry();
    dg.setAttribute("position", new Float32BufferAttribute(arr, 3));
    this.dust = new Points(dg, new PointsMaterial({ color: new Color(T.dark ? T.blue : T.blue), size: 0.06, transparent: true, opacity: T.dark ? 0.55 : 0.4, depthWrite: false }));
    this.world.add(this.dust);
  }
  private slabHolders: Group[] = [];

  private paintLabel(c: CanvasRenderingContext2D, big: string, small: string, isCode: boolean) {
    const T = this.t;
    c.fillStyle = T.dark ? "#111a30" : "#ffffff"; c.fillRect(0, 0, 640, 640);
    c.strokeStyle = isCode ? T.gold : T.blue; c.lineWidth = 12; c.strokeRect(6, 6, 628, 628);
    c.fillStyle = T.dark ? "#9fb0c9" : "#44546b"; c.font = `600 34px ${FONT}`; c.textBaseline = "alphabetic";
    c.fillText(isCode ? "TARIFF LINE" : "GOODS DECLARED", 44, 84);
    c.fillStyle = T.dark ? "#e7edf8" : "#0b1324";
    if (isCode) {
      c.font = `700 92px ${MONO}`; c.fillText(big, 44, 270);
      c.font = `500 34px ${FONT}`; c.fillStyle = T.dark ? "#9fb0c9" : "#44546b"; wrap(c, small, 44, 340, 550, 44);
      c.fillStyle = T.ok; c.font = `700 36px ${FONT}`; c.fillText("matched · sources attached", 44, 560);
    } else {
      c.font = `700 62px ${FONT}`; wrap(c, big, 44, 200, 550, 76);
      c.fillStyle = T.dark ? "#9fb0c9" : "#44546b"; c.font = `500 34px ${FONT}`; c.fillText("assessed value PKR 500,000", 44, 540);
    }
  }

  // ------------------------------------------------------------------------------------------------ per frame
  setProgress(p: number) { this.target = Math.min(1, Math.max(0, p)); }

  setSize(w: number, h: number) {
    this.w = Math.max(1, w); this.h = Math.max(1, h);
    this.renderer.setSize(this.w, this.h, false);
    this.camera.aspect = this.w / this.h;
    this.camera.fov = this.camera.aspect < 0.8 ? 52 : 38;
    // On wide screens the text panel sits on the left, so the scene is shifted to the right.
    // On phones the chapter card covers the lower part, so the scene is lifted instead.
    if (this.camera.aspect > 1.15) this.camera.setViewOffset(this.w, this.h, -this.w * 0.15, 0, this.w, this.h);
    else if (this.camera.aspect < 0.9) this.camera.setViewOffset(this.w, this.h, 0, this.h * 0.17, this.w, this.h);
    else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
    this.render();
  }

  setVisible(v: boolean) {
    this.visible = v;
    if (v) this.start(); else this.stop();
  }

  refreshTheme() {
    const was = this.cur;
    this.disposeWorld();
    this.build();
    this.cur = was;
    this.render();
  }

  start() {
    if (this.running || !this.visible) return;
    this.running = true;
    this.last = performance.now();
    this.renderer.setAnimationLoop(() => this.tick());
  }
  stop() {
    this.running = false;
    this.renderer.setAnimationLoop(null);
  }

  private tick() {
    const now = performance.now();
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    this.cur += (this.target - this.cur) * (1 - Math.exp(-dt * 5.5)); // cinematic inertia
    this.render();
  }

  private render() {
    const p = this.cur;
    const T = this.t;
    const time = (performance.now() - this.t0) / 1000;
    const aspect = this.camera.aspect;

    // crate: arrives, waits in the gate, leaves
    const arrive = ramp(p, 0, 0.16), leave = ramp(p, 0.84, 1);
    this.crate.position.z = lerp(-34, -0.4, arrive) + leave * 18;
    this.crate.position.y = 1.25 + Math.sin(time * 1.4) * 0.03;
    const fade = 1 - ramp(p, 0.92, 1);
    (this.crateEdges.material as LineBasicMaterial).opacity = 0.95 * fade;
    (this.crateFill.material as MeshBasicMaterial).opacity = (T.dark ? 0.12 : 0.09) * fade;
    const labelMat = this.label.material as MeshBasicMaterial;
    labelMat.opacity = fade;
    const coded = p > 0.22;
    if (labelMat.map !== (coded ? this.labelB : this.labelA)) { labelMat.map = coded ? this.labelB : this.labelA; labelMat.needsUpdate = true; }

    // scan beam
    const scan = ramp(p, 0.15, 0.27);
    this.beam.position.z = this.crate.position.z + 2.95;
    this.beamMat.uniforms.uY!.value = scan;
    this.beamMat.uniforms.uA!.value = bump(p, 0.15, 0.17, 0.27, 0.3);

    // layers rise one by one
    const sinkAll = ramp(p, 0.84, 0.93);
    this.slabs.forEach((s, i) => {
      const grp = this.slabHolders[i]!;
      const r = ramp(p, 0.3 + i * 0.034, 0.3 + i * 0.034 + 0.07) * (1 - sinkAll);
      grp.visible = r > 0.002;
      grp.scale.y = Math.max(0.001, r);
      grp.position.set(0, (s.y + (s.h * r) / 2) * 1 - (1 - r) * 0.6 + 0.0, this.crate.position.z);
      (s.mesh.material as MeshBasicMaterial).opacity = (T.dark ? 0.28 : 0.22) * r;
      (s.edges.material as LineBasicMaterial).opacity = r;
    });

    // source sheets fan out
    const fan = ramp(p, 0.53, 0.65) * (1 - ramp(p, 0.8, 0.88));
    this.papers.forEach((m, i) => {
      const a = (i / (this.papers.length - 1)) * Math.PI;
      const r = 3.1 * fan;
      m.visible = fan > 0.01;
      m.position.set(Math.cos(a) * r, 2.5 + Math.sin(a) * r * 0.75, this.crate.position.z + 0.2 + (i % 2) * 0.12);
      m.rotation.set(0, (Math.cos(a) * 0.35), (a - Math.PI / 2) * -0.25);
      (m.material as MeshBasicMaterial).opacity = fan * 0.95;
    });

    // candidate tags: shown while the tool is unsure
    const doubt = bump(p, 0.69, 0.74, 0.8, 0.84);
    this.tags.forEach((m, i) => {
      m.visible = doubt > 0.01;
      m.position.set((i - 1) * 1.95, 5.1 + Math.sin(time * 1.2 + i) * 0.06 + (1 - doubt) * 0.8, 0.2);
      (m.material as MeshBasicMaterial).opacity = doubt;
    });

    // gate light: blue while working, amber when unsure, green when cleared
    const col = new Color(T.blue).lerp(new Color(T.warn), bump(p, 0.68, 0.72, 0.8, 0.84)).lerp(new Color(T.ok), ramp(p, 0.84, 0.88));
    this.lightMat.color.copy(col);
    this.light.scale.x = 1 + 0.25 * Math.sin(time * 4) * bump(p, 0.68, 0.72, 0.8, 0.84);
    this.barrier.rotation.z = -ramp(p, 0.84, 0.9) * 1.3;

    // dust drifts; a gentle burst when cleared
    this.dust.rotation.y = time * 0.02 + p * 0.4;
    this.dust.position.y = Math.sin(time * 0.3) * 0.2;
    (this.dust.material as PointsMaterial).size = 0.06 + 0.05 * ramp(p, 0.84, 0.9);

    // camera along keyframes
    let i = 0;
    while (i < CAMERA.length - 2 && p > CAMERA[i + 1]!.p) i++;
    const a = CAMERA[i]!, b = CAMERA[i + 1]!;
    const u = ramp(p, a.p, b.p);
    const portrait = aspect < 1 ? (1 - aspect) * 7 : 0;
    this.camera.position.set(lerp(a.pos[0], b.pos[0], u), lerp(a.pos[1], b.pos[1], u), lerp(a.pos[2], b.pos[2], u) + portrait);
    this.camera.lookAt(new Vector3(lerp(a.look[0], b.look[0], u), lerp(a.look[1], b.look[1], u), lerp(a.look[2], b.look[2], u)));
    this.renderer.render(this.scene, this.camera);
  }

  // ------------------------------------------------------------------------------------------------ cleanup
  private disposeWorld() {
    this.world.traverse((o: Object3D) => {
      const m = o as Mesh;
      m.geometry?.dispose?.();
      const mat = m.material as Material | Material[] | undefined;
      if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
    });
    this.textures.forEach((t) => t.dispose());
    this.textures = [];
    this.world.clear();
    this.crate = new Group();
    this.barrier = new Group();
    this.slabs = []; this.slabHolders = []; this.papers = []; this.tags = [];
  }

  dispose() {
    this.stop();
    this.disposeWorld();
    this.renderer.dispose();
  }
}
