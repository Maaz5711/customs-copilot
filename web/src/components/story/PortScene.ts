import {
  BoxGeometry, BufferGeometry, CanvasTexture, CircleGeometry, Color, CylinderGeometry, DoubleSide, DynamicDrawUsage, EdgesGeometry, ExtrudeGeometry, Float32BufferAttribute,
  Fog, Group, IcosahedronGeometry, LineBasicMaterial, LineSegments, Material, MathUtils, Mesh, MeshBasicMaterial, Object3D, PerspectiveCamera,
  PlaneGeometry, Scene, Shape, SRGBColorSpace, Texture, Vector3, WebGLRenderer,
} from "three";
import { EXAMPLE, clamp01, fmtPKR, ramp } from "./chapters";

// The home-page story as a hand-drafted 3D sketch of a port, drawn in code (no downloaded models or photos): ink outlines on paper with colour only
// on what matters. A ship docks, the crane lifts one container onto the quay, a clearing agent walks over and scans it, the duty layers stack up,
// the source sheets fan out, candidate codes float up when unsure, then a truck takes the container through the green customs gate.
// Everything is driven by one number, scroll progress 0..1, so scrolling back plays it in reverse. Light theme: white paper; dark theme: blueprint.

type Tokens = { dark: boolean; paper: string; ink: string; ink2: string; gold: string; ok: string; warn: string };

const readTokens = (el: Element): Tokens => {
  const cs = getComputedStyle(el);
  const v = (n: string, d: string) => cs.getPropertyValue(n).trim() || d;
  const t = document.documentElement.dataset.theme;
  const dark = t === "dark" || (t !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  return {
    dark, paper: v("--paper", dark ? "#0c1a33" : "#f8f7f3"), ink: v("--ink", dark ? "#e7edf8" : "#0b1324"), ink2: v("--ink-2", dark ? "#9fb0c9" : "#44546b"),
    gold: v("--gold", "#b9801f"), ok: v("--ok", "#17663b"), warn: v("--warn", "#8a4b00"),
  };
};

const HUE = {
  orange: "#ec7a3c", blue: "#2f6fd6", teal: "#16a394", red: "#dd4b4b", yellow: "#f2b632", violet: "#7a5cc7", navy: "#284a7e",
  vest: "#b8d82e", sky: "#8cc4f2", sun: "#ffc857",
};
const BOX_HUES = [HUE.blue, HUE.teal, HUE.red, HUE.yellow, HUE.violet, HUE.orange];
const SLAB_HUES = [HUE.blue, HUE.teal, HUE.violet, HUE.orange, HUE.yellow, HUE.red];

const FONT = 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif';
const MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const lerp = MathUtils.lerp;
const bump = (p: number, a: number, b: number, c: number, d: number) => ramp(p, a, b) * (1 - ramp(p, c, d));
/** Piecewise value over scroll: eased between consecutive [p, value] keys (keys must have increasing p). */
const track = (p: number, keys: [number, number][]) => {
  if (p <= keys[0]![0]) return keys[0]![1];
  for (let i = 1; i < keys.length; i++) {
    const [p1, v1] = keys[i]!;
    if (p <= p1) { const [p0, v0] = keys[i - 1]!; return lerp(v0, v1, ramp(p, p0, p1)); }
  }
  return keys[keys.length - 1]![1];
};

// Positions (scene units are about a metre): quay edge at z = -8, water behind it, road along z = -4, crane centred on x = 6, gate at x = 24.
const C = { L: 6, H: 2.6, W: 2.44 }; // container
const ROAD_Z = -4, GATE_X = 24, CRANE_X = 6, TROLLEY_Y = 12.2;
const AGENT_PATH: [number, number][] = [[25.5, 3.6], [12, 1.4], [8.7, -1.5]]; // ends at the right corner, clear of the code label

const CAMERA: [number, [number, number, number], [number, number, number]][] = [
  [0, [-36, 15, 32], [-24, 3, -12]],
  [0.09, [-10, 15, 30], [3, 5, -10]],
  [0.17, [16, 12, 24], [6, 4, -6]],
  [0.27, [20, 6, 12], [9, 1.8, -2]],
  [0.33, [13.5, 4, 7.5], [6.5, 1.8, -2.8]],
  [0.46, [16, 9, 16], [6, 4.6, -4]],
  [0.58, [4, 8, 15], [6, 4.4, -3]],
  [0.7, [10, 10, 19], [6, 6, -4]],
  [0.8, [-2, 10, 25], [4, 3, -4]],
  [0.875, [10, 8, 20], [14, 2.6, -4]],
  [1, [60, 8, 22], [72, 2, -4]],
]

function drawTexture(w: number, h: number, draw: (ctx: CanvasRenderingContext2D) => void): CanvasTexture {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  draw(c.getContext("2d")!);
  const tex = new CanvasTexture(c);
  tex.colorSpace = SRGBColorSpace;
  tex.anisotropy = 4;
  return tex;
}

/** A tiny repeatable random sequence, so the yard and the waves look the same on every visit. */
const rand = (seed: number) => () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;

type Agent = { root: Group; legL: Group; legR: Group; armL: Group; armR: Group; tablet: Mesh };

export class PortScene {
  private renderer: WebGLRenderer;
  private scene = new Scene();
  private camera = new PerspectiveCamera(36, 1, 0.1, 400);
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
  private look = new Vector3();
  onLost?: () => void;

  // moving parts
  private ship = new Group();
  private hero = new Group();
  private heroLabel!: Mesh;
  private labels: Texture[] = [];
  private trolley = new Group();
  private cables!: LineSegments;
  private spreader = new Group();
  private agent!: Agent;
  private scan!: Mesh;
  private rays!: LineSegments;
  private slabs: Group[] = [];
  private sheets: Mesh[] = [];
  private tags: Mesh[] = [];
  private truck = new Group();
  private wheels: Mesh[] = [];
  private barrier = new Group();
  private light!: MeshBasicMaterial;
  private waves = new Group();
  private gulls: Group[] = [];

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
    this.renderer = new WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: "default" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2));
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.stop(); this.onLost?.(); });
    this.scene.add(this.world);
    this.build();
  }

  // ------------------------------------------------------------------------------------------------ drawing helpers
  private tex(t: CanvasTexture) { this.textures.push(t); return t; }

  /** A colour pushed toward the paper, so fills read as a light wash under the ink lines. */
  private wash(hex: string, k: number) { return new Color(hex).lerp(new Color(this.t.paper), k); }

  private fill(hex: string, k = 0.3) {
    return new MeshBasicMaterial({ color: this.wash(hex, k), polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
  }

  private ink(opacity = 0.92, hex?: string) {
    return new LineBasicMaterial({ color: new Color(hex ?? this.t.ink), transparent: opacity < 1, opacity });
  }

  /** A filled solid with ink outlines. The geometry should already sit where it belongs inside its group. */
  private solid(geo: BufferGeometry, hex: string, k = 0.3, lineOpacity = 0.92, threshold = 20) {
    const g = new Group();
    g.add(new Mesh(geo, this.fill(hex, k)), new LineSegments(new EdgesGeometry(geo, threshold), this.ink(lineOpacity)));
    return g;
  }

  /** A box standing on y = 0 (its base at the origin). */
  private box(w: number, h: number, d: number, hex: string, k = 0.3, lineOpacity = 0.92) {
    const geo = new BoxGeometry(w, h, d);
    geo.translate(0, h / 2, 0);
    return this.solid(geo, hex, k, lineOpacity);
  }

  private lines(pts: number[], opacity = 0.6, hex?: string) {
    const g = new BufferGeometry();
    g.setAttribute("position", new Float32BufferAttribute(pts, 3));
    return new LineSegments(g, this.ink(opacity, hex));
  }

  private container(hex: string, k = 0.32) {
    const g = this.box(C.L, C.H, C.W, hex, k);
    const pts: number[] = [];
    for (let x = -C.L / 2 + 0.3; x < C.L / 2 - 0.1; x += 0.3)
      for (const z of [-C.W / 2 - 0.004, C.W / 2 + 0.004]) pts.push(x, 0.14, z, x, C.H - 0.14, z);
    const ex = C.L / 2 + 0.004; // door end: two doors and four locking bars
    pts.push(ex, 0.1, 0, ex, C.H - 0.1, 0);
    for (const z of [-0.85, -0.35, 0.35, 0.85]) pts.push(ex, 0.12, z, ex, C.H - 0.12, z);
    g.add(this.lines(pts, 0.35));
    return g;
  }

  private label(w: number, h: number, tex: Texture, opacity = 1) {
    return new Mesh(new PlaneGeometry(w, h), new MeshBasicMaterial({ map: tex, transparent: true, opacity, depthWrite: false, side: DoubleSide }));
  }

  // ------------------------------------------------------------------------------------------------ building
  private build() {
    this.t = readTokens(this.canvas);
    const T = this.t;
    this.renderer.setClearColor(new Color(T.paper), 1);
    this.scene.fog = new Fog(new Color(T.paper), 60, 190);
    const r = rand(7);

    // ground: quay edge, bollards, road with dashed centre line, a few parking marks
    const ground: number[] = [];
    ground.push(-160, 0, -8, 200, 0, -8, -160, -1.2, -8, 200, -1.2, -8);
    for (let x = -150; x < 200; x += 6) ground.push(x, 0, -8, x, -1.2, -8);
    for (const z of [ROAD_Z - 1.8, ROAD_Z + 1.8]) ground.push(-160, 0.01, z, 200, 0.01, z);
    for (let x = -150; x < 200; x += 3) ground.push(x, 0.01, ROAD_Z, x + 1.4, 0.01, ROAD_Z);
    for (let x = -81; x < -44; x += 6.6) ground.push(x, 0.01, 0.4, x, 0.01, 6.2);
    this.world.add(this.lines(ground, T.dark ? 0.45 : 0.35));
    for (let x = -60; x < 90; x += 7) {
      const b = this.solid(new CylinderGeometry(0.22, 0.26, 0.5, 8).translate(0, 0.25, 0), HUE.yellow, 0.35, 0.7);
      b.position.set(x, 0, -7.6);
      this.world.add(b);
    }

    // water with sketched waves
    const water = new Mesh(new PlaneGeometry(420, 120), this.fill(HUE.sky, T.dark ? 0.72 : 0.62));
    water.rotation.x = -Math.PI / 2;
    water.position.set(20, -1.2, -68);
    this.world.add(water);
    const wv: number[] = [];
    for (let i = 0; i < 260; i++) {
      const x = -90 + r() * 200, z = -60 + r() * 50, y = -1.18, s = 0.5 + r() * 0.7;
      wv.push(x, y, z, x + s, y, z - 0.25, x + s, y, z - 0.25, x + 2 * s, y, z);
    }
    const wl = this.lines(wv, T.dark ? 0.5 : 0.4, HUE.blue);
    this.waves.add(wl);
    this.world.add(this.waves);

    // a sun (or a moon in blueprint mode) and a few gulls, for life
    const sun = new Mesh(new CircleGeometry(10, 48), new MeshBasicMaterial({ color: this.wash(T.dark ? "#dfe8ff" : HUE.sun, T.dark ? 0.75 : 0.35), fog: false }));
    sun.position.set(-40, 30, -150);
    this.world.add(sun);
    for (let i = 0; i < 6; i++) {
      const g = new Group();
      const wing = this.lines([-0.6, 0.18, 0, 0, 0, 0, 0, 0, 0, 0.6, 0.18, 0], 0.8);
      g.add(wing);
      this.gulls.push(g);
      this.world.add(g);
    }

    // yard stacks for context
    const yard: [number, number][] = [];
    for (let i = 0; i < 5; i++) yard.push([-78 + i * 6.6, 1.8], [-78 + i * 6.6, 4.7]); // well left of the opening view of the ship
    yard.forEach(([x, z], i) => {
      const tiers = 1 + Math.floor(r() * 3);
      for (let k = 0; k < tiers; k++) {
        const c = this.container(BOX_HUES[(i * 3 + k) % BOX_HUES.length]!, T.dark ? 0.55 : 0.42);
        c.position.set(x, k * C.H, z);
        this.world.add(c);
      }
    });

    this.buildShip(r);
    this.buildCrane();
    this.buildGate();

    // the hero container and its label (goods declared -> tariff line -> cleared)
    const hero = this.container(HUE.orange, T.dark ? 0.3 : 0.18);
    this.hero.add(hero);
    this.labels = [
      this.tex(drawTexture(640, 250, (c) => this.paintLabel(c, "GOODS DECLARED", EXAMPLE.product, "PCT ????.????", false))),
      this.tex(drawTexture(640, 250, (c) => this.paintLabel(c, "TARIFF LINE", `PCT ${EXAMPLE.code}`, EXAMPLE.codeName, false))),
      this.tex(drawTexture(640, 250, (c) => this.paintLabel(c, "TARIFF LINE", `PCT ${EXAMPLE.code}`, EXAMPLE.codeName, true))),
    ];
    this.heroLabel = this.label(4.1, 1.6, this.labels[0]!);
    this.heroLabel.position.set(0, C.H / 2, C.W / 2 + 0.02);
    this.hero.add(this.heroLabel);
    this.world.add(this.hero);

    this.agent = this.buildAgent();
    this.world.add(this.agent.root);

    // scan: a sheet of light that sweeps along the container, with rays from the tablet
    this.scan = new Mesh(new PlaneGeometry(C.W + 0.5, C.H + 0.5), new MeshBasicMaterial({ color: new Color(HUE.teal), transparent: true, opacity: 0, depthWrite: false, side: DoubleSide }));
    this.scan.rotation.y = Math.PI / 2;
    this.world.add(this.scan);
    this.rays = this.lines(new Array(24).fill(0), 0.7, HUE.teal);
    (this.rays.geometry.getAttribute("position") as Float32BufferAttribute).setUsage(DynamicDrawUsage);
    this.world.add(this.rays);

    // duty layers, each labelled with its tax, rate and amount
    EXAMPLE.lines.forEach((l, i) => {
      const g = new Group();
      g.add(this.box(5.4, 0.34, 2.1, SLAB_HUES[i]!, T.dark ? 0.35 : 0.2, 1));
      const tag = this.tex(drawTexture(512, 64, (c) => {
        c.fillStyle = T.ink; c.font = `700 34px ${MONO}`; c.textBaseline = "middle";
        c.fillText(`${l.tax} ${l.rate}`, 12, 34);
        c.font = `600 30px ${FONT}`; c.textAlign = "right"; c.fillText(`PKR ${fmtPKR(l.amount)}`, 500, 34);
      }));
      const m = this.label(5.0, 0.32, tag);
      m.position.set(0, 0.17, 1.06);
      g.add(m);
      g.visible = false;
      this.slabs.push(g);
      this.world.add(g);
    });

    // source sheets
    EXAMPLE.lines.forEach((l, i) => {
      const tex = this.tex(drawTexture(260, 340, (c) => {
        c.fillStyle = T.dark ? "#13233f" : "#ffffff"; c.fillRect(0, 0, 260, 340);
        c.strokeStyle = T.ink; c.lineWidth = 3; c.strokeRect(2, 2, 256, 336);
        c.fillStyle = SLAB_HUES[i]!; c.fillRect(2, 2, 256, 54);
        c.fillStyle = "#ffffff"; c.font = `700 30px ${MONO}`; c.textBaseline = "middle"; c.fillText(l.tax, 18, 30);
        c.fillStyle = T.ink; c.font = `600 22px ${FONT}`;
        const words = l.source.split(" "); let line = "", y = 92;
        for (const w of words) { const t = line ? `${line} ${w}` : w; if (c.measureText(t).width > 224 && line) { c.fillText(line, 18, y); line = w; y += 28; } else line = t; }
        c.fillText(line, 18, y);
        c.fillStyle = T.ink2;
        for (let k = 0; k < 6; k++) c.fillRect(18, 180 + k * 24, k % 3 === 2 ? 120 : 220, 6);
      }));
      const m = this.label(1.3, 1.7, tex, 0);
      m.visible = false;
      this.sheets.push(m);
      this.world.add(m);
    });

    // candidate codes for the "not sure" beat
    EXAMPLE.candidates.forEach((code, i) => {
      const tex = this.tex(drawTexture(420, 150, (c) => {
        c.fillStyle = T.dark ? "#36270d" : "#fff4dd"; c.fillRect(0, 0, 420, 150);
        c.strokeStyle = T.warn; c.lineWidth = 6; c.strokeRect(3, 3, 414, 144);
        c.fillStyle = T.warn; c.font = `700 56px ${MONO}`; c.textBaseline = "middle"; c.fillText(code, 26, 60);
        c.font = `600 26px ${FONT}`; c.fillText(`candidate ${i + 1}`, 28, 118);
      }));
      const m = this.label(2.4, 0.86, tex, 0);
      m.visible = false;
      this.tags.push(m);
      this.world.add(m);
    });

    this.buildTruck();
  }

  private buildShip(r: () => number) {
    const T = this.t;
    const hull = new Shape();
    hull.moveTo(-13, -1.3); hull.lineTo(10, -1.3); hull.lineTo(13.6, 2.5); hull.lineTo(-13, 2.5); hull.lineTo(-13, -1.3);
    const hg = new ExtrudeGeometry(hull, { depth: 6, bevelEnabled: false });
    hg.translate(0, 0, -3);
    this.ship.add(this.solid(hg, HUE.navy, T.dark ? 0.3 : 0.12, 0.95, 25));
    this.ship.add(this.lines([-13, -0.5, 3.01, 10.75, -0.5, 3.01], 0.9, HUE.red)); // boot-top line
    // bridge and funnel at the stern
    const bridge = this.box(3, 4.6, 5.4, "#ffffff", T.dark ? 0.8 : 0.1);
    bridge.position.set(-11.3, 2.5, 0);
    const win: number[] = [];
    for (let k = 0; k < 3; k++) win.push(-9.79, 3.6 + k * 1.2, -2.4, -9.79, 3.6 + k * 1.2, 2.4);
    const funnel = this.box(1.2, 1.8, 1.6, HUE.red, 0.3);
    funnel.position.set(-12, 7.1, 0);
    this.ship.add(bridge, funnel, this.lines(win, 0.6));
    // deck cargo: three bays, three rows; the hero sits on top of bay x = 6, row nearest the quay
    let n = 0;
    for (const bx of [-6.4, -0.2, 6]) {
      for (const rz of [-2.5, 0, 2.5]) {
        const hero = bx === 6 && rz === 2.5;
        const tiers = hero ? 1 : 1 + Math.floor(r() * 3);
        for (let k = 0; k < tiers; k++) {
          const c = this.container(BOX_HUES[n++ % BOX_HUES.length]!, T.dark ? 0.5 : 0.38);
          c.position.set(bx, 2.5 + k * C.H, rz);
          this.ship.add(c);
        }
      }
    }
    this.ship.position.set(-34, 0, -12.5);
    this.world.add(this.ship);
  }

  private buildCrane() {
    const T = this.t;
    const crane = new Group();
    const blue = T.dark ? 0.55 : 0.4;
    for (const x of [2.2, 9.8]) for (const z of [-0.2, -7.8]) {
      const leg = this.box(0.45, 12.6, 0.45, HUE.blue, blue);
      leg.position.set(x, 0, z);
      crane.add(leg);
    }
    for (const z of [-0.2, -7.8]) { const b = this.box(8.05, 0.6, 0.45, HUE.blue, blue); b.position.set(6, 11.6, z); crane.add(b); }
    for (const x of [2.2, 9.8]) { const b = this.box(0.45, 0.5, 7.6, HUE.blue, blue); b.position.set(x, 6.4, -4); crane.add(b); }
    for (const x of [4.7, 7.3]) { const rail = this.box(0.4, 0.5, 22, HUE.blue, blue); rail.position.set(x, 12.6, -8); crane.add(rail); }
    const house = this.box(3.4, 1.6, 3, "#ffffff", T.dark ? 0.8 : 0.1);
    house.position.set(6, 13.1, 1.6);
    crane.add(house);
    // A-frame and stays
    const stays: number[] = [];
    for (const x of [4.7, 7.3]) stays.push(x, 13.1, -4, x, 19, -4, x, 19, -4, x, 13.1, -19, x, 19, -4, x, 13.1, 3);
    stays.push(4.7, 19, -4, 7.3, 19, -4);
    for (let z = 2; z > -19; z -= 2) stays.push(4.7, 13.1, z, 7.3, 13.1, z);
    crane.add(this.lines(stays, 0.8));
    crane.position.x = CRANE_X - 6;
    this.world.add(crane);

    // trolley, cables, spreader
    this.trolley.add(this.box(2.8, 0.7, 2.2, HUE.yellow, 0.3));
    this.trolley.position.set(CRANE_X, TROLLEY_Y, -10);
    this.world.add(this.trolley);
    const cp: number[] = [];
    for (const [x, z] of [[-1, -0.6], [1, -0.6], [-1, 0.6], [1, 0.6]] as const) cp.push(x, 0, z, x, -1, z);
    this.cables = this.lines(cp, 0.85);
    this.world.add(this.cables);
    this.spreader.add(this.box(6.1, 0.3, 2.45, HUE.yellow, 0.3));
    this.world.add(this.spreader);
  }

  private buildGate() {
    const T = this.t;
    const gate = new Group();
    for (const z of [-0.9, -7.1]) { const p = this.box(0.5, 5.5, 0.5, "#ffffff", T.dark ? 0.75 : 0.05); p.position.set(GATE_X, 0, z); gate.add(p); }
    const lintel = this.box(0.7, 0.8, 6.9, HUE.navy, T.dark ? 0.4 : 0.2);
    lintel.position.set(GATE_X, 5.5, ROAD_Z);
    gate.add(lintel);
    const sign = this.tex(drawTexture(700, 80, (c) => {
      c.fillStyle = "#ffffff"; c.font = `700 46px ${FONT}`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText("PAKISTAN CUSTOMS", 350, 42);
    }));
    const sm = this.label(6.2, 0.7, sign);
    sm.rotation.y = -Math.PI / 2;
    sm.position.set(GATE_X - 0.36, 5.9, ROAD_Z);
    gate.add(sm);
    this.light = new MeshBasicMaterial({ color: new Color(T.ink2) });
    const lamp = new Mesh(new BoxGeometry(0.5, 0.36, 1.6), this.light);
    lamp.position.set(GATE_X, 6.5, ROAD_Z);
    gate.add(lamp, new LineSegments(new EdgesGeometry(lamp.geometry), this.ink()).translateX(GATE_X).translateY(6.5).translateZ(ROAD_Z));
    // barrier arm: pivots at the booth side and swings up
    const arm = this.box(0.18, 0.18, 5.8, "#ffffff", 0.0, 1);
    arm.position.set(0, -0.09, -2.9);
    this.barrier.add(arm);
    for (let k = 0; k < 3; k++) { const s = this.box(0.2, 0.2, 0.9, HUE.red, 0.1, 0); s.position.set(0, -0.1, -0.7 - k * 1.9); this.barrier.add(s); }
    this.barrier.position.set(GATE_X - 0.6, 1.1, -1.0);
    gate.add(this.barrier);
    // booth
    const booth = this.box(2.6, 2.8, 2.4, "#ffffff", T.dark ? 0.8 : 0.08);
    booth.position.set(GATE_X + 3.2, 0, 1.4);
    const roof = this.box(3.2, 0.25, 3, HUE.navy, T.dark ? 0.4 : 0.2);
    roof.position.set(GATE_X + 3.2, 2.8, 1.4);
    const bw: number[] = [];
    bw.push(GATE_X + 2.2, 1.2, 2.61, GATE_X + 4.2, 1.2, 2.61, GATE_X + 2.2, 2.3, 2.61, GATE_X + 4.2, 2.3, 2.61, GATE_X + 2.2, 1.2, 2.61, GATE_X + 2.2, 2.3, 2.61, GATE_X + 4.2, 1.2, 2.61, GATE_X + 4.2, 2.3, 2.61);
    gate.add(booth, roof, this.lines(bw, 0.8));
    this.world.add(gate);
  }

  private buildAgent(): Agent {
    const T = this.t;
    const root = new Group();
    const body = new Group();
    const limb = (w: number, h: number, d: number, hex: string) => {
      const g = new BoxGeometry(w, h, d);
      g.translate(0, -h / 2, 0);
      return this.solid(g, hex, T.dark ? 0.35 : 0.2, 0.95);
    };
    const legL = new Group(), legR = new Group();
    legL.add(limb(0.19, 0.86, 0.22, HUE.navy)); legR.add(limb(0.19, 0.86, 0.22, HUE.navy));
    legL.position.set(-0.12, 0.9, 0); legR.position.set(0.12, 0.9, 0);
    const torso = this.box(0.5, 0.64, 0.28, HUE.navy, T.dark ? 0.35 : 0.25);
    torso.position.y = 0.88;
    const vest = this.box(0.53, 0.5, 0.31, HUE.vest, T.dark ? 0.2 : 0.05);
    vest.position.y = 0.98;
    const stripes = this.lines([-0.27, 1.12, 0.16, 0.27, 1.12, 0.16, -0.27, 1.3, 0.16, 0.27, 1.3, 0.16], 0.9, "#9aa3ad");
    const head = this.solid(new IcosahedronGeometry(0.15, 1), "#f1c9a5", T.dark ? 0.4 : 0.1, 0.8, 10);
    head.position.y = 1.7;
    const hat = this.solid(new CylinderGeometry(0.15, 0.19, 0.12, 10), HUE.yellow, 0.1, 0.9);
    hat.position.y = 1.83;
    const armL = new Group(), armR = new Group();
    armL.add(limb(0.12, 0.6, 0.14, HUE.navy)); armR.add(limb(0.12, 0.6, 0.14, HUE.navy));
    armL.position.set(-0.33, 1.48, 0); armR.position.set(0.33, 1.48, 0);
    const tablet = new Mesh(new BoxGeometry(0.34, 0.03, 0.26), this.fill(HUE.teal, 0.2));
    tablet.position.set(0, -0.62, 0.1);
    tablet.add(new LineSegments(new EdgesGeometry(tablet.geometry), this.ink()));
    armR.add(tablet);
    body.add(legL, legR, torso, vest, stripes, head, hat, armL, armR);
    body.scale.setScalar(1.25);
    root.add(body);
    return { root, legL, legR, armL, armR, tablet };
  }

  private buildTruck() {
    const T = this.t;
    const chassis = this.box(12, 0.3, 2.3, "#5b6474", T.dark ? 0.5 : 0.45);
    chassis.position.set(1.4, 0.9, 0);
    const cab = this.box(2.6, 2.7, 2.5, HUE.red, T.dark ? 0.3 : 0.15);
    cab.position.set(6.2, 0.9, 0);
    const det: number[] = [];
    det.push(7.51, 2.3, -1.0, 7.51, 2.3, 1.0, 7.51, 3.4, -1.0, 7.51, 3.4, 1.0, 7.51, 2.3, -1.0, 7.51, 3.4, -1.0, 7.51, 2.3, 1.0, 7.51, 3.4, 1.0); // windscreen
    det.push(5.2, 2.3, 1.26, 6.6, 2.3, 1.26, 5.2, 3.3, 1.26, 6.6, 3.3, 1.26, 5.2, 2.3, 1.26, 5.2, 3.3, 1.26, 6.6, 2.3, 1.26, 6.6, 3.3, 1.26); // side window
    det.push(4.95, 3.6, 0.9, 4.95, 4.4, 0.9); // exhaust
    this.truck.add(chassis, cab, this.lines(det, 0.9));
    for (const x of [-3.8, -2.6, 3.4, 4.5, 6.6]) for (const z of [-1.0, 1.0]) {
      const g = new CylinderGeometry(0.5, 0.5, 0.36, 12);
      g.rotateX(Math.PI / 2);
      const wheel = new Mesh(g, this.fill(T.dark ? "#cfd8e6" : "#2b3240", T.dark ? 0.6 : 0.1));
      wheel.add(new LineSegments(new EdgesGeometry(g, 25), this.ink(0.9, T.dark ? undefined : "#8b95a5")));
      wheel.add(this.lines([-0.42, 0, z * 0.2, 0.42, 0, z * 0.2, 0, -0.42, z * 0.2, 0, 0.42, z * 0.2], 0.9, T.dark ? undefined : "#c9d1dc"));
      wheel.position.set(x, 0.5, z);
      this.wheels.push(wheel);
      this.truck.add(wheel);
    }
    this.truck.position.set(-48, 0, ROAD_Z);
    this.truck.visible = false;
    this.world.add(this.truck);
  }

  private paintLabel(c: CanvasRenderingContext2D, kicker: string, big: string, small: string, cleared: boolean) {
    const T = this.t;
    c.fillStyle = T.dark ? "#13233f" : "#ffffff"; c.fillRect(0, 0, 640, 250);
    c.strokeStyle = T.ink; c.lineWidth = 6; c.strokeRect(3, 3, 634, 244);
    c.fillStyle = T.ink2; c.font = `700 26px ${MONO}`; c.textBaseline = "alphabetic"; c.fillText(kicker, 28, 50);
    c.fillStyle = T.ink; c.font = big.startsWith("PCT") ? `700 64px ${MONO}` : `700 40px ${FONT}`; c.fillText(big, 28, 130, 584);
    c.fillStyle = T.ink2; c.font = `500 28px ${FONT}`; c.fillText(small, 28, 196, 584);
    if (cleared) {
      c.save(); c.translate(470, 150); c.rotate(-0.18);
      c.strokeStyle = T.ok; c.lineWidth = 7; c.strokeRect(-130, -46, 260, 92);
      c.fillStyle = T.ok; c.font = `800 52px ${FONT}`; c.textAlign = "center"; c.textBaseline = "middle"; c.fillText("CLEARED", 0, 4);
      c.restore();
    }
  }

  // ------------------------------------------------------------------------------------------------ per frame
  setProgress(p: number) { this.target = clamp01(p); }

  setSize(w: number, h: number) {
    this.w = Math.max(1, w); this.h = Math.max(1, h);
    this.renderer.setSize(this.w, this.h, false);
    this.camera.aspect = this.w / this.h;
    this.camera.fov = this.camera.aspect < 0.8 ? 54 : 36;
    // Wide screens: the chapter card sits on the left, so the drawing shifts right. Phones: the card covers the bottom, so the drawing lifts.
    if (this.camera.aspect > 1.15) this.camera.setViewOffset(this.w, this.h, -this.w * 0.16, 0, this.w, this.h);
    else if (this.camera.aspect < 0.9) this.camera.setViewOffset(this.w, this.h, 0, this.h * 0.2, this.w, this.h);
    else this.camera.clearViewOffset();
    this.camera.updateProjectionMatrix();
    this.render();
  }

  setVisible(v: boolean) {
    this.visible = v;
    if (v) this.start(); else this.stop();
  }

  refreshTheme() {
    this.disposeWorld();
    this.build();
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
    this.cur += (this.target - this.cur) * (1 - Math.exp(-dt * 5)); // gentle inertia
    this.render();
  }

  private render() {
    const p = this.cur;
    const T = this.t;
    const time = (performance.now() - this.t0) / 1000;

    // 1. the ship docks
    const shipX = lerp(-34, 0, ramp(p, 0, 0.09));
    this.ship.position.x = shipX;
    this.ship.position.y = Math.sin(time * 0.8) * 0.05;
    this.waves.position.x = (time * 0.35) % 2.4;

    // 2. the crane lifts the container onto the quay; later onto the truck
    const truckX = track(p, [[0.775, -48], [0.835, 6], [0.875, 6], [1, 82]]);
    const heroY = track(p, [[0.11, 5.1], [0.13, 8.4], [0.155, 8.4], [0.175, 0], [0.765, 0], [0.79, 4.4], [0.835, 4.4], [0.86, 1.2]]);
    const heroZ = track(p, [[0.13, -10], [0.155, ROAD_Z]]);
    const onTruck = p >= 0.86;
    this.hero.position.set(onTruck ? truckX : 6 + shipX, heroY + (p < 0.11 ? this.ship.position.y : 0), heroZ);
    const trolleyZ = track(p, [[0.13, -10], [0.155, ROAD_Z]]);
    this.trolley.position.z = trolleyZ;
    const sp = track(p, [[0.08, 10.6], [0.11, 7.7], [0.13, 11.0], [0.155, 11.0], [0.175, 2.6], [0.2, 10.6], [0.74, 10.6], [0.765, 2.6], [0.79, 7.0], [0.835, 7.0], [0.86, 3.8], [0.89, 10.6]]);
    this.spreader.position.set(CRANE_X, sp, trolleyZ);
    this.cables.position.set(CRANE_X, TROLLEY_Y, trolleyZ);
    this.cables.scale.y = Math.max(0.01, TROLLEY_Y - (sp + 0.3));

    // container label: goods declared -> tariff line -> cleared
    const lm = this.heroLabel.material as MeshBasicMaterial;
    const want = this.labels[p < 0.3 ? 0 : p < 0.785 ? 1 : 2]!;
    if (lm.map !== want) { lm.map = want; lm.needsUpdate = true; }

    // 3. the clearing agent walks from the gate booth to the container, checks it, and later turns to watch the truck leave
    const a = this.agent;
    const u = ramp(p, 0.17, 0.27);
    const segs = AGENT_PATH.slice(1).map((pt, i) => Math.hypot(pt[0] - AGENT_PATH[i]![0], pt[1] - AGENT_PATH[i]![1]));
    const total = segs.reduce((s, x) => s + x, 0);
    let d = u * total, si = 0;
    while (si < segs.length - 1 && d > segs[si]!) { d -= segs[si]!; si++; }
    const A = AGENT_PATH[si]!, B = AGENT_PATH[si + 1]!;
    const f = segs[si]! > 0 ? clamp01(d / segs[si]!) : 1;
    a.root.position.set(lerp(A[0], B[0], f), 0, lerp(A[1], B[1], f));
    const walking = Math.min(1, u * 10, (1 - u) * 10);
    const heading = Math.atan2(B[0] - A[0], B[1] - A[1]);
    const atWork = Math.atan2(6 - 8.7, ROAD_Z + 1.5); // face the middle of the container
    let facing = lerp(heading, atWork, ramp(p, 0.265, 0.285));
    facing = lerp(facing, -1.5 * Math.PI, ramp(p, 0.86, 0.9)); // turn the short way round to watch the truck
    a.root.rotation.y = facing;
    a.root.visible = p > 0.14;
    const phase = u * total * 2.6;
    a.legL.rotation.x = Math.sin(phase) * 0.55 * walking;
    a.legR.rotation.x = -Math.sin(phase) * 0.55 * walking;
    a.armL.rotation.x = -Math.sin(phase) * 0.45 * walking - ramp(p, 0.9, 0.93) * 2.6 + Math.sin(time * 6) * 0.2 * ramp(p, 0.91, 0.94);
    a.armR.rotation.x = Math.sin(phase) * 0.45 * walking - track(p, [[0.26, 0], [0.29, 1.15], [0.74, 1.15], [0.78, 0]]);
    a.root.position.y = Math.abs(Math.sin(phase)) * 0.05 * walking;

    // scan sweep with rays from the tablet
    const scanA = bump(p, 0.27, 0.285, 0.315, 0.335);
    const sx = lerp(6 - C.L / 2, 6 + C.L / 2, ramp(p, 0.275, 0.325));
    this.scan.position.set(sx, C.H / 2, ROAD_Z);
    (this.scan.material as MeshBasicMaterial).opacity = 0.32 * scanA;
    this.scan.visible = scanA > 0.01;
    const tp = new Vector3();
    a.tablet.getWorldPosition(tp);
    const rp = this.rays.geometry.getAttribute("position") as Float32BufferAttribute;
    const corners = [[0.25, -C.W / 2 - 0.25], [0.25, C.W / 2 + 0.25], [C.H + 0.25, -C.W / 2 - 0.25], [C.H + 0.25, C.W / 2 + 0.25]] as const;
    corners.forEach(([y, z], k) => { rp.setXYZ(k * 2, tp.x, tp.y, tp.z); rp.setXYZ(k * 2 + 1, sx, y, ROAD_Z + z); });
    rp.needsUpdate = true;
    this.rays.visible = scanA > 0.01;
    (this.rays.material as LineBasicMaterial).opacity = 0.7 * scanA;

    // 4. duty layers stack above the container, then fold back into it
    const fold = ramp(p, 0.76, 0.79);
    this.slabs.forEach((g, k) => {
      const e = ramp(p, 0.34 + k * 0.022, 0.38 + k * 0.022) * (1 - fold);
      g.visible = e > 0.01 && !onTruck;
      g.position.set(6, lerp(C.H, C.H + 0.3 + k * 0.48, e), ROAD_Z);
      g.scale.set(lerp(0.6, 1, e), Math.max(0.001, e), lerp(0.6, 1, e));
    });

    // 5. source sheets fan out from the tablet
    this.sheets.forEach((m, k) => {
      const o = ramp(p, 0.5 + k * 0.015, 0.56 + k * 0.015) * (1 - ramp(p, 0.64, 0.68));
      m.visible = o > 0.01;
      m.position.set(lerp(tp.x, 6 + (k - 2.5) * 1.55, o), lerp(tp.y, 6.6 + Math.sin(k * 1.3) * 0.35 + Math.sin(time * 1.1 + k) * 0.05, o), lerp(tp.z, -1.4, o));
      m.rotation.set(0, 0, (k - 2.5) * -0.06);
      m.scale.setScalar(Math.max(0.001, o));
      (m.material as MeshBasicMaterial).opacity = o;
    });

    // 6. not sure: candidate codes float up
    const doubt = bump(p, 0.65, 0.68, 0.73, 0.76);
    this.tags.forEach((m, k) => {
      m.visible = doubt > 0.01;
      m.position.set(2.2 + k * 2.7, 7.5 + Math.sin(time * 1.3 + k) * 0.08 + (1 - doubt) * 0.8, -2);
      (m.material as MeshBasicMaterial).opacity = doubt;
    });

    // 7. truck in, container loaded, gate opens green, truck leaves the port
    this.truck.visible = p > 0.77;
    this.truck.position.x = truckX;
    const roll = truckX / 0.5;
    this.wheels.forEach((w) => { w.rotation.z = -roll; });
    this.barrier.rotation.x = track(p, [[0.86, 0], [0.885, 1.35]]);
    const lamp = new Color(T.ink2).lerp(new Color(T.warn), bump(p, 0.64, 0.67, 0.74, 0.77)).lerp(new Color(T.ok), ramp(p, 0.78, 0.8));
    this.light.color.copy(lamp);

    // gulls circle slowly
    this.gulls.forEach((g, k) => {
      const ang = time * 0.12 + k * 1.1;
      g.position.set(-8 + Math.cos(ang) * (16 + k * 3), 15 + k * 1.4 + Math.sin(time * 0.7 + k) * 0.6, -18 + Math.sin(ang) * 8);
      g.rotation.y = -ang;
      g.scale.y = 0.6 + Math.sin(time * 5 + k) * 0.5;
    });

    // camera along keyframes, with a slow breathing drift
    let i = 0;
    while (i < CAMERA.length - 2 && p > CAMERA[i + 1]![0]) i++;
    const ka = CAMERA[i]!, kb = CAMERA[i + 1]!;
    const cu = ramp(p, ka[0], kb[0]);
    const portrait = this.camera.aspect < 1 ? (1 - this.camera.aspect) * 9 : 0;
    this.camera.position.set(
      lerp(ka[1][0], kb[1][0], cu) + Math.sin(time * 0.25) * 0.15,
      lerp(ka[1][1], kb[1][1], cu) + Math.sin(time * 0.31) * 0.08,
      lerp(ka[1][2], kb[1][2], cu) + portrait,
    );
    this.look.set(lerp(ka[2][0], kb[2][0], cu), lerp(ka[2][1], kb[2][1], cu), lerp(ka[2][2], kb[2][2], cu));
    this.camera.lookAt(this.look);
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
    this.ship = new Group(); this.hero = new Group(); this.trolley = new Group(); this.spreader = new Group();
    this.truck = new Group(); this.barrier = new Group(); this.waves = new Group();
    this.slabs = []; this.sheets = []; this.tags = []; this.wheels = []; this.gulls = []; this.labels = [];
  }

  dispose() {
    this.stop();
    this.disposeWorld();
    this.renderer.dispose();
  }
}
