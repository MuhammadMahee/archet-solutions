import * as THREE from './public-three.module.min.js';

// Archet's logo becomes an observatory: a dimensional A, globe, growth bars,
// and a golden trajectory. All geometry and light textures are local.
const canvas = document.querySelector('#world');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: innerWidth > 700, alpha: false, powerPreference: 'low-power' });
} catch (_) {
  document.body.classList.add('webgl-unavailable');
  window.dispatchEvent(new Event('scene-ready'));
}
if (renderer) {
  renderer.setClearColor(0x061219);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.25;
  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x061219, .025);
  const camera = new THREE.PerspectiveCamera(40, innerWidth / innerHeight, .1, 100);
  scene.add(new THREE.HemisphereLight(0xa4fff0, 0x062432, 2.2));
  const key = new THREE.DirectionalLight(0xd7fff6, 4); key.position.set(3, 8, 6); scene.add(key);
  const rim = new THREE.DirectionalLight(0xe6bd54, 3); rim.position.set(-4, 3, -4); scene.add(rim);
  const teal = new THREE.MeshStandardMaterial({ color: 0x149b9c, metalness: .7, roughness: .27, emissive: 0x0a5051, emissiveIntensity: .45 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xddba4d, metalness: .65, roughness: .25, emissive: 0xbd8219, emissiveIntensity: .4 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x0a252e, metalness: .7, roughness: .4 });
  const lineMaterial = new THREE.LineBasicMaterial({ color: 0x55d6c9, transparent: true, opacity: .32 });
  const brightLine = new THREE.LineBasicMaterial({ color: 0x8affde, transparent: true, opacity: .7 });
  function mesh(geometry, material, parent = scene) { const object = new THREE.Mesh(geometry, material); parent.add(object); return object; }
  function line(points, material, parent = scene) { const object = new THREE.Line(new THREE.BufferGeometry().setFromPoints(points), material); parent.add(object); return object; }
  function circle(radius, y = 0) { return Array.from({ length: 129 }, (_, i) => { const angle = i / 128 * Math.PI * 2; return new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius); }); }
  const engine = new THREE.Group(); engine.position.set(2.5, 3.25, 0); scene.add(engine);
  const monument = new THREE.Group(); engine.add(monument);
  const outline = new THREE.Shape();
  outline.moveTo(-1.7, -2); outline.lineTo(-.93, -2); outline.lineTo(0, .9); outline.lineTo(.93, -2); outline.lineTo(1.7, -2); outline.lineTo(.4, 2.1); outline.lineTo(-.4, 2.1); outline.closePath();
  const aGeometry = new THREE.ExtrudeGeometry(outline, { depth: .48, bevelEnabled: true, bevelSegments: 3, steps: 1, bevelSize: .055, bevelThickness: .06 });
  aGeometry.translate(0, 0, -.24);
  mesh(aGeometry, teal, monument);
  const crossbar = mesh(new THREE.BoxGeometry(1.7, .38, .48), teal, monument); crossbar.position.set(0, -.8, 0);
  const edge = new THREE.LineSegments(new THREE.EdgesGeometry(aGeometry, 35), brightLine); monument.add(edge);
  const globe = new THREE.Group(); globe.position.z = -.65; engine.add(globe);
  for (let i = 0; i < 9; i++) {
    const longitude = i / 9 * Math.PI;
    line(Array.from({ length: 129 }, (_, j) => {
      const angle = j / 128 * Math.PI * 2;
      return new THREE.Vector3(2.8 * Math.sin(angle) * Math.cos(longitude), 2.8 * Math.cos(angle), 2.8 * Math.sin(angle) * Math.sin(longitude));
    }), lineMaterial, globe);
  }
  for (let i = -3; i <= 3; i++) {
    const y = i * .65; line(circle(Math.sqrt(2.8 ** 2 - y ** 2), y), lineMaterial, globe);
  }
  const bars = new THREE.Group(); bars.position.set(1.6, -2, -.55); engine.add(bars);
  [.8, 1.2, 1.75, 2.45].forEach((height, i) => {
    const bar = mesh(new THREE.BoxGeometry(.28, height, .33), teal, bars); bar.position.set(i * .43, height / 2, 0);
    const cap = mesh(new THREE.BoxGeometry(.29, .035, .34), gold, bars); cap.position.set(i * .43, height, 0);
  });
  const orbitPoints = Array.from({ length: 90 }, (_, i) => {
    const t = i / 89, angle = -Math.PI + t * (Math.PI + .15);
    return new THREE.Vector3(Math.cos(angle) * 3.6, -1.55 + t * 2.8, -Math.sin(angle) * 2.0);
  });
  const orbitCurve = new THREE.CatmullRomCurve3(orbitPoints);
  mesh(new THREE.TubeGeometry(orbitCurve, 128, .035, 7, false), gold, engine);
  const arrow = mesh(new THREE.ConeGeometry(.14, .42, 4), gold, engine);
  arrow.position.copy(orbitCurve.getPoint(1)); arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), orbitCurve.getTangent(1));
  const glowCanvas = document.createElement('canvas'); glowCanvas.width = glowCanvas.height = 64;
  const ctx = glowCanvas.getContext('2d');
  const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  gradient.addColorStop(0, '#fff8cf'); gradient.addColorStop(.12, '#f1ce74dd'); gradient.addColorStop(.4, '#d8a43c44'); gradient.addColorStop(1, '#b5861700');
  ctx.fillStyle = gradient; ctx.fillRect(0, 0, 64, 64);
  const spriteMaterial = new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(glowCanvas), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
  const tracer = new THREE.Sprite(spriteMaterial); tracer.scale.setScalar(.65); engine.add(tracer);
  const floor = mesh(new THREE.PlaneGeometry(160, 160), new THREE.MeshStandardMaterial({ color: 0x071922, metalness: .6, roughness: .55 })); floor.rotation.x = -Math.PI / 2; floor.position.y = -.15;
  const platform = new THREE.Group(); platform.position.x = 2.5; scene.add(platform);
  [4.1, 3.7, 3.3].forEach((radius, i) => {
    const disc = mesh(new THREE.CylinderGeometry(radius, radius + .15, .12, 96), dark, platform); disc.position.y = .07 + i * .14;
    line(circle(radius, .14 + i * .14), i === 2 ? brightLine : lineMaterial, platform);
  });
  for (let i = 0; i < 24; i++) {
    const a = i / 24 * Math.PI * 2;
    line([new THREE.Vector3(Math.cos(a) * 4.4, .01, Math.sin(a) * 4.4), new THREE.Vector3(Math.cos(a) * 11, .01, Math.sin(a) * 11)], lineMaterial, platform);
    if (i % 3 === 0) {
      const height = .35 + (i % 5) * .16;
      const node = mesh(new THREE.BoxGeometry(.18, height, .18), dark, platform); node.position.set(Math.cos(a) * 6, height / 2, Math.sin(a) * 6);
      const light = mesh(new THREE.BoxGeometry(.19, .04, .19), gold, platform); light.position.copy(node.position); light.position.y = height;
    }
  }
  [5, 7.5, 10, 15].forEach(radius => line(circle(radius, .005), lineMaterial, platform));
  const stars = new Float32Array(180 * 3);
  // Deterministic point field keeps the composition stable across visits.
  for (let i = 0; i < 180; i++) { stars[i * 3] = Math.sin(i * 127.1) * 24; stars[i * 3 + 1] = 1 + (Math.sin(i * 63.7) + 1) * 7; stars[i * 3 + 2] = -4 - (Math.cos(i * 23.1) + 1) * 16; }
  const starGeometry = new THREE.BufferGeometry(); starGeometry.setAttribute('position', new THREE.BufferAttribute(stars, 3));
  scene.add(new THREE.Points(starGeometry, new THREE.PointsMaterial({ color: 0x8ce1d5, size: .025, transparent: true, opacity: .45 })));

  let active = !document.body.classList.contains('is-loading'), lost = false, frame = 0, lastTime = 0, elapsed = 0;
  const pointer = new THREE.Vector2(); const target = new THREE.Vector3();
  const sceneWindow = document.querySelector('.scene-window');
  function resize() {
    renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 700 ? 1.35 : 1.7));
    renderer.setSize(innerWidth, innerHeight); camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
    engine.scale.setScalar(innerWidth < 700 ? .82 : 1);
    platform.scale.setScalar(innerWidth < 700 ? .82 : 1);
    if (reduced.matches || !active) draw(0);
  }
  function draw(delta) {
    const mobile = innerWidth < 700;
    const rect = sceneWindow.getBoundingClientRect();
    const showcase = Math.max(0, 1 - Math.abs(rect.top + rect.height / 2 - innerHeight / 2) / innerHeight);
    const tour = reduced.matches ? 0 : Math.min(scrollY / (document.documentElement.scrollHeight - innerHeight || 1), 1);
    const x = mobile ? 2.5 : -1.1 + showcase * 3.6 + Math.sin(tour * Math.PI) * 1.1;
    const y = mobile ? 6 : 5.2 + showcase * 1.5;
    const z = mobile ? 22 : 13.5 - showcase * 2;
    const blend = delta ? 1 - Math.exp(-delta * 3) : 1;
    camera.position.lerp(new THREE.Vector3(x + (reduced.matches ? 0 : pointer.x * .22), y + (reduced.matches ? 0 : pointer.y * .12), z), blend);
    target.set(mobile ? 2.5 : .1 + showcase * 2.4, mobile ? 7.5 : 2.7, 0);
    camera.lookAt(target);
    globe.rotation.y = reduced.matches ? .15 : elapsed * .035;
    monument.rotation.y = -.12;
    tracer.position.copy(orbitCurve.getPoint(reduced.matches ? .72 : (elapsed * .045 + .25) % 1));
    renderer.render(scene, camera);
  }
  function tick(time) {
    frame = 0;
    if (!active || document.hidden || lost || reduced.matches) return;
    if (lastTime && time - lastTime < 1000 / 30) { frame = requestAnimationFrame(tick); return; }
    const delta = lastTime ? Math.min((time - lastTime) / 1000, .05) : 0;
    lastTime = time; elapsed += delta; draw(delta);
    frame = requestAnimationFrame(tick);
  }
  function start() { if (!frame && active && !document.hidden && !lost && !reduced.matches) { lastTime = 0; frame = requestAnimationFrame(tick); } }
  addEventListener('pointermove', event => { pointer.set(event.clientX / innerWidth - .5, .5 - event.clientY / innerHeight); }, { passive: true });
  addEventListener('resize', resize);
  addEventListener('scroll', () => { if (active && reduced.matches && !lost) draw(0); }, { passive: true });
  addEventListener('experience-enter', () => { active = true; draw(0); start(); }, { once: true });
  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(frame); frame = 0; } else start(); });
  reduced.addEventListener('change', () => { cancelAnimationFrame(frame); frame = 0; draw(0); start(); });
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); lost = true; cancelAnimationFrame(frame); frame = 0; document.body.classList.remove('webgl-ready'); });
  canvas.addEventListener('webglcontextrestored', () => { lost = false; draw(0); document.body.classList.add('webgl-ready'); start(); });
  resize();
  document.body.classList.add('webgl-ready');
  window.dispatchEvent(new Event('scene-ready'));
  start();
}
