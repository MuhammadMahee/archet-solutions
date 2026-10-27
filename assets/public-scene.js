import * as THREE from './public-three.module.min.js';

// An original, locally rendered architectural set: retail on the left,
// software on the right. No remote models, textures, or runtime dependencies.
const canvas = document.querySelector('#world');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(pointer: fine)');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
} catch (_) {
  document.body.classList.add('webgl-unavailable');
  window.dispatchEvent(new Event('scene-ready'));
}

if (renderer) {
  renderer.setClearColor(0x050b10);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x050b10, .013);
  const camera = new THREE.PerspectiveCamera(42, 1, .1, 160);
  scene.add(new THREE.HemisphereLight(0xb9dce9, 0x17202c, 2.6));
  const key = new THREE.DirectionalLight(0xffe5bc, 3.8);
  key.position.set(-8, 14, 10); scene.add(key);
  const fill = new THREE.DirectionalLight(0x79dcff, 2.4);
  fill.position.set(10, 9, -4); scene.add(fill);
  const retailLight = new THREE.PointLight(0xffc58b, 12, 15, 1.4);
  retailLight.position.set(-5, 4.4, .5); scene.add(retailLight);
  const studioLight = new THREE.PointLight(0x8bd9ec, 10, 15, 1.4);
  studioLight.position.set(5, 4.4, .5); scene.add(studioLight);

  // Soft studio environment makes the phone edges and architecture readable.
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(0x25333e);
  for (const [x, y, z, w, h, color] of [
    [-8, 8, 4, 8, 12, 0xffddb0], [9, 5, 2, 6, 10, 0x8be1ff], [0, 12, -4, 16, 5, 0xe7f7ff],
  ]) {
    const panel = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide }));
    panel.position.set(x, y, z); panel.lookAt(0, 0, 0); studio.add(panel);
  }
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromScene(studio, .12);
  scene.environment = environment.texture; pmrem.dispose();
  studio.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });

  const material = (color, metalness = .25, roughness = .5) => new THREE.MeshStandardMaterial({ color, metalness, roughness });
  const charcoal = material(0x17232b, .65, .32);
  const stone = material(0x606e71, .18, .55);
  const pale = material(0xbbc7c1, .35, .3);
  const dark = material(0x080f16, .4, .34);
  const brass = material(0xb99a60, .78, .25);
  const wood = material(0x7a5140, .1, .67);
  const teal = material(0x256477, .5, .35);
  const leaf = material(0x244d40, .05, .8);
  const glow = color => new THREE.MeshBasicMaterial({ color, toneMapped: false });
  const warm = glow(0xffc578), cool = glow(0x76d9e9), white = glow(0xe3efec);
  const glass = new THREE.MeshPhysicalMaterial({ color: 0x70b9c7, metalness: .3, roughness: .12, transparent: true, opacity: .1, depthWrite: false, side: THREE.DoubleSide });
  const unitBox = new THREE.BoxGeometry(1, 1, 1);
  const unitCylinder = new THREE.CylinderGeometry(1, 1, 1, 16);
  const building = new THREE.Group(); scene.add(building);
  function box(x, y, z, w, h, d, mat, parent = building) {
    const mesh = new THREE.Mesh(unitBox, mat);
    mesh.position.set(x, y, z); mesh.scale.set(w, h, d); parent.add(mesh); return mesh;
  }
  function cylinder(x, y, z, radius, height, mat, parent = building) {
    const mesh = new THREE.Mesh(unitCylinder, mat);
    mesh.position.set(x, y, z); mesh.scale.set(radius, height, radius); parent.add(mesh); return mesh;
  }
  function texture(draw, width = 1024, height = 512) {
    const surface = document.createElement('canvas'); surface.width = width; surface.height = height;
    draw(surface.getContext('2d'), width, height);
    const map = new THREE.CanvasTexture(surface); map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy()); return map;
  }
  function screen(x, y, z, w, h, map, parent = building) {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map, toneMapped: false }));
    mesh.position.set(x, y, z); parent.add(mesh); return mesh;
  }
  function sign(title, subtitle, color) {
    return texture((ctx, w, h) => {
      ctx.fillStyle = '#101c24'; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = color; ctx.fillRect(62, 88, 60, 5);
      ctx.font = '500 66px Arial'; ctx.fillText(title, 60, 200);
      ctx.font = '22px Arial'; ctx.fillStyle = '#97b0b8'; ctx.fillText(subtitle, 64, 270);
      ctx.fillStyle = color; ctx.font = '18px Arial'; ctx.fillText('A R C H E T   /   S O L U T I O N S', 64, 422);
    });
  }
  const phoneMaps = ['#4ac9d3', '#b895e5', '#e5a568'].map((color, variant) => texture((ctx, w, h) => {
    const gradient = ctx.createLinearGradient(0, 0, w, h);
    gradient.addColorStop(0, '#111b36'); gradient.addColorStop(.5, color); gradient.addColorStop(1, '#091521');
    ctx.fillStyle = gradient; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = '#ffffff55'; ctx.lineWidth = 3;
    for (let i = 0; i < 6; i++) { ctx.beginPath(); ctx.ellipse(w * .8, h * .7, 80 + i * 31, 160 + i * 40, -.5, 0, Math.PI * 2); ctx.stroke(); }
    ctx.fillStyle = '#ffffff'; ctx.textAlign = 'center'; ctx.font = '300 66px Arial'; ctx.fillText('09:41', w / 2, 153);
    ctx.font = '15px Arial'; ctx.fillText('DESIGNED TO CONNECT', w / 2, 188);
    ctx.fillStyle = '#05111b'; ctx.beginPath(); ctx.roundRect(w / 2 - 35, 17, 70, 17, 12); ctx.fill();
    ctx.fillStyle = '#ffffffcc'; ctx.fillRect(w / 2 - 35, h - 22, 70, 4);
  }, 256, 512));
  const codeMap = texture((ctx, w, h) => {
    ctx.fillStyle = '#091821'; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#162e3b'; ctx.fillRect(0, 0, w, 48); ctx.fillRect(0, 48, 175, h);
    ['#e99580', '#e8c47a', '#80d8c3'].forEach((c, i) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(24 + i * 22, 24, 5, 0, Math.PI * 2); ctx.fill(); });
    ctx.font = '18px monospace'; ctx.fillStyle = '#b2cbd1'; ctx.fillText('archet / workspace', 220, 31);
    const lines = ['// Build something that works.', 'const experience = {', '  strategy: "human-first",', '  design: "intentional",', '  technology: "connected"', '};', '', 'function createPossibility() {', '  return ideas.map(build);', '}', '', 'export default experience;'];
    lines.forEach((line, i) => { ctx.fillStyle = '#3a5867'; ctx.fillText(String(i + 1).padStart(2, '0'), 205, 92 + i * 31); ctx.fillStyle = ['#87dcca', '#b3a0eb', '#dbd1ac'][i % 3]; ctx.fillText(line, 250, 92 + i * 31); });
    ctx.fillStyle = '#597987'; ['EXPLORER', 'src', '  components', '  studio', '  design', 'assets'].forEach((t, i) => ctx.fillText(t, 18, 90 + i * 32));
  });
  const designMap = texture((ctx, w, h) => {
    ctx.fillStyle = '#17212e'; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#253446'; ctx.fillRect(0, 0, 125, h); ctx.fillRect(0, 0, w, 40);
    ctx.fillStyle = '#e6e7db'; ctx.fillRect(185, 82, 480, 365);
    ctx.fillStyle = '#243d3e'; ctx.font = 'bold 50px Arial'; ctx.fillText('Ideas into', 218, 173); ctx.fillText('experiences.', 218, 229);
    ctx.fillStyle = '#2a7d78'; ctx.fillRect(218, 274, 150, 32);
    for (let i = 0; i < 3; i++) { ctx.fillStyle = ['#9dc9bd', '#c2a86d', '#344d5b'][i]; ctx.fillRect(218 + i * 130, 340, 110, 72); ctx.fillRect(730, 100 + i * 103, 190, 80); }
  });

  // The shared plinth and inset floor lights visually connect the two wings.
  box(0, -.55, 0, 20, .7, 11.4, charcoal);
  box(0, -.15, 0, 19.6, .15, 11, stone);
  box(-5, -.055, .2, 9, .035, 9.8, material(0x403b34, .4, .4));
  box(5, -.055, .2, 9, .035, 9.8, material(0x243743, .55, .28));
  box(0, -.38, 5.72, 19.7, .035, .025, warm);
  box(0, -.92, 6.1, 16, .15, .8, charcoal);
  box(0, -1.1, 6.7, 14, .15, .6, charcoal);
  for (let x = -9; x <= 9; x += 1.5) box(x, -.026, .2, .012, .009, 10, charcoal);
  for (let z = -4.5; z <= 5; z += 1.5) box(0, -.023, z, 19, .009, .012, charcoal);
  box(0, 2.6, -4.95, 19.5, 5.3, .22, charcoal);
  box(-9.65, 2.6, -.25, .2, 5.3, 9.4, charcoal);
  box(9.65, 2.6, -.25, .2, 5.3, 9.4, charcoal);
  // A deliberately open roof keeps the interior visible along the camera path.
  for (const x of [-9.6, 0, 9.6]) {
    box(x, 2.65, 4.65, .12, 5.4, .12, brass);
    box(x, 5.32, -.1, .14, .16, 9.65, charcoal);
    box(x, 5.24, -.1, .075, .09, 9.5, x < 0 ? warm : cool);
  }
  box(0, 5.32, 4.65, 19.4, .16, .16, charcoal);
  box(0, 5.24, 4.74, 19.1, .07, .045, white);
  box(0, 5.32, -4.7, 19.4, .16, .16, charcoal);
  for (const x of [-7.2, -4.8, -2.4, 2.4, 4.8, 7.2]) {
    box(x, 5.3, -1.8, .075, .1, 5.8, charcoal);
    box(x, 5.36, -1.8, .055, .035, 5.65, x < 0 ? warm : cool);
  }
  for (const z of [-3.3, -.8, 1.7]) {
    box(0, 2.55, z, .04, 4.9, 2.4, glass);
    box(0, 2.55, z - 1.2, .07, 5, .06, brass);
  }
  // Rear showroom: illuminated phone bays, branding, and oak wall slats.
  for (let x = -9.3; x < -.5; x += .28) box(x, 2.55, -4.78, .075, 5.1, .1, wood);
  box(-5.2, 3.4, -4.62, 5.7, 2.65, .15, dark);
  screen(-5.2, 3.4, -4.53, 5.5, 2.55, sign('THE MOBILE STORE', 'CONNECTED DEVICES. ENDLESS POSSIBILITY.', '#edc58c'));
  screen(5.1, 3.65, -4.81, 5.8, 2.6, sign('THE DESIGN STUDIO', 'SOFTWARE / INTERFACES / DIGITAL EXPERIENCES', '#80dfe2'));
  function phone(x, y, z, variant, parent = building) {
    const group = new THREE.Group(); group.position.set(x, y, z); group.rotation.x = -.12; parent.add(group);
    box(0, 0, 0, .43, .87, .065, variant === 2 ? brass : charcoal, group);
    screen(0, 0, .035, .385, .8, phoneMaps[variant], group);
    box(0, -.45, -.035, .15, .08, .22, pale, group);
  }
  for (const z of [-1.7, 2.1]) {
    box(-5.1, .66, z, 5.6, 1.3, 1.45, charcoal);
    box(-5.1, 1.34, z, 5.85, .13, 1.65, pale);
    box(-5.1, .12, z + .74, 5.3, .04, .025, warm);
    for (let i = 0; i < 5; i++) {
      const x = -7.25 + i * 1.06;
      box(x, 1.44, z, .74, .07, .62, dark);
      phone(x, 1.96, z, i % 3);
      box(x, 1.423, z + .52, .3, .008, .13, white);
    }
  }
  for (let i = 0; i < 3; i++) {
    box(-9.45, 1.6 + i * 1.03, -.3, .6, .06, 5.4, pale);
    box(-9.11, 1.58 + i * 1.03, -.3, .025, .035, 5.3, warm);
    for (let j = 0; j < 5; j++) box(-9.4, 1.93 + i * 1.03, -2.3 + j, .28, .55, .38, j % 2 ? pale : teal);
  }
  // Office: paired workbenches, code and design screens, keyboards and chairs.
  function monitor(x, y, z, map) {
    box(x, y, z, 1.72, 1.05, .09, dark);
    screen(x, y, z + .052, 1.62, .94, map);
    box(x, y - .65, z, .09, .3, .12, charcoal);
    box(x, y - .8, z + .04, .55, .035, .35, charcoal);
  }
  for (const z of [-1.85, 1.9]) {
    box(5.05, 1.35, z, 6.35, .14, 1.65, wood);
    for (const x of [2.2, 7.9]) {
      box(x, .65, z, .1, 1.3, 1.25, charcoal);
      box(x, .09, z, .7, .08, 1.4, charcoal);
    }
    for (const [i, x] of [3.45, 6.55].entries()) {
      monitor(x, 2.2, z - .34, i ? designMap : codeMap);
      box(x, 1.455, z + .37, .95, .04, .32, dark);
      for (let row = 0; row < 3; row++) for (let col = 0; col < 11; col++) box(x - .4 + col * .078, 1.48, z + .28 + row * .08, .055, .007, .047, stone);
      box(x + .72, 1.45, z + .36, .14, .06, .22, pale);
      cylinder(x - .9, 1.58, z + .25, .1, .3, pale);
      cylinder(x, .48, z + 1.45, .055, .75, charcoal);
      box(x, .88, z + 1.45, .87, .15, .8, teal);
      box(x, 1.42, z + 1.78, .87, 1.1, .12, teal);
      for (const angle of [0, Math.PI / 3, -Math.PI / 3]) {
        const foot = box(x, .15, z + 1.45, 1.05, .06, .06, charcoal); foot.rotation.y = angle;
      }
    }
  }
  function plant(x, z) {
    cylinder(x, .34, z, .3, .65, stone);
    for (let i = 0; i < 7; i++) {
      const angle = i * 2.4;
      const stem = box(x + Math.sin(angle) * .12, 1.05, z + Math.cos(angle) * .12, .025, 1.1, .025, wood);
      stem.rotation.z = Math.sin(angle) * .15;
      const frond = new THREE.Mesh(new THREE.SphereGeometry(1, 8, 6), leaf);
      frond.position.set(x + Math.sin(angle) * .22, 1.55 + (i % 3) * .13, z + Math.cos(angle) * .22);
      frond.scale.set(.19, .52, .11); frond.rotation.z = Math.sin(angle) * .65; building.add(frond);
    }
  }
  plant(-8.7, 3.9); plant(8.75, -3.8); plant(.9, 3.9);
  // Ground pools and a distant skyline give the architecture depth.
  box(0, -1.3, 0, 180, .1, 180, material(0x070f18, .65, .32), scene);
  const poolMap = texture((ctx, w, h) => {
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
    g.addColorStop(0, '#ffffff44'); g.addColorStop(.4, '#ffffff18'); g.addColorStop(1, '#ffffff00');
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  }, 256, 256);
  for (const [x, color] of [[-5, 0xe9a95e], [5, 0x409dba]]) {
    const pool = new THREE.Mesh(new THREE.PlaneGeometry(22, 22), new THREE.MeshBasicMaterial({ map: poolMap, color, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    pool.rotation.x = -Math.PI / 2; pool.position.set(x, -1.23, 2); scene.add(pool);
  }
  for (let i = 0; i < 20; i++) {
    const x = (i - 9.5) * 4.8, height = 2 + (i * 7 % 9);
    box(x, height / 2 - 1.2, -22 - (i % 3) * 4, 2.6, height, 3.5, dark, scene);
  }
  // Batch the static architecture (including keyboard keys and wall slats).
  // Hundreds of individual details become a handful of GPU draw calls.
  scene.updateMatrixWorld(true);
  const batches = new Map();
  scene.traverse(object => {
    if (object.geometry !== unitBox && object.geometry !== unitCylinder) return;
    const key = `${object.geometry.uuid}:${object.material.uuid}`;
    if (!batches.has(key)) batches.set(key, []);
    batches.get(key).push(object);
  });
  for (const objects of batches.values()) {
    const batch = new THREE.InstancedMesh(objects[0].geometry, objects[0].material, objects.length);
    objects.forEach((object, i) => { batch.setMatrixAt(i, object.matrixWorld); object.removeFromParent(); });
    batch.instanceMatrix.needsUpdate = true; scene.add(batch);
  }
  const dustPositions = new Float32Array(110 * 3);
  let seed = 47;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < dustPositions.length; i += 3) {
    dustPositions[i] = (random() - .5) * 38; dustPositions[i + 1] = random() * 12; dustPositions[i + 2] = (random() - .5) * 26;
  }
  const dustGeometry = new THREE.BufferGeometry(); dustGeometry.setAttribute('position', new THREE.BufferAttribute(dustPositions, 3));
  const dust = new THREE.Points(dustGeometry, new THREE.PointsMaterial({ color: 0xb5d4d6, size: .028, transparent: true, opacity: .4, depthWrite: false })); scene.add(dust);

  // Scroll selects a shot; exponential interpolation gives a gentle dolly move.
  const shots = [
    ['#top', [21, 15, 27], [-2.4, 1.6, 0]],
    ['#approach', [15, 10, 25], [-2, 1.4, 0]],
    ['#brands', [-17, 10, 22], [-4, 1.8, -.5]],
    ['#services', [-12, 7.7, 18], [-4, 1.4, -.8]],
    ['#studio-tour', [13, 9, 18], [3, 1.6, -.5]],
    ['#digital', [15, 8, 19], [4, 1.5, -.5]],
    ['#contact', [22, 16, 29], [0, 1, 0]],
  ].map(([selector, position, target]) => ({ element: document.querySelector(selector), position: new THREE.Vector3(...position), target: new THREE.Vector3(...target), top: 0 })).filter(shot => shot.element);
  const desiredPosition = new THREE.Vector3(), desiredTarget = new THREE.Vector3();
  const basePosition = shots[0].position.clone(), look = shots[0].target.clone();
  const pointer = new THREE.Vector2(), smoothPointer = new THREE.Vector2();
  let active = !document.body.classList.contains('is-loading');
  let lost = false, frame = 0, lastTime = null, elapsed = 0;
  let mobile = innerWidth < 700;
  function chooseShot() {
    const progress = reduced.matches ? 0 : scrollY;
    let index = 0;
    while (index < shots.length - 2 && progress >= shots[index + 1].top) index++;
    const from = shots[index], to = shots[Math.min(index + 1, shots.length - 1)];
    let t = THREE.MathUtils.clamp((progress - from.top) / Math.max(1, to.top - from.top), 0, 1);
    t = t * t * (3 - 2 * t);
    desiredPosition.lerpVectors(from.position, to.position, t);
    desiredTarget.lerpVectors(from.target, to.target, t);
    if (mobile) {
      desiredTarget.y += 3.3;
      desiredTarget.x = 0;
      desiredPosition.copy(desiredTarget).add(new THREE.Vector3(32, 25, 48));
    }
  }
  function draw(delta = 0, snap = false) {
    const motion = !reduced.matches;
    if (motion || snap) {
      chooseShot();
      const ease = snap ? 1 : 1 - Math.exp(-delta * 2.4);
      basePosition.lerp(desiredPosition, ease); look.lerp(desiredTarget, ease);
      smoothPointer.lerp(pointer, ease);
    }
    camera.position.copy(basePosition);
    if (motion) {
      camera.position.x += Math.sin(elapsed * .13) * .65 + smoothPointer.x * .5;
      camera.position.y += Math.sin(elapsed * .17) * .22 + smoothPointer.y * .22;
      dust.rotation.y = elapsed * .009;
    }
    camera.lookAt(look); renderer.render(scene, camera);
  }
  function resize() {
    mobile = innerWidth < 700;
    renderer.setPixelRatio(Math.min(devicePixelRatio, mobile ? 1.25 : 1.5));
    renderer.setSize(innerWidth, innerHeight);
    camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    shots.forEach(shot => { shot.top = shot.element.getBoundingClientRect().top + scrollY; });
    if (!lost) draw(0, true);
  }
  function tick(time) {
    frame = 0;
    if (!active || document.hidden || lost || reduced.matches) return;
    const delta = lastTime === null ? 0 : Math.min((time - lastTime) / 1000, .05);
    lastTime = time; elapsed += delta; draw(delta); frame = requestAnimationFrame(tick);
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
  new ResizeObserver(() => { shots.forEach(shot => { shot.top = shot.element.getBoundingClientRect().top + scrollY; }); }).observe(document.querySelector('main'));
  addEventListener('experience-enter', () => { active = true; resize(); start(); }, { once: true });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else start();
  });
  reduced.addEventListener('change', () => {
    cancelAnimationFrame(frame); frame = 0;
    if (!lost) draw(0, true); start();
  });
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault(); lost = true; cancelAnimationFrame(frame); frame = 0;
    document.body.classList.remove('webgl-ready');
    document.body.classList.add('webgl-unavailable');
  });
  canvas.addEventListener('webglcontextrestored', () => {
    lost = false; resize(); document.body.classList.add('webgl-ready');
    document.body.classList.remove('webgl-unavailable');
    start();
  });
  resize(); document.body.classList.add('webgl-ready');
  window.dispatchEvent(new Event('scene-ready')); start();
}
