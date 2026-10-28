/* Interactive viewer for Bodygram's .obj body model.
 * Uses the vendored three.js r147 UMD build (THREE, THREE.OBJLoader, THREE.OrbitControls).
 * Draws Bodygram-style girth bands (bust, waist, hip, arm, thigh, calf) around the
 * mesh and labels them with the measured values.
 */
(function () {
  const MODEL_HEIGHT = 1.78; // viewer units after normalisation
  const BAND_COLOR = 0x17a99a;
  const BAND_HALF = 0.011; // ~1.8 cm band on a 1.78-unit body
  const BAND_PUSH = 0.005;
  const LABEL_GAP = 32;
  const LABEL_TOP = 8;

  const state = {
    renderer: null,
    scene: null,
    camera: null,
    controls: null,
    model: null,
    bandGroup: null,
    bandEntries: [],
    lineEntries: [],
    labels: [],
    overlay: null,
    svg: null,
    frame: null,
    resizeObserver: null,
    url: '',
    bands: [],
    lines: [],
    bandsKey: '',
    heightCm: 0,
    unitsPerCm: 0,
    thumbCamera: null,
    thumbWaiters: [],
    token: 0,
    lastError: null,
  };

  function statusElement() {
    return document.getElementById('bodygram-avatar-status');
  }

  function setStatus(message, isError) {
    const el = statusElement();
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('is-error', Boolean(isError));
    el.hidden = !message;
  }

  function stageElement() {
    return document.getElementById('bodygram-avatar-stage');
  }

  function ensureScene() {
    if (state.renderer) return true;
    if (typeof THREE === 'undefined' || !THREE.OBJLoader) {
      setStatus('3D viewer unavailable in this browser.', true);
      return false;
    }
    const stage = stageElement();
    const canvas = document.getElementById('bodygram-avatar-canvas');
    if (!stage || !canvas) return false;

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.92;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.05, 100);
    camera.position.set(0, 1.15, 3.6);

    const controls = new THREE.OrbitControls(camera, canvas);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 1.6;
    controls.maxDistance = 8;
    controls.minPolarAngle = 0.35;
    controls.maxPolarAngle = Math.PI * 0.62;
    controls.target.set(0, 0.92, 0);

    scene.add(new THREE.HemisphereLight(0xffffff, 0xc7a4b6, 0.42));

    const keyLight = new THREE.DirectionalLight(0xffffff, 0.95);
    keyLight.position.set(2.2, 3.6, 2.6);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xfbe6ef, 0.28);
    fillLight.position.set(-3, 2.2, 1.5);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.45);
    rimLight.position.set(-1.5, 2.6, -3.2);
    scene.add(rimLight);

    const shadow = new THREE.Mesh(
      new THREE.CircleGeometry(0.62, 48),
      new THREE.MeshBasicMaterial({ color: 0x8a5a74, transparent: true, opacity: 0.16 })
    );
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = 0.002;
    scene.add(shadow);

    state.renderer = renderer;
    state.scene = scene;
    state.camera = camera;
    state.controls = controls;
    state.bandGroup = new THREE.Group();
    scene.add(state.bandGroup);

    ensureOverlay();
    resize();
    if (typeof ResizeObserver !== 'undefined') {
      state.resizeObserver = new ResizeObserver(resize);
      state.resizeObserver.observe(stage);
    } else {
      window.addEventListener('resize', resize);
    }

    loop();
    return true;
  }

  function ensureOverlay() {
    const stage = stageElement();
    if (!stage || state.overlay) return;
    const overlay = document.createElement('div');
    overlay.className = 'bodygram-band-overlay';
    overlay.hidden = true;
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'bodygram-band-lines');
    svg.setAttribute('aria-hidden', 'true');
    overlay.append(svg);
    stage.append(overlay);
    state.overlay = overlay;
    state.svg = svg;
  }

  function resize() {
    const stage = stageElement();
    if (!stage || !state.renderer) return;
    const width = Math.max(stage.clientWidth, 1);
    const height = Math.max(stage.clientHeight, 1);
    state.renderer.setSize(width, height, false);
    state.camera.aspect = width / height;
    state.camera.updateProjectionMatrix();
    updateLabels();
  }

  function loop() {
    state.frame = window.requestAnimationFrame(loop);
    if (!state.renderer) return;
    try {
      state.controls.update();
      state.renderer.render(state.scene, state.camera);
      updateLabels();
      state.lastError = null;
    } catch (error) {
      const message = String((error && error.stack) || error);
      if (state.lastError !== message) console.error('Bodygram avatar render failed:', error);
      state.lastError = message;
    }
  }

  function renderNow() {
    if (!state.renderer || !state.scene || !state.camera) return false;
    state.controls.update();
    state.renderer.render(state.scene, state.camera);
    updateLabels();
    return true;
  }

  function disposeModel() {
    if (!state.model) return;
    state.scene.remove(state.model);
    state.model.traverse(child => {
      if (child.geometry) child.geometry.dispose();
      if (child.material) {
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach(material => material.dispose && material.dispose());
      }
    });
    state.model = null;
    clearBands();
  }

  function clearBands() {
    state.bandEntries.forEach(entry => {
      state.bandGroup.remove(entry.mesh);
      entry.mesh.geometry.dispose();
      entry.mesh.material.dispose();
    });
    state.bandEntries = [];
    state.lineEntries = [];
    state.labels.forEach(label => {
      label.chip.remove();
      label.line.remove();
      label.dot.remove();
    });
    state.labels = [];
    if (state.overlay) state.overlay.hidden = true;
  }

  function materialForModel() {
    return new THREE.MeshStandardMaterial({
      color: 0xc98fa9,
      roughness: 0.86,
      metalness: 0.02,
      side: THREE.DoubleSide,
    });
  }

  function bandMaterial() {
    return new THREE.MeshBasicMaterial({
      color: BAND_COLOR,
      side: THREE.DoubleSide,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    });
  }

  function fitModel(object) {
    object.updateMatrixWorld(true);
    let box = new THREE.Box3().setFromObject(object);
    let size = box.getSize(new THREE.Vector3());

    // Bodygram can deliver a Z-up model; turn it upright when it is deeper than tall.
    if (size.z > size.y * 1.1) {
      object.rotation.x = -Math.PI / 2;
      object.updateMatrixWorld(true);
      box = new THREE.Box3().setFromObject(object);
      size = box.getSize(new THREE.Vector3());
    }

    const height = Math.max(size.y, 0.001);
    const scale = MODEL_HEIGHT / height;
    object.scale.setScalar(scale);
    object.updateMatrixWorld(true);

    box = new THREE.Box3().setFromObject(object);
    const center = box.getCenter(new THREE.Vector3());
    object.position.x -= center.x;
    object.position.z -= center.z;
    object.position.y -= box.min.y;
    object.updateMatrixWorld(true);
  }

  function reset() {
    if (!state.controls || !state.camera) return;
    state.camera.position.set(0, 1.15, 3.6);
    state.controls.target.set(0, 0.92, 0);
    state.controls.update();
    updateLabels();
  }

  /* ---------- mesh slicing ---------- */

  function meshDataFor(object) {
    let data = null;
    object.updateMatrixWorld(true);
    object.traverse(child => {
      if (data || !child.isMesh) return;
      const position = child.geometry && child.geometry.attributes.position;
      if (!position) return;
      const matrix = child.matrixWorld;
      const vertex = new THREE.Vector3();
      const tris = new Float32Array(position.count * 3);
      for (let i = 0; i < position.count; i += 1) {
        vertex.fromBufferAttribute(position, i).applyMatrix4(matrix);
        tris[i * 3] = vertex.x;
        tris[i * 3 + 1] = vertex.y;
        tris[i * 3 + 2] = vertex.z;
      }
      data = { tris };
    });
    return data;
  }

  function contoursAt(data, y) {
    const { tris } = data;
    const segments = [];
    for (let i = 0; i < tris.length; i += 9) {
      const y0 = tris[i + 1];
      const y1 = tris[i + 4];
      const y2 = tris[i + 7];
      const above = (y0 >= y) + (y1 >= y) + (y2 >= y);
      if (above === 0 || above === 3) continue;
      const points = [];
      for (let edge = 0; edge < 3; edge += 1) {
        const a = i + edge * 3;
        const b = i + ((edge + 1) % 3) * 3;
        const ay = tris[a + 1];
        const by = tris[b + 1];
        if ((ay < y && by >= y) || (by < y && ay >= y)) {
          const t = (y - ay) / (by - ay);
          points.push(new THREE.Vector3(
            tris[a] + (tris[b] - tris[a]) * t,
            y,
            tris[a + 2] + (tris[b + 2] - tris[a + 2]) * t
          ));
        }
      }
      if (points.length === 2) segments.push(points);
    }
    return chainSegments(segments);
  }

  function pointKey(point) {
    return `${Math.round(point.x * 1e4)}:${Math.round(point.z * 1e4)}`;
  }

  function chainSegments(segments) {
    const buckets = new Map();
    segments.forEach((segment, index) => {
      [segment[0], segment[1]].forEach(point => {
        const key = pointKey(point);
        const list = buckets.get(key);
        if (list) list.push(index);
        else buckets.set(key, [index]);
      });
    });

    const used = new Array(segments.length).fill(false);
    const loops = [];
    for (let i = 0; i < segments.length; i += 1) {
      if (used[i]) continue;
      used[i] = true;
      const loop = [segments[i][0], segments[i][1]];
      let tail = segments[i][1];
      while (true) {
        const candidates = buckets.get(pointKey(tail)) || [];
        let next = -1;
        for (const index of candidates) {
          if (!used[index]) { next = index; break; }
        }
        if (next < 0) break;
        used[next] = true;
        const [a, b] = segments[next];
        tail = pointKey(a) === pointKey(tail) ? b : a;
        loop.push(tail);
        if (pointKey(tail) === pointKey(loop[0])) {
          loop.pop();
          break;
        }
      }
      if (loop.length >= 12) loops.push(loop);
    }
    return loops;
  }

  function perimeter(loop) {
    let total = 0;
    for (let i = 0; i < loop.length; i += 1) {
      const a = loop[i];
      const b = loop[(i + 1) % loop.length];
      total += Math.hypot(b.x - a.x, b.z - a.z);
    }
    return total;
  }

  function centerXZ(loop) {
    let x = 0;
    let z = 0;
    loop.forEach(point => { x += point.x; z += point.z; });
    return new THREE.Vector2(x / loop.length, z / loop.length);
  }

  function pickTorso(loops) {
    let best = null;
    loops.forEach(loop => {
      const value = perimeter(loop);
      if (!best || value > best.value) best = { loop, value };
    });
    return best;
  }

  function pickLeftLimb(loops, minX, maxX) {
    let best = null;
    loops.forEach(loop => {
      const center = centerXZ(loop);
      if (center.x > -0.02) return;
      if (minX !== undefined && center.x < minX) return;
      if (maxX !== undefined && center.x > maxX) return;
      const value = perimeter(loop);
      if (!best || value > best.value) best = { loop, value };
    });
    return best;
  }

  function bestHeightForGirth(data, target, fromY, toY, picker) {
    const steps = 9;
    let best = null;
    for (let i = 0; i < steps; i += 1) {
      const y = fromY + ((toY - fromY) * i) / (steps - 1);
      const picked = picker(contoursAt(data, y));
      if (!picked) continue;
      const diff = Math.abs(picked.value - target);
      if (!best || diff < best.diff) best = { y, diff };
    }
    return best ? best.y : null;
  }

  function resampleLoop(loop, count) {
    const center = centerXZ(loop);
    const polar = loop.map(point => ({
      angle: Math.atan2(point.z - center.y, point.x - center.x),
      radius: Math.hypot(point.x - center.x, point.z - center.y),
    }));
    polar.sort((a, b) => a.angle - b.angle);

    const points = [];
    for (let i = 0; i < count; i += 1) {
      const angle = -Math.PI + (i / count) * Math.PI * 2;
      let before = polar[polar.length - 1];
      let after = polar[0];
      for (let j = 0; j < polar.length; j += 1) {
        if (polar[j].angle <= angle) before = polar[j];
        if (polar[j].angle >= angle) { after = polar[j]; break; }
      }
      if (after.angle < angle) after = polar[0];
      let radius = before.radius;
      if (after !== before) {
        const span = after.angle - before.angle;
        const offset = span > 0 ? (angle - before.angle) / span : 0;
        radius = before.radius + (after.radius - before.radius) * offset;
      }
      points.push(new THREE.Vector3(
        center.x + Math.cos(angle) * radius,
        loop[0].y,
        center.y + Math.sin(angle) * radius
      ));
    }
    return { points, center };
  }

  function verticalRibbon(section) {
    const count = section.points.length;
    const positions = [];
    const indices = [];
    const y = section.points[0].y;
    for (let i = 0; i < count; i += 1) {
      const point = section.points[i];
      const dx = point.x - section.center.x;
      const dz = point.z - section.center.y;
      const length = Math.hypot(dx, dz) || 1;
      const x = point.x + (dx / length) * BAND_PUSH;
      const z = point.z + (dz / length) * BAND_PUSH;
      positions.push(x, y + BAND_HALF, z, x, y - BAND_HALF, z);
    }
    for (let i = 0; i < count; i += 1) {
      const next = (i + 1) % count;
      const a = i * 2;
      const b = i * 2 + 1;
      const c = next * 2 + 1;
      const d = next * 2;
      indices.push(a, b, d, b, c, d);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setIndex(indices);
    return geometry;
  }

  function bandAnchor(section, side) {
    let point = section.points[0];
    section.points.forEach(candidate => {
      if (side === 'left' ? candidate.x < point.x : candidate.x > point.x) point = candidate;
    });
    return point.clone();
  }

  function sectionRadius(points, center) {
    let radius = 0;
    points.forEach(point => {
      radius = Math.max(radius, Math.hypot(point.x - center.x, point.z - center.y));
    });
    return radius;
  }

  function buildBand(data, plan) {
    const picked = plan.picker(contoursAt(data, plan.y));
    if (!picked) return null;

    const section = resampleLoop(picked.loop, 120);
    const mesh = new THREE.Mesh(verticalRibbon(section), bandMaterial());
    mesh.renderOrder = 2;
    mesh.frustumCulled = false;
    return {
      key: plan.key,
      mesh,
      anchor: bandAnchor(section, plan.side),
      label: plan.label,
      value: plan.value,
      side: plan.side,
      y: plan.y,
      center: new THREE.Vector3(section.center.x, plan.y, section.center.y),
      radius: sectionRadius(section.points, section.center),
      frameCm: plan.frameCm,
    };
  }

  function planBands(bands, heightCm, data) {
    if (!(heightCm > 0)) return [];
    const unitsPerCm = MODEL_HEIGHT / heightCm;
    const plans = [];

    bands.forEach(band => {
      const side = band.side === 'left' ? 'left' : 'right';
      const limb = band.limb || '';
      const picker = limb === 'arm'
        ? loops => pickLeftLimb(loops, -0.9, -0.12)
        : limb
          ? loops => pickLeftLimb(loops, -0.22, -0.02)
          : pickTorso;

      let y = null;
      const anchorCm = Number(band.anchorCm);
      if (Number.isFinite(anchorCm)) {
        y = anchorCm * unitsPerCm;
      } else if (Number.isFinite(Number(band.heightCm))) {
        y = Number(band.heightCm) * unitsPerCm;
      } else if (limb) {
        // Fallback: find the height whose contour best matches the measured girth.
        const target = Number(band.value) * unitsPerCm * 1.05;
        y = bestHeightForGirth(
          data,
          target,
          heightCm * 0.16 * unitsPerCm,
          heightCm * 0.85 * unitsPerCm,
          picker
        );
      }

      if (!Number.isFinite(y) || y <= 0.02 || y >= MODEL_HEIGHT - 0.02) return;
      plans.push({
        y,
        picker,
        side,
        key: band.key || '',
        label: band.label,
        value: Number(band.value),
        primary: Boolean(band.primary),
        frameCm: Number(band.frameCm) || 30,
      });
    });

    return plans;
  }

  function surfacePoint(data, y, limb, edge) {
    const loops = contoursAt(data, y);
    const picked = limb === 'arm'
      ? pickLeftLimb(loops, -0.9, -0.12)
      : limb
        ? pickLeftLimb(loops, -0.22, -0.02)
        : pickTorso(loops);
    if (!picked) return null;
    const { loop } = picked;
    let point = loop[0];
    loop.forEach(candidate => {
      if (edge === 'inner' || edge === 'right') {
        if (candidate.x > point.x) point = candidate;
      } else if (edge === 'back') {
        if (candidate.z < point.z) point = candidate;
      } else if (candidate.x < point.x) {
        point = candidate;
      }
    });
    return point.clone();
  }

  function buildLines(data) {
    const unitsPerCm = state.unitsPerCm;
    if (!(unitsPerCm > 0)) return;
    state.lines.forEach(spec => {
      const from = spec.from || {};
      const to = spec.to || {};
      const a = surfacePoint(data, Number(from.cm) * unitsPerCm, from.limb || '', from.edge || 'outer');
      const b = surfacePoint(data, Number(to.cm) * unitsPerCm, to.limb || '', to.edge || 'outer');
      if (!a || !b) return;

      const points = [a];
      (spec.via || []).forEach(step => {
        const point = surfacePoint(data, Number(step.cm) * unitsPerCm, step.limb || '', step.edge || 'outer');
        if (point) points.push(point);
      });
      points.push(b);

      const box = new THREE.Box3().setFromPoints(points);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      let length = 0;
      for (let i = 1; i < points.length; i += 1) length += points[i - 1].distanceTo(points[i]);
      state.lineEntries.push({
        key: spec.key,
        label: spec.label,
        value: Number(spec.value),
        points,
        center,
        view: spec.view === 'back' ? 'back' : 'front',
        frameCm: Math.max(Math.max(size.x, size.y) / unitsPerCm * 1.35, length / unitsPerCm * 1.1, 18),
      });
    });
  }

  function buildBands() {
    if (!state.model) return;
    const data = meshDataFor(state.model);
    if (!data) return;
    state.unitsPerCm = state.heightCm > 0 ? MODEL_HEIGHT / state.heightCm : 0;

    if (state.bands.length) {
      const plans = planBands(state.bands, state.heightCm, data);
      ensureOverlay();
      state.overlay.hidden = false;

      plans.forEach(plan => {
        const band = buildBand(data, plan);
        if (!band) return;
        band.mesh.visible = Boolean(plan.primary);
        state.bandGroup.add(band.mesh);
        state.bandEntries.push(band);
        if (plan.primary) addLabel(band);
      });
    }

    buildLines(data);
    updateLabels();
    flushThumbnails();
  }

  /* ---------- labels ---------- */

  function addLabel(band) {
    const chip = document.createElement('div');
    chip.className = `bodygram-band-label is-${band.side}`;
    const name = document.createElement('span');
    name.textContent = band.label;
    const value = document.createElement('strong');
    value.textContent = `${Number(band.value).toFixed(1)} cm`;
    chip.append(name, value);

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('class', 'bodygram-band-line');
    const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    dot.setAttribute('class', 'bodygram-band-dot');
    dot.setAttribute('r', '2.6');

    state.overlay.append(chip);
    state.svg.append(line, dot);
    state.labels.push({ chip, line, dot, anchor: band.anchor, side: band.side });
  }

  function updateLabels() {
    const stage = stageElement();
    if (!stage || !state.camera || !state.labels.length) return;
    const width = stage.clientWidth;
    const height = stage.clientHeight;
    if (!width || !height) return;

    state.camera.updateMatrixWorld();
    const projected = new THREE.Vector3();

    state.labels.forEach(label => {
      projected.copy(label.anchor);
      projected.project(state.camera);
      label.screenX = (projected.x * 0.5 + 0.5) * width;
      label.screenY = (-projected.y * 0.5 + 0.5) * height;
    });

    ['left', 'right'].forEach(side => {
      const items = state.labels
        .filter(label => label.side === side)
        .sort((a, b) => a.screenY - b.screenY);
      let cursor = LABEL_TOP;
      items.forEach(label => {
        const chipHeight = label.chip.offsetHeight || 30;
        const top = Math.max(label.screenY - chipHeight / 2, cursor);
        label.chip.style.top = `${Math.round(top)}px`;
        label.chip.style[side === 'left' ? 'left' : 'right'] = '6px';
        cursor = top + chipHeight + 6;
      });
      const overflow = cursor - height + LABEL_TOP;
      if (overflow > 0 && items.length) {
        items.forEach(label => {
          const top = parseFloat(label.chip.style.top) - overflow;
          label.chip.style.top = `${Math.round(Math.max(LABEL_TOP, top))}px`;
        });
      }
      items.forEach(label => {
        const chipHeight = label.chip.offsetHeight || 30;
        const chipWidth = label.chip.offsetWidth || 76;
        const top = parseFloat(label.chip.style.top) + chipHeight / 2;
        const edge = side === 'left' ? 6 + chipWidth : width - 6 - chipWidth;
        label.line.setAttribute('x1', String(Math.round(edge)));
        label.line.setAttribute('y1', String(Math.round(top)));
        label.line.setAttribute('x2', String(Math.round(label.screenX)));
        label.line.setAttribute('y2', String(Math.round(label.screenY)));
        label.dot.setAttribute('cx', String(Math.round(label.screenX)));
        label.dot.setAttribute('cy', String(Math.round(label.screenY)));
      });
    });
  }

  /* ---------- per-measurement thumbnails ---------- */

  const THUMB_SIZE = 192;

  function thumbnailCamera(center, extent, view) {
    if (!state.thumbCamera) {
      state.thumbCamera = new THREE.PerspectiveCamera(32, 1, 0.01, 20);
    }
    const camera = state.thumbCamera;
    const reach = Math.max(extent, 0.05);
    const distance = (reach / 2) / Math.tan((camera.fov * Math.PI / 180) / 2);
    camera.aspect = 1;
    camera.near = Math.max(distance * 0.02, 0.005);
    camera.far = distance * 8;
    const facing = view === 'back' ? -1 : 1;
    camera.position.set(center.x, center.y + reach * 0.05, center.z + distance * facing);
    camera.updateProjectionMatrix();
    camera.lookAt(center.x, center.y, center.z);
    camera.updateMatrixWorld();
    return camera;
  }

  function drawLineThumbnail(ctx, camera, line, size, box, ratio) {
    const project = point => {
      const vector = point.clone().project(camera);
      return {
        x: ((vector.x * 0.5 + 0.5) * box) * (size / box),
        y: ((-vector.y * 0.5 + 0.5) * box) * (size / box),
      };
    };
    const points = line.points.map(project);
    ctx.save();
    ctx.strokeStyle = '#17a99a';
    ctx.lineWidth = Math.max(1.6 * ratio, 1.5);
    ctx.lineCap = 'round';
    ctx.setLineDash([4.5 * ratio, 3.5 * ratio]);
    ctx.beginPath();
    points.forEach((point, index) => {
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = '#17a99a';
    [points[0], points[points.length - 1]].forEach(point => {
      ctx.beginPath();
      ctx.arc(point.x, point.y, 3.2 * ratio, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  }

  function makeThumbnail(key) {
    if (!state.renderer || !state.model) return null;
    const stage = stageElement();
    if (!stage) return null;

    const band = state.bandEntries.find(entry => entry.key === key);
    const line = state.lineEntries.find(entry => entry.key === key);
    if (!band && !line) return null;

    const box = Math.max(Math.min(THUMB_SIZE, stage.clientWidth, stage.clientHeight), 64);
    const ratio = state.renderer.getPixelRatio();
    const center = band ? band.center : line.center;
    const extentCm = band ? band.frameCm : line.frameCm;
    const extent = extentCm * (state.unitsPerCm || 0.01);
    const camera = thumbnailCamera(center, extent, line ? line.view : 'front');

    const visibility = state.bandEntries.map(entry => entry.mesh.visible);
    state.bandEntries.forEach(entry => { entry.mesh.visible = entry === band; });

    const canvas = document.createElement('canvas');
    canvas.width = THUMB_SIZE;
    canvas.height = THUMB_SIZE;
    const ctx = canvas.getContext('2d');

    state.renderer.setScissorTest(true);
    state.renderer.setViewport(0, 0, box, box);
    state.renderer.setScissor(0, 0, box, box);
    state.renderer.render(state.scene, camera);
    const sourceY = (stage.clientHeight - box) * ratio;
    ctx.drawImage(
      state.renderer.domElement,
      0, sourceY, box * ratio, box * ratio,
      0, 0, THUMB_SIZE, THUMB_SIZE
    );
    if (line) drawLineThumbnail(ctx, camera, line, THUMB_SIZE, box, ratio);

    state.bandEntries.forEach((entry, index) => { entry.mesh.visible = visibility[index]; });
    state.renderer.setScissorTest(false);
    state.renderer.setViewport(0, 0, stage.clientWidth, stage.clientHeight);
    state.renderer.render(state.scene, state.camera);
    updateLabels();

    const url = canvas.toDataURL('image/png');
    return url && url.length > 64 ? url : null;
  }

  function flushThumbnails() {
    if (!state.thumbWaiters.length) return;
    if (!state.model) return;
    const pending = state.thumbWaiters.splice(0);
    pending.forEach(request => {
      const result = {};
      request.keys.forEach(key => {
        try {
          const url = makeThumbnail(key);
          if (url) result[key] = url;
        } catch (error) {
          console.error('Bodygram thumbnail failed:', error);
        }
      });
      request.resolve(result);
    });
  }

  function thumbnails(keys) {
    return new Promise(resolve => {
      const list = Array.isArray(keys) ? keys.filter(Boolean) : [];
      if (!list.length) {
        resolve({});
        return;
      }
      state.thumbWaiters.push({ keys: list, resolve });
      flushThumbnails();
    });
  }

  /* ---------- public API ---------- */

  function load(url, options) {
    const settings = options || {};
    const signature = JSON.stringify([settings.bands || [], settings.lines || []]);
    const sameModel = Boolean(url) && state.url === url;

    if (!url) return;
    if (!ensureScene()) return;

    if (sameModel) {
      if (signature !== state.bandsKey) {
        state.bands = settings.bands || [];
        state.lines = settings.lines || [];
        state.bandsKey = signature;
        state.heightCm = Number(settings.heightCm) || 0;
        clearBands();
        buildBands();
        renderNow();
      }
      return;
    }

    const token = ++state.token;
    state.url = url;
    state.bands = settings.bands || [];
    state.lines = settings.lines || [];
    state.bandsKey = signature;
    state.heightCm = Number(settings.heightCm) || 0;
    disposeModel();
    setStatus('Loading 3D model…', false);

    fetch(url, { credentials: 'same-origin' })
      .then(response => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then(text => {
        if (token !== state.token) return;
        const object = new THREE.OBJLoader().parse(text);
        object.traverse(child => {
          if (child.isMesh) child.material = materialForModel();
        });
        fitModel(object);
        state.scene.add(object);
        state.model = object;
        reset();
        setStatus('', false);
        // Let the body paint before slicing it into measurement contours.
        window.setTimeout(() => {
          if (token !== state.token) return;
          buildBands();
          renderNow();
        }, 30);
      })
      .catch(() => {
        if (token !== state.token) return;
        state.url = '';
        setStatus('Could not load the 3D model.', true);
        const pending = state.thumbWaiters.splice(0);
        pending.forEach(request => request.resolve({}));
      });
  }

  function destroy() {
    state.token += 1;
    state.url = '';
    disposeModel();
    const pending = state.thumbWaiters.splice(0);
    pending.forEach(request => request.resolve({}));
    setStatus('', false);
    if (state.frame) {
      window.cancelAnimationFrame(state.frame);
      state.frame = null;
    }
    if (state.resizeObserver) {
      state.resizeObserver.disconnect();
      state.resizeObserver = null;
    } else {
      window.removeEventListener('resize', resize);
    }
    if (state.overlay) {
      state.overlay.remove();
      state.overlay = null;
      state.svg = null;
    }
    if (state.controls) state.controls.dispose();
    if (state.renderer) state.renderer.dispose();
    state.renderer = null;
    state.scene = null;
    state.camera = null;
    state.controls = null;
  }

  function info() {
    const size = state.model
      ? new THREE.Box3().setFromObject(state.model).getSize(new THREE.Vector3()).toArray()
      : null;
    return {
      ready: Boolean(state.model),
      url: state.url,
      triangles: state.renderer ? state.renderer.info.render.triangles : 0,
      calls: state.renderer ? state.renderer.info.render.calls : 0,
      size,
      bands: state.bandEntries.map(band => ({ label: band.label, value: band.value, visible: band.mesh.visible })),
      lines: state.lineEntries.map(line => ({ label: line.label, value: line.value })),
      labels: state.labels.length,
      camera: state.camera ? state.camera.position.toArray() : null,
      error: state.lastError || null,
    };
  }

  window.BodygramAvatar = { load, reset, destroy, info, renderNow, thumbnails };
  window.resetBodygramAvatar = reset;
})();
