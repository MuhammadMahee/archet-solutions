import * as THREE from './public-three.module.min.js';

// A floating sculpture of Archet's original mark. A fixed camera and one
// continuous motion keep the letter, globe, bars, and ribbon visually unified.
const canvas = document.querySelector('#world');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(pointer: fine)');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'low-power' });
} catch (_) {
  document.body.classList.add('webgl-unavailable');
  window.dispatchEvent(new Event('scene-ready'));
}
if (renderer) {
  renderer.setClearColor(0x061219);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, .1, 60);
  camera.position.set(0, 0, 14);
  scene.add(new THREE.HemisphereLight(0xcef9f5, 0x0b2737, 1.5));
  function light(color, intensity, x, y, z) {
    const source = new THREE.DirectionalLight(color, intensity);
    source.position.set(x, y, z); scene.add(source);
  }
  light(0xfff2df, 3, -3, 5, 6);
  light(0x75bac9, 1.5, 5, -2, 3);
  light(0xffdfa0, 3, 3, 4, -3);
  const teal = new THREE.MeshStandardMaterial({ color: 0x188b98, metalness: .52, roughness: .28 });
  const tealEdge = new THREE.MeshStandardMaterial({ color: 0x084a59, metalness: .65, roughness: .25 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xe6ab35, metalness: .82, roughness: .23, envMapIntensity: 1.2 });
  // Broad studio reflections give the bevels and ribbon a metallic finish.
  // Generate this once locally; no network texture or postprocessing passes.
  const studio = new THREE.Scene(); studio.background = new THREE.Color(0x17232b);
  for (const [x, y, z, width, height, color] of [
    [-4, 3, 5, 3, 7, 0xfff5df], [4, 1, 3, 2, 6, 0xa6d8e3],
    [0, 6, -2, 8, 3, 0xffe5ac], [-2, -4, 2, 6, 1, 0x465a67],
  ]) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }));
    panel.position.set(x, y, z); panel.lookAt(0, 0, 0); studio.add(panel);
  }
  const environment = new THREE.PMREMGenerator(renderer);
  scene.environment = environment.fromScene(studio, .06).texture;
  environment.dispose();
  studio.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
  const rig = new THREE.Group(); scene.add(rig);
  const emblem = new THREE.Group(); rig.add(emblem);
  function mesh(geometry, material, parent = emblem) {
    const object = new THREE.Mesh(geometry, material); parent.add(object); return object;
  }
  function extrude(points, depth, bevel, material) {
    const shape = new THREE.Shape();
    points.forEach(([x, y], i) => i ? shape.lineTo(x, y) : shape.moveTo(x, y));
    shape.closePath();
    const geometry = new THREE.ExtrudeGeometry(shape, {
      depth, steps: 1, bevelEnabled: true, bevelSegments: 3,
      bevelSize: bevel, bevelThickness: bevel,
    });
    geometry.translate(0, 0, -depth / 2);
    return mesh(geometry, material);
  }
  // The actual mark has a sharp apex and an open center. Its gold sweep
  // supplies the cross stroke, instead of a generic block-letter crossbar.
  const letter = extrude([
    [-1.74, -1.9], [-.98, -1.9], [0, .55], [1.03, -1.9],
    [1.76, -1.9], [0, 2.05],
  ], .42, .035, [teal, tealEdge]);
  letter.position.set(-.22, -.18, .25);
  const facet = new THREE.Shape();
  facet.moveTo(-1.74, -1.9); facet.lineTo(-1.43, -1.9);
  facet.lineTo(0, 1.57); facet.lineTo(0, 2.05); facet.closePath();
  const face = mesh(new THREE.ShapeGeometry(facet), new THREE.MeshStandardMaterial({ color: 0x258fa7, metalness: .45, roughness: .3 }));
  face.position.copy(letter.position); face.position.z += .248;

  // Sparse globe arcs remain behind the letter and move with the whole mark.
  const globe = new THREE.Group(); globe.position.set(-.12, .55, -.72); emblem.add(globe);
  const globeMaterial = new THREE.MeshBasicMaterial({ color: 0x31a9aa, transparent: true, opacity: .34 });
  function arc(points, radius = .009) {
    return mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), 96, radius, 5, false), globeMaterial, globe);
  }
  const radius = 2.08;
  arc(Array.from({ length: 97 }, (_, i) => {
    const angle = i / 96 * Math.PI * 2;
    return new THREE.Vector3(Math.cos(angle) * radius, Math.sin(angle) * radius, 0);
  }), .013);
  for (const width of [.42, .78]) {
    arc(Array.from({ length: 97 }, (_, i) => {
      const angle = i / 96 * Math.PI * 2;
      return new THREE.Vector3(Math.sin(angle) * radius * width, Math.cos(angle) * radius, -.12 * Math.sin(angle));
    }));
  }
  for (const y of [-.85, 0, .85]) {
    const half = Math.sqrt(radius * radius - y * y);
    arc(Array.from({ length: 49 }, (_, i) => {
      const t = i / 48;
      return new THREE.Vector3((t * 2 - 1) * half, y + Math.sin(t * Math.PI) * .23, .02);
    }));
  }
  [.58, 1.02, 1.48].forEach((height, i) => {
    const bar = extrude([[-.16, 0], [.16, 0], [.16, height], [-.16, height]], .2, .018, [teal, tealEdge]);
    bar.position.set(.12 + i * .48, -.6, .08);
  });

  // A tapered ribbon replaces the thin tube, arrow, and jumping light tracer.
  const ribbonCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(-2.02, -.75, -.4),
    new THREE.Vector3(-2.28, -1.45, .05),
    new THREE.Vector3(-1.15, -1.22, .8),
    new THREE.Vector3(.25, -.6, .9),
    new THREE.Vector3(1.65, .02, .6),
    new THREE.Vector3(2.45, .8, .1),
    new THREE.Vector3(2.55, 1.25, -.15),
  ]);
  const positions = [], indices = [];
  const up = new THREE.Vector3(0, 0, 1);
  for (let i = 0; i <= 120; i++) {
    const t = i / 120;
    const center = ribbonCurve.getPoint(t);
    const side = new THREE.Vector3().crossVectors(up, ribbonCurve.getTangent(t)).normalize();
    const width = .012 + .18 * Math.pow(Math.sin(Math.PI * t), 1.1);
    for (const [edge, depth] of [[-1, -.023], [1, -.023], [-1, .023], [1, .023]]) {
      const point = center.clone().addScaledVector(side, width * edge);
      positions.push(point.x, point.y, point.z + depth);
    }
    if (i < 120) {
      const a = i * 4, b = a + 4;
      indices.push(a, b + 1, b, a, a + 1, b + 1);
      indices.push(a + 2, b + 2, b + 3, a + 2, b + 3, a + 3);
      indices.push(a, b, b + 2, a, b + 2, a + 2);
      indices.push(a + 1, a + 3, b + 3, a + 1, b + 3, b + 1);
    }
  }
  indices.push(0, 2, 3, 0, 3, 1, 480, 481, 483, 480, 483, 482);
  const ribbonGeometry = new THREE.BufferGeometry();
  ribbonGeometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  ribbonGeometry.setIndex(indices); ribbonGeometry.computeVertexNormals();
  mesh(ribbonGeometry, gold);
  const endpoint = mesh(new THREE.SphereGeometry(.07, 20, 12), gold);
  endpoint.position.copy(ribbonCurve.getPoint(1));

  const glowCanvas = document.createElement('canvas'); glowCanvas.width = glowCanvas.height = 128;
  const ctx = glowCanvas.getContext('2d');
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, '#208b893c'); gradient.addColorStop(.4, '#17697a20'); gradient.addColorStop(1, '#06121900');
  ctx.fillStyle = gradient; ctx.fillRect(0, 0, 128, 128);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(glowCanvas), depthWrite: false, transparent: true, blending: THREE.AdditiveBlending }));
  halo.position.z = -2; halo.scale.set(9, 9, 1); rig.add(halo);

  let active = !document.body.classList.contains('is-loading');
  let lost = false, frame = 0, lastTime = null, elapsed = 0;
  const pointer = new THREE.Vector2();
  const smoothedPointer = new THREE.Vector2();
  function draw(delta = 0) {
    smoothedPointer.lerp(pointer, 1 - Math.exp(-delta * 2.6));
    const motion = reduced.matches ? 0 : 1;
    const phase = elapsed * Math.PI * 2 / 28;
    emblem.rotation.set(
      .025 + motion * (Math.sin(phase * .7) * .018 - smoothedPointer.y * .025),
      -.26 + motion * (Math.sin(phase) * .07 + smoothedPointer.x * .045),
      -.025 + motion * Math.sin(phase * .6) * .008,
    );
    emblem.position.y = motion * Math.sin(phase) * .045;
    renderer.render(scene, camera);
  }
  function resize() {
    const mobile = innerWidth < 700;
    renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.25 : 1.5));
    renderer.setSize(innerWidth, innerHeight);
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    const height = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.position.z;
    const width = height * camera.aspect;
    const scale = mobile ? Math.min(.57, width * .72 / 4.9) : Math.min(1.02, width * .42 / 4.9);
    rig.scale.setScalar(scale);
    rig.position.set(mobile ? 0 : width * .235, mobile ? -height * .33 : height * .04, 0);
    if (!lost) draw();
  }
  function tick(time) {
    frame = 0;
    if (!active || document.hidden || lost || reduced.matches) return;
    const delta = lastTime === null ? 0 : Math.min((time - lastTime) / 1000, .05);
    lastTime = time; elapsed += delta; draw(delta);
    frame = requestAnimationFrame(tick);
  }
  function start() {
    if (!frame && active && !document.hidden && !lost && !reduced.matches) {
      lastTime = null; frame = requestAnimationFrame(tick);
    }
  }
  addEventListener('pointermove', event => {
    if (finePointer.matches && event.pointerType !== 'touch') pointer.set(event.clientX / innerWidth * 2 - 1, 1 - event.clientY / innerHeight * 2);
  }, { passive: true });
  document.documentElement.addEventListener('pointerleave', () => pointer.set(0, 0));
  addEventListener('resize', resize);
  addEventListener('experience-enter', () => { active = true; start(); }, { once: true });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else start();
  });
  reduced.addEventListener('change', () => {
    cancelAnimationFrame(frame); frame = 0;
    if (!lost) draw(); start();
  });
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault(); lost = true; cancelAnimationFrame(frame); frame = 0;
    document.body.classList.remove('webgl-ready');
  });
  canvas.addEventListener('webglcontextrestored', () => {
    lost = false; resize(); document.body.classList.add('webgl-ready'); start();
  });
  resize();
  document.body.classList.add('webgl-ready');
  window.dispatchEvent(new Event('scene-ready'));
  start();
}
