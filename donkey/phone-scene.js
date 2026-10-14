import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const hero = document.querySelector('#phone');
const stage = document.querySelector('#phone-view');
const canvas = document.querySelector('#phone-canvas');
const progressBar = document.querySelector('#rotation-progress');
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');

// The scene renders only after scroll/resize changes, not in an idle animation loop.
function initializePhone() {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.95;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(33, 1, 0.1, 100);
  camera.position.set(0, 0, 12.5);
  const room = new RoomEnvironment();
  const pmrem = new THREE.PMREMGenerator(renderer);
  const environment = pmrem.fromScene(room, 0.04);
  scene.environment = environment.texture;
  scene.environmentIntensity = 0.85;
  room.dispose();
  pmrem.dispose();

  const key = new THREE.DirectionalLight(0xffe7d1, 2);
  key.position.set(-4, 6, 7);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = key.shadow.camera.bottom = -5;
  key.shadow.camera.right = key.shadow.camera.top = 5;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 25;
  key.shadow.bias = -0.0003;
  key.shadow.normalBias = 0.015;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xc6d8ff, 1.1);
  fill.position.set(5, 1, -5);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xfff7eb, 2.2);
  rim.position.set(3, 6, -3);
  scene.add(rim);

  const phone = new THREE.Group();
  scene.add(phone);
  const metal = new THREE.MeshPhysicalMaterial({ color: 0xb97950, metalness: 1, roughness: 0.24, clearcoat: 0.45, clearcoatRoughness: 0.18 });
  const grainCanvas = document.createElement('canvas');
  grainCanvas.width = grainCanvas.height = 256;
  const grainContext = grainCanvas.getContext('2d');
  const grainPixels = grainContext.createImageData(256, 256);
  let seed = 71;
  for (let i = 0; i < grainPixels.data.length; i += 4) {
    seed = (seed * 16807) % 2147483647;
    const shade = 112 + (seed % 32);
    grainPixels.data[i] = grainPixels.data[i + 1] = grainPixels.data[i + 2] = shade;
    grainPixels.data[i + 3] = 255;
  }
  grainContext.putImageData(grainPixels, 0, 0);
  const grainTexture = new THREE.CanvasTexture(grainCanvas);
  grainTexture.wrapS = grainTexture.wrapT = THREE.RepeatWrapping;
  grainTexture.repeat.set(6, 12);
  const backGlass = new THREE.MeshPhysicalMaterial({ color: 0xb87c56, metalness: 0.35, roughness: 0.3, clearcoat: 0.45, clearcoatRoughness: 0.3, bumpMap: grainTexture, bumpScale: 0.009 });
  const black = new THREE.MeshStandardMaterial({ color: 0x080b10, metalness: 0.35, roughness: 0.27 });
  const lensGlass = new THREE.MeshPhysicalMaterial({ color: 0x152331, metalness: 0.48, roughness: 0.06, clearcoat: 1, clearcoatRoughness: 0.03 });
  const lensInner = new THREE.MeshPhysicalMaterial({ color: 0x02050b, metalness: 0.35, roughness: 0.12, clearcoat: 1 });
  const antenna = new THREE.MeshStandardMaterial({ color: 0x63564d, roughness: 0.65 });

  function roundedShape(width, height, radius) {
    const x = -width / 2;
    const y = -height / 2;
    const shape = new THREE.Shape();
    shape.moveTo(x + radius, y);
    shape.lineTo(x + width - radius, y);
    shape.quadraticCurveTo(x + width, y, x + width, y + radius);
    shape.lineTo(x + width, y + height - radius);
    shape.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    shape.lineTo(x + radius, y + height);
    shape.quadraticCurveTo(x, y + height, x, y + height - radius);
    shape.lineTo(x, y + radius);
    shape.quadraticCurveTo(x, y, x + radius, y);
    return shape;
  }
  function roundedSolid(width, height, depth, radius, material, parent, x = 0, y = 0, z = 0) {
    const geometry = new THREE.ExtrudeGeometry(roundedShape(width, height, radius), { depth, bevelEnabled: true, bevelThickness: 0.025, bevelSize: 0.025, bevelSegments: 4, steps: 1, curveSegments: 18 });
    geometry.translate(0, 0, -depth / 2);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }
  function roundedSurface(width, height, radius, material, parent, x = 0, y = 0, z = 0) {
    const geometry = new THREE.ShapeGeometry(roundedShape(width, height, radius), 32);
    const position = geometry.attributes.position;
    const uv = geometry.attributes.uv;
    for (let i = 0; i < position.count; i++) uv.setXY(i, position.getX(i) / width + 0.5, position.getY(i) / height + 0.5);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }
  function cylinder(radius, depth, material, parent, x, y, z) {
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, depth, 64), material);
    mesh.rotation.x = Math.PI / 2;
    mesh.position.set(x, y, z);
    parent.add(mesh);
    return mesh;
  }

  // A rounded, beveled enclosure with real depth; both faces belong to one model.
  roundedSolid(2.65, 5.65, 0.23, 0.36, metal, phone);
  const rear = new THREE.Group();
  rear.rotation.y = Math.PI;
  phone.add(rear);
  roundedSurface(2.58, 5.58, 0.34, backGlass, rear, 0, 0, 0.145);
  roundedSolid(1.83, 1.81, 0.08, 0.29, backGlass, rear, -0.3, 1.73, 0.21);

  const lensPositions = [[-0.78, 2.12], [-0.78, 1.35], [-0.02, 1.735]];
  const lensCanvas = document.createElement('canvas');
  lensCanvas.width = lensCanvas.height = 256;
  const lensContext = lensCanvas.getContext('2d');
  const opticalGradient = lensContext.createRadialGradient(128, 128, 0, 128, 128, 128);
  [[0, '#010309'], [0.25, '#080f19'], [0.36, '#0e1b2b'], [0.42, '#02070d'], [0.49, '#203a49'], [0.54, '#080f18'], [0.67, '#16252c'], [0.8, '#05080c'], [0.96, '#1c2429'], [1, '#030509']].forEach(([stop, color]) => opticalGradient.addColorStop(stop, color));
  lensContext.fillStyle = opticalGradient;
  lensContext.fillRect(0, 0, 256, 256);
  [[90, 70, 28, 'rgba(117,166,203,.7)'], [151, 169, 18, 'rgba(116,71,174,.32)'], [117, 82, 11, 'rgba(206,221,229,.65)']].forEach(([x, y, radius, color]) => {
    const reflection = lensContext.createRadialGradient(x, y, 0, x, y, radius);
    reflection.addColorStop(0, color);
    reflection.addColorStop(1, 'rgba(8,15,25,0)');
    lensContext.fillStyle = reflection;
    lensContext.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  });
  const opticalTexture = new THREE.CanvasTexture(lensCanvas);
  opticalTexture.colorSpace = THREE.SRGBColorSpace;
  const opticalMaterial = new THREE.MeshPhysicalMaterial({ map: opticalTexture, roughness: 0.16, metalness: 0.25, clearcoat: 0.65, envMapIntensity: 0.3, emissiveMap: opticalTexture, emissive: 0xffffff, emissiveIntensity: 0.15 });
  lensPositions.forEach(([x, y]) => {
    cylinder(0.345, 0.12, metal, rear, x, y, 0.32);
    cylinder(0.305, 0.13, black, rear, x, y, 0.345);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.313, 0.016, 12, 72), metal);
    ring.position.set(x, y, 0.415);
    rear.add(ring);
    cylinder(0.27, 0.02, lensGlass, rear, x, y, 0.414);
    cylinder(0.153, 0.024, lensInner, rear, x, y, 0.431);
    const iris = new THREE.Mesh(new THREE.TorusGeometry(0.16, 0.008, 8, 64), lensGlass);
    iris.position.set(x, y, 0.447);
    rear.add(iris);
    const opticalReflection = new THREE.Mesh(new THREE.CircleGeometry(0.034, 24), new THREE.MeshBasicMaterial({ color: 0x5e8695, transparent: true, opacity: 0.45 }));
    opticalReflection.position.set(x - 0.07, y + 0.08, 0.451);
    rear.add(opticalReflection);
    const opticalFace = new THREE.Mesh(new THREE.CircleGeometry(0.27, 64), opticalMaterial);
    opticalFace.position.set(x, y, 0.456);
    rear.add(opticalFace);
  });
  cylinder(0.12, 0.03, new THREE.MeshPhysicalMaterial({ color: 0xe6d8b6, roughness: 0.35, clearcoat: 1 }), rear, 0.44, 2.13, 0.274);
  cylinder(0.105, 0.035, black, rear, 0.45, 1.4, 0.274);
  cylinder(0.027, 0.02, antenna, rear, 0.46, 1.735, 0.275);

  const markShape = new THREE.Shape();
  markShape.moveTo(0, 0.24); markShape.lineTo(0.08, 0.08); markShape.lineTo(0.24, 0);
  markShape.lineTo(0.08, -0.08); markShape.lineTo(0, -0.24); markShape.lineTo(-0.08, -0.08);
  markShape.lineTo(-0.24, 0); markShape.lineTo(-0.08, 0.08); markShape.closePath();
  const mark = new THREE.Mesh(new THREE.ShapeGeometry(markShape), new THREE.MeshStandardMaterial({ color: 0x956145, metalness: 0.6, roughness: 0.4 }));
  mark.position.set(0, -0.35, 0.15);
  rear.add(mark);

  roundedSurface(2.58, 5.58, 0.34, black, phone, 0, 0, 0.148);

  // Procedural screen artwork is a texture on the glass, not a flat stand-in for the phone.
  const wallpaperCanvas = document.createElement('canvas');
  wallpaperCanvas.width = 768;
  wallpaperCanvas.height = 1536;
  const ctx = wallpaperCanvas.getContext('2d');
  const wallpaper = ctx.createLinearGradient(0, 0, 768, 1536);
  wallpaper.addColorStop(0, '#1c1010');
  wallpaper.addColorStop(0.6, '#30180e');
  wallpaper.addColorStop(1, '#0b080b');
  ctx.fillStyle = wallpaper;
  ctx.fillRect(0, 0, 768, 1536);
  for (let i = 0; i < 3; i++) {
    const ribbon = ctx.createLinearGradient(0, 0, 768, 1400);
    ribbon.addColorStop(0, '#603922');
    ribbon.addColorStop(0.34, '#bf8257');
    ribbon.addColorStop(0.54, '#ffe0bf');
    ribbon.addColorStop(0.7, '#bd7e4f');
    ribbon.addColorStop(1, '#2a1110');
    ctx.strokeStyle = ribbon;
    ctx.lineWidth = 165;
    ctx.beginPath();
    ctx.moveTo(-200, 1450 + i * 430);
    ctx.bezierCurveTo(90, 650 + i * 340, 720, 1130 + i * 230, 890, -100 + i * 330);
    ctx.stroke();
    ctx.strokeStyle = '#f8d9b45c';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-200, 1370 + i * 430);
    ctx.bezierCurveTo(90, 570 + i * 340, 720, 1050 + i * 230, 890, -180 + i * 330);
    ctx.stroke();
  }
  const screenTexture = new THREE.CanvasTexture(wallpaperCanvas);
  screenTexture.colorSpace = THREE.SRGBColorSpace;
  screenTexture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 4);
  const screenMaterial = new THREE.MeshPhysicalMaterial({ map: screenTexture, emissiveMap: screenTexture, emissive: 0xffffff, emissiveIntensity: 0.55, roughness: 0.24, metalness: 0, clearcoat: 0.3, clearcoatRoughness: 0.16, envMapIntensity: 0.2 });
  roundedSurface(2.44, 5.44, 0.29, screenMaterial, phone, 0, 0, 0.152);
  roundedSurface(0.73, 0.18, 0.085, new THREE.MeshBasicMaterial({ color: 0x050608 }), phone, 0, 2.49, 0.158);
  cylinder(0.033, 0.014, lensGlass, phone, 0.25, 2.49, 0.162);
  roundedSurface(0.64, 0.025, 0.012, new THREE.MeshBasicMaterial({ color: 0xe5ddd6 }), phone, 0, -2.55, 0.16);

  roundedSolid(0.075, 0.64, 0.14, 0.035, metal, phone, 1.35, 0.72, 0);
  roundedSolid(0.075, 0.45, 0.14, 0.035, metal, phone, -1.35, 1.12, 0);
  roundedSolid(0.075, 0.45, 0.14, 0.035, metal, phone, -1.35, 0.5, 0);
  roundedSolid(0.075, 0.21, 0.14, 0.035, metal, phone, -1.35, 1.82, 0);
  [-2.2, 2.2].forEach(y => [-1, 1].forEach(side => {
    const seam = new THREE.Mesh(new THREE.BoxGeometry(0.038, 0.032, 0.234), antenna);
    seam.position.set(side * 1.342, y, 0);
    phone.add(seam);
  }));
  const port = new THREE.Mesh(new THREE.BoxGeometry(0.38, 0.015, 0.085), black);
  port.position.set(0, -2.847, 0);
  phone.add(port);
  for (let i = 0; i < 5; i++) [-1, 1].forEach(side => {
    const speaker = new THREE.Mesh(new THREE.SphereGeometry(0.024, 12, 8), black);
    speaker.scale.set(1, 0.35, 1);
    speaker.position.set(side * (0.49 + i * 0.11), -2.851, 0);
    phone.add(speaker);
  });

  phone.traverse(object => { if (object.isMesh) { object.castShadow = true; object.receiveShadow = true; } });
  let frame = 0;
  let progress = 0;
  let target = 0;
  let visible = true;
  let lastTime = 0;
  let contextLost = false;
  function measureProgress() {
    const headerHeight = document.querySelector('.global-nav').getBoundingClientRect().height;
    const rect = hero.getBoundingClientRect();
    const distance = hero.offsetHeight - document.querySelector('.phone-sticky').offsetHeight;
    target = motionPreference.matches ? 0 : THREE.MathUtils.clamp((headerHeight - rect.top) / Math.max(distance, 1), 0, 1);
    progressBar.style.transform = 'scaleX(' + target + ')';
    hero.dataset.scrollProgress = target.toFixed(3);
  }
  function draw(now = 0) {
    frame = 0;
    if (contextLost || !visible || document.hidden) return;
    const dt = Math.min((now - lastTime) / 1000 || 0.016, 0.1);
    lastTime = now;
    progress = motionPreference.matches ? 0 : THREE.MathUtils.lerp(progress, target, 1 - Math.exp(-16 * dt));
    if (Math.abs(progress - target) < 0.0001) progress = target;
    phone.rotation.set(-0.08 + Math.sin(progress * Math.PI * 2) * 0.1, Math.PI + 0.38 + progress * Math.PI * 2, -0.12 + Math.sin(progress * Math.PI * 2) * 0.045);
    hero.dataset.rotationDegrees = (progress * 360).toFixed(1);
    renderer.render(scene, camera);
    if (Math.abs(progress - target) > 0.0001) frame = requestAnimationFrame(draw);
  }
  function requestDraw() { if (!frame && visible && !document.hidden && !contextLost) frame = requestAnimationFrame(draw); }
  function resize() {
    hero.style.setProperty('--hero-scroll-distance', Math.round(innerHeight * 1.6) + 'px');
    hero.classList.toggle('reduced-motion', motionPreference.matches);
    stage.setAttribute('aria-label', motionPreference.matches ? 'A realistic copper Phone Pro with a metallic frame, glass screen, and raised cameras.' : 'A copper Phone Pro with realistic metal, glass, and cameras, rotating a full turn as you scroll.');
    renderer.setSize(stage.clientWidth, stage.clientHeight, false);
    camera.aspect = stage.clientWidth / stage.clientHeight;
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    camera.position.z = Math.max(6.85 / (2 * Math.tan(verticalFov / 2)), 3.8 / (2 * Math.tan(verticalFov / 2) * camera.aspect));
    camera.updateProjectionMatrix();
    measureProgress();
    requestDraw();
  }
  hero.classList.add('has-3d');
  resize();
  draw();
  stage.classList.add('scene-ready');

  const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible) { measureProgress(); requestDraw(); } }, { rootMargin: '80px' });
  observer.observe(stage);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  window.addEventListener('resize', resize, { passive: true });
  window.addEventListener('scroll', () => { measureProgress(); requestDraw(); }, { passive: true });
  document.addEventListener('visibilitychange', requestDraw);
  motionPreference.addEventListener('change', resize);
  canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); contextLost = true; stage.classList.remove('scene-ready'); hero.classList.remove('has-3d'); stage.setAttribute('aria-label', 'A studio photograph of the copper Phone Pro.'); });
  canvas.addEventListener('webglcontextrestored', () => { contextLost = false; hero.classList.add('has-3d'); resize(); stage.classList.add('scene-ready'); requestDraw(); });
  window.addEventListener('pagehide', event => {
    if (event.persisted) return;
    cancelAnimationFrame(frame);
    observer.disconnect();
    resizeObserver.disconnect();
    scene.traverse(object => {
      object.geometry?.dispose();
      if (object.material) object.material.dispose();
    });
    screenTexture.dispose();
    grainTexture.dispose();
    opticalTexture.dispose();
    environment.dispose();
    renderer.dispose();
  }, { once: true });
}
try { initializePhone(); } catch (error) {
  hero.classList.remove('has-3d');
  stage.classList.remove('scene-ready');
  hero.dataset.renderer = 'fallback';
  stage.setAttribute('aria-label', 'A studio photograph of the copper Phone Pro.');
  console.warn('3D phone unavailable; displaying the product photograph.', error);
}

