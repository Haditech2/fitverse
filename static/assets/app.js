const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];

/* Utility Toast */
function toast(message){
  let el = $('#toast');
  if(!el){
    el = document.createElement('div');
    el.id = 'toast';
    el.className = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.remove('show'), 2600);
}

function toggleMenu(){
  const n = $('#main-nav');
  if(n) n.classList.toggle('open');
}

function markActive(el){
  const group = el.closest('.choice-grid,.mini-designs,.segmented,.wardrobe-tabs,.model-presets');
  if(group){
    $$('button,a', group).forEach(x => x.classList.remove('active','selected'));
  }
  el.classList.add(group?.classList.contains('mini-designs') || group?.classList.contains('model-presets') ? 'selected' : 'active');
}

function saveLocal(key, value){
  try { localStorage.setItem('fitverse-' + key, JSON.stringify(value)); } catch(e){}
}

function readLocal(key, fallback){
  try { return JSON.parse(localStorage.getItem('fitverse-' + key)) ?? fallback; } catch(e){ return fallback; }
}

function toggleFavorite(button, id){
  let list = readLocal('favorites', []);
  const isCurrentlySaved = list.includes(String(id));

  if(isCurrentlySaved){
    list = list.filter(x => x !== String(id));
    button.textContent = '♡';
    toast('Removed from your wardrobe');
  } else {
    list.push(String(id));
    button.textContent = '♥';
    toast('Saved to your wardrobe');
  }
  saveLocal('favorites', list);

  // Sync with Django backend
  fetch('/api/favorite/toggle/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ design_id: id })
  }).catch(() => {});
}

function filterProducts(){
  const q = ($('#design-search')?.value || '').toLowerCase();
  const cat = $('#category-filter')?.value || 'all';
  let shown = 0;
  $$('.product-card').forEach(card => {
    const matchQ = card.dataset.search?.toLowerCase().includes(q) ?? true;
    const matchC = cat === 'all' || card.dataset.category === cat;
    card.style.display = matchQ && matchC ? '' : 'none';
    if(matchQ && matchC) shown++;
  });
  const empty = $('#no-results');
  if(empty) empty.style.display = shown ? 'none' : 'block';
}

function previewUpload(input, target){
  const file = input.files?.[0];
  if(!file) return;
  if(!file.type.startsWith('image/')){
    toast('Please choose an image file.');
    return;
  }
  if(file.size > 12 * 1024 * 1024){
    toast('Choose an image smaller than 12 MB.');
    return;
  }
  const url = URL.createObjectURL(file);
  const img = $(target);
  if(img){
    img.src = url;
    img.style.display = 'block';
    img.dataset.uploaded = 'true';
    toast('Photo loaded into fitting stage.');
  }
}

function generateTryOn(){
  const img = $('#user-photo-preview');
  if(!img?.dataset.uploaded){
    toast('Upload your photo first.');
    return;
  }
  const status = $('#tryon-status');
  if(status){
    status.innerHTML = '<strong>FASHN VTON Ready</strong><p>Photo loaded. Open Style Intelligence for real-time split testing with FASHN VTON 1.5.</p>';
    status.style.display = 'block';
  }
  toast('Photo ready for virtual try-on.');
}

function saveLook(){
  const img = $('#vton-output-image') || $('#user-photo-preview');
  const src = img?.src;
  if(!src){
    toast('No try-on image to save.');
    return;
  }
  const title = $('#ag-title')?.textContent || 'Virtual Try-On Look';
  let saved = readLocal('savedLooks', []);
  saved.unshift({
    date: new Date().toLocaleDateString(),
    title: title,
    src: src
  });
  saveLocal('savedLooks', saved.slice(0, 20));

  // Sync with Django backend
  fetch('/api/looks/save/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: title, image_url: src })
  }).catch(() => {});

  toast('Look saved to your wardrobe!');
}

function switchUnit(unit){
  $$('[data-cm]').forEach(el => {
    const cm = Number(el.dataset.cm);
    el.value = unit === 'in' ? (cm / 2.54).toFixed(1) : cm;
  });
  $$('[data-unit-label]').forEach(el => el.textContent = unit === 'in' ? 'in' : 'cm');
  $$('.segmented button').forEach(b => b.classList.toggle('active', b.dataset.unit === unit));
}

function saveMeasurements(){
  const data = {};
  $$('[data-measure]').forEach(el => data[el.dataset.measure] = el.value);
  const unit = $('.segmented button.active')?.dataset.unit || 'cm';
  data['unit'] = unit;
  
  saveLocal('measurements', data);

  // Sync with Django Backend
  fetch('/api/measurements/save/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(r => r.json()).then(() => {
    toast('Measurements saved to your profile!');
  }).catch(() => {
    toast('Measurements saved in this browser.');
  });
}

function loadMeasurements(){
  const data = readLocal('measurements', {});
  $$('[data-measure]').forEach(el => {
    if(data[el.dataset.measure] !== undefined) el.value = data[el.dataset.measure];
  });
}

/* Bodygram photo-based measurement estimation */
function previewBodygramPhoto(input, target){
  const file = input.files?.[0];
  if(!file) return;
  if(!file.type.startsWith('image/')){
    toast('Please choose an image file.');
    return;
  }
  if(file.size > 12 * 1024 * 1024){
    toast('Choose an image smaller than 12 MB.');
    return;
  }
  const img = $(target);
  if(img){
    img.src = URL.createObjectURL(file);
    img.style.display = 'block';
  }
  input.closest('.bodygram-photo')?.classList.add('is-selected');
}

function setBodygramStatus(message, kind){
  const status = $('#bodygram-status');
  if(!status) return;
  status.textContent = message;
  status.className = 'tryon-status' + (kind ? ' is-' + kind : '');
  status.style.display = message ? 'block' : 'none';
}

const BODYGRAM_COMPOSITION_LABELS = {
  bodyFatPercentage: 'Body fat',
  bodyFatMass: 'Body fat mass',
  leanMass: 'Lean mass',
  skeletalMuscleMass: 'Skeletal muscle mass',
  muscleMass: 'Muscle mass',
  fatMass: 'Fat mass',
  bodyWater: 'Body water',
  visceralFat: 'Visceral fat',
  basalMetabolicRate: 'Basal metabolic rate',
};

const BODYGRAM_GROUP_ORDER = ['Circumferences', 'Widths & depths', 'Lengths', 'Heights', 'Other'];

function bodygramCompositionLabel(key){
  if(BODYGRAM_COMPOSITION_LABELS[key]) return BODYGRAM_COMPOSITION_LABELS[key];
  return key
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, c => c.toUpperCase())
    .trim();
}

/* Bodygram returns percentages as bare numbers and masses in grams; the docs
   sample wraps values as { value, unit }. Support both shapes. */
function bodygramCompositionValue(key, raw){
  if(raw && typeof raw === 'object' && raw.value !== undefined){
    return `${raw.value}${raw.unit ? ' ' + raw.unit : ''}`;
  }
  if(typeof raw !== 'number' || !Number.isFinite(raw)) return null;
  if(key === 'bodyFatPercentage') return `${raw.toFixed(1)}%`;
  if(/Mass$/.test(key)) return `${(raw / 1000).toFixed(1)} kg`;
  return String(raw);
}

function clearBodygramResult(){
  ['#bodygram-composition', '#bodygram-all', '#bodygram-visuals', '#bodygram-saved-photos'].forEach(selector => {
    const el = $(selector);
    if(el){
      if(selector === '#bodygram-composition') el.innerHTML = '';
      el.hidden = true;
    }
  });
  const groups = $('#bodygram-all-groups');
  if(groups) groups.innerHTML = '';
  const postureRows = $('#bodygram-posture-rows');
  if(postureRows) postureRows.innerHTML = '';
  if(window.BodygramAvatar) window.BodygramAvatar.destroy();
  try { localStorage.removeItem('fitverse-bodygram-result'); } catch(e){}
}

function renderBodyComposition(composition, scanId, scannedAt){
  const host = $('#bodygram-composition');
  if(!host) return;
  const entries = Object.entries(composition || {})
    .map(([key, raw]) => [bodygramCompositionLabel(key), bodygramCompositionValue(key, raw)])
    .filter(([, value]) => value !== null && value !== '');

  if(!entries.length){
    host.innerHTML = '';
    host.hidden = true;
  } else {
    host.innerHTML = '';
    entries.forEach(([label, value]) => {
      const chip = document.createElement('span');
      chip.className = 'bodygram-chip';
      const name = document.createElement('span');
      name.textContent = label;
      const amount = document.createElement('strong');
      amount.textContent = value;
      chip.append(name, amount);
      host.append(chip);
    });

    if(scanId){
      const note = document.createElement('small');
      note.className = 'bodygram-scan-id';
      note.textContent = `Bodygram scan ${scanId}${scannedAt ? ' · ' + scannedAt : ''}`;
      host.append(note);
    }
    host.hidden = false;
  }
}

function renderAllMeasurements(measurements){
  const host = $('#bodygram-all');
  const groupsHost = $('#bodygram-all-groups');
  const count = $('#bodygram-all-count');
  if(!host || !groupsHost) return;

  const items = Array.isArray(measurements) ? measurements.filter(m => m && m.label) : [];
  if(!items.length){
    groupsHost.innerHTML = '';
    host.hidden = true;
    return;
  }

  groupsHost.innerHTML = '';
  const groups = new Map();
  items.forEach(item => {
    const group = item.group || 'Other';
    if(!groups.has(group)) groups.set(group, []);
    groups.get(group).push(item);
  });

  const ordered = [...groups.keys()].sort((a, b) => {
    const ai = BODYGRAM_GROUP_ORDER.indexOf(a);
    const bi = BODYGRAM_GROUP_ORDER.indexOf(b);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });

  ordered.forEach(group => {
    const section = document.createElement('div');
    section.className = 'bodygram-group';
    const heading = document.createElement('h4');
    heading.textContent = group;
    section.append(heading);

    const rows = document.createElement('div');
    rows.className = 'bodygram-rows';
    groups.get(group).forEach(item => {
      const row = document.createElement('div');
      row.className = 'bodygram-row';

      const label = document.createElement('span');
      label.className = 'bodygram-row-label';
      label.textContent = item.label;
      if(item.profile_field) label.dataset.profileField = item.profile_field;

      const value = document.createElement('span');
      value.className = 'bodygram-row-value';
      value.textContent = `${Number(item.value).toFixed(1)} cm`;

      if(item.profile_field){
        const badge = document.createElement('em');
        badge.className = 'bodygram-row-badge';
        badge.textContent = 'profile';
        label.append(' ', badge);
      }

      row.append(label, value);
      rows.append(row);
    });
    section.append(rows);
    groupsHost.append(section);
  });

  if(count) count.textContent = `(${items.length})`;
  host.hidden = false;
}

const BODYGRAM_POSTURE_ROWS = [
  { key: 'ear', label: 'Head tilt', view: 'Front view' },
  { key: 'shoulder', label: 'Shoulder tilt', view: 'Front view' },
  { key: 'topHip', label: 'Pelvis tilt', view: 'Front view' },
];

function formatPostureAngle(value){
  if(!Number.isFinite(value)) return null;
  const rounded = Math.round(value * 10) / 10;
  return `${rounded > 0 ? '+' : ''}${rounded.toFixed(1)}°`;
}

function postureReading(posture){
  const rows = [];
  const front = {};
  (posture?.front?.angles || []).forEach(angle => {
    if(angle && angle.name) front[angle.name] = Number(angle.value);
  });
  BODYGRAM_POSTURE_ROWS.forEach(row => {
    if(Number.isFinite(front[row.key])){
      rows.push({ label: row.label, view: row.view, value: front[row.key] });
    }
  });

  const bodyLine = (posture?.right?.angles || [])
    .find(entry => entry && entry.name === 'bodyLine')?.angles || [];
  if(Number.isFinite(bodyLine[2])) rows.push({ label: 'Back lean', view: 'Right view', value: bodyLine[2] });
  if(Number.isFinite(bodyLine[3])) rows.push({ label: 'Neck lean', view: 'Right view', value: bodyLine[3] });
  return rows;
}

function renderPosture(posture){
  const host = $('#bodygram-posture-rows');
  const section = $('#bodygram-visuals');
  if(!host) return;
  const rows = postureReading(posture);
  host.innerHTML = '';
  if(!rows.length){
    return;
  }
  rows.forEach(row => {
    const item = document.createElement('div');
    item.className = 'bodygram-posture-row';
    const label = document.createElement('span');
    label.textContent = row.label;
    const note = document.createElement('small');
    note.textContent = row.view;
    label.append(note);
    const value = document.createElement('strong');
    value.textContent = formatPostureAngle(row.value);
    item.append(label, value);
    host.append(item);
  });
  if(section) section.hidden = false;
}

function renderBodygramPhotos(frontUrl, rightUrl){
  const strip = $('#bodygram-saved-photos');
  if(!strip) return;
  const front = $('#bodygram-saved-front');
  const right = $('#bodygram-saved-right');
  if(!frontUrl && !rightUrl){
    strip.hidden = true;
    return;
  }
  if(front){
    front.src = frontUrl || '';
    front.hidden = !frontUrl;
  }
  if(right){
    right.src = rightUrl || '';
    right.hidden = !rightUrl;
  }
  strip.hidden = false;
}

/* Band placement mirrors Bodygram's dashboard: the six primary bands are drawn on
 * the main avatar, the rest are built for the per-measurement thumbnails. Anchors
 * are Bodygram heights (cm) with small offsets to land on the anatomical point. */
const BODYGRAM_BAND_SPECS = [
  { key: 'bustGirth', label: 'Bust', anchor: 'bustHeight', side: 'right', primary: true, frameCm: 36 },
  { key: 'waistGirth', label: 'Waist', anchor: 'waistHeight', side: 'right', primary: true, frameCm: 34 },
  { key: 'hipGirth', label: 'Hip', anchor: 'hipHeight', side: 'right', primary: true, frameCm: 36 },
  { key: 'upperArmGirthR', label: 'Upper arm', anchor: 'bustHeight', limb: 'arm', side: 'left', primary: true, frameCm: 18 },
  { key: 'thighGirthR', label: 'Thigh', anchor: 'hipHeight', offset: -11.7, limb: 'leg', side: 'left', primary: true, frameCm: 26 },
  { key: 'calfGirthR', label: 'Calf', anchor: 'kneeHeightR', offset: -15, limb: 'leg', side: 'left', primary: true, frameCm: 22 },
  { key: 'bellyWaistGirth', label: 'Belly waist', anchor: 'bellyWaistHeight', side: 'right', frameCm: 34 },
  { key: 'underBustGirth', label: 'Under bust', anchor: 'bustHeight', offset: -9, side: 'right', frameCm: 30 },
  { key: 'topHipGirth', label: 'Top hip', anchor: 'topHipHeight', side: 'right', frameCm: 32 },
  { key: 'neckGirth', label: 'Neck', anchor: 'backNeckHeight', offset: 3.2, side: 'right', frameCm: 18 },
  { key: 'neckBaseGirth', label: 'Neck base', anchor: 'backNeckHeight', offset: 1.2, side: 'right', frameCm: 22 },
  { key: 'forearmGirthR', label: 'Forearm', anchor: 'waistHeight', offset: 2, limb: 'arm', side: 'left', frameCm: 18 },
  { key: 'wristGirthR', label: 'Wrist', anchor: 'hipHeight', offset: -0.7, limb: 'arm', side: 'left', frameCm: 14 },
  { key: 'midThighGirthR', label: 'Mid-thigh', anchor: 'hipHeight', offset: -21.7, limb: 'leg', side: 'left', frameCm: 22 },
  { key: 'kneeGirthR', label: 'Knee', anchor: 'kneeHeightR', limb: 'leg', side: 'left', frameCm: 20 },
];

const BODYGRAM_LINE_DEFS = [
  {
    key: 'acrossBackShoulderWidth', label: 'Shoulder width',
    from: { anchor: 'backNeckHeight', offset: -2.3, edge: 'outer' },
    to: { anchor: 'backNeckHeight', offset: -2.3, edge: 'right' },
  },
  {
    key: 'backNeckPointToWristLengthR', label: 'Sleeve length',
    from: { anchor: 'backNeckHeight', offset: 0.5, edge: 'outer' },
    via: [{ anchor: 'bustHeight', offset: 1, limb: 'arm', edge: 'outer' }],
    to: { anchor: 'hipHeight', offset: -0.7, limb: 'arm', edge: 'outer' },
  },
  {
    key: 'outerArmLengthR', label: 'Outer arm length',
    from: { anchor: 'bustHeight', offset: 1, limb: 'arm', edge: 'outer' },
    to: { anchor: 'hipHeight', offset: -0.7, limb: 'arm', edge: 'outer' },
  },
  {
    key: 'shoulderToElbowR', label: 'Shoulder to elbow',
    from: { anchor: 'bustHeight', offset: 1, limb: 'arm', edge: 'outer' },
    to: { anchor: 'waistHeight', offset: -5, limb: 'arm', edge: 'outer' },
  },
  {
    key: 'backNeckPointToWaist', label: 'Back length', view: 'back',
    from: { anchor: 'backNeckHeight', offset: -0.5, edge: 'back' },
    to: { anchor: 'waistHeight', offset: 0, edge: 'back' },
  },
  {
    key: 'insideLegLengthR', label: 'Inside leg',
    from: { anchor: 'insideLegHeight', offset: -4, limb: 'leg', edge: 'inner' },
    to: { anchor: 'outerAnkleHeightR', offset: 6, limb: 'leg', edge: 'inner' },
  },
  {
    key: 'outseamR', label: 'Outseam',
    from: { anchor: 'insideLegHeight', offset: -4, limb: 'leg', edge: 'outer' },
    to: { anchor: 'outerAnkleHeightR', offset: 6, limb: 'leg', edge: 'outer' },
  },
];

const BODYGRAM_CARD_ORDER = [
  'waistGirth', 'bustGirth', 'upperArmGirthR', 'hipGirth', 'thighGirthR', 'calfGirthR',
  'neckGirth', 'neckBaseGirth', 'acrossBackShoulderWidth', 'wristGirthR',
  'backNeckPointToWristLengthR', 'outerArmLengthR', 'underBustGirth', 'bellyWaistGirth',
  'backNeckPointToWaist', 'topHipGirth', 'forearmGirthR', 'midThighGirthR', 'kneeGirthR',
  'insideLegLengthR', 'outseamR', 'shoulderToElbowR',
];

function bodygramValues(measurements){
  const values = {};
  (Array.isArray(measurements) ? measurements : []).forEach(entry => {
    if(entry && entry.name && Number.isFinite(Number(entry.value))){
      values[entry.name] = Number(entry.value);
    }
  });
  return values;
}

function bodygramBands(measurements){
  const values = bodygramValues(measurements);
  return BODYGRAM_BAND_SPECS.map(spec => {
    const value = values[spec.key];
    if(!Number.isFinite(value)) return null;
    const base = values[spec.anchor];
    const anchorCm = Number.isFinite(Number(base)) ? Number(base) + (Number(spec.offset) || 0) : null;
    return {
      key: spec.key,
      label: spec.label,
      value,
      side: spec.side,
      limb: spec.limb || '',
      anchorCm,
      frameCm: spec.frameCm || 30,
      primary: Boolean(spec.primary),
    };
  }).filter(Boolean);
}

function bodygramLines(measurements){
  const values = bodygramValues(measurements);
  return BODYGRAM_LINE_DEFS.map(def => {
    const value = Number(values[def.key]);
    if(!Number.isFinite(value)) return null;
    const resolve = end => {
      const base = Number(values[end.anchor]);
      if(!Number.isFinite(base)) return null;
      return { cm: base + (Number(end.offset) || 0), limb: end.limb || '', edge: end.edge || 'outer' };
    };
    const from = resolve(def.from);
    const to = resolve(def.to);
    if(!from || !to) return null;
    const via = (def.via || []).map(resolve).filter(Boolean);
    return { key: def.key, label: def.label, value, from, to, via, view: def.view || 'front' };
  }).filter(Boolean);
}

function bodygramCards(measurements){
  const values = bodygramValues(measurements);
  const specs = BODYGRAM_BAND_SPECS.concat(BODYGRAM_LINE_DEFS.map(def => ({ key: def.key, label: def.label })));
  const byKey = {};
  specs.forEach(spec => { byKey[spec.key] = spec; });
  return BODYGRAM_CARD_ORDER
    .map(key => {
      const value = Number(values[key]);
      const spec = byKey[key];
      if(!spec || !Number.isFinite(value)) return null;
      return { key, label: spec.label, value };
    })
    .filter(Boolean);
}

function renderBodygramCards(measurements, hasAvatar){
  const host = $('#bodygram-cards');
  if(!host) return;
  const cards = bodygramCards(measurements);
  if(!cards.length){
    host.innerHTML = '';
    host.hidden = true;
    return;
  }

  host.innerHTML = '';
  cards.forEach(card => {
    const el = document.createElement('div');
    el.className = 'bodygram-card';

    const label = document.createElement('span');
    label.className = 'bodygram-card-label';
    label.textContent = card.label;

    const value = document.createElement('strong');
    value.className = 'bodygram-card-value';
    value.textContent = Number(card.value).toFixed(1);
    const unit = document.createElement('small');
    unit.textContent = ' cm';
    value.append(unit);

    const image = document.createElement('img');
    image.className = 'bodygram-card-thumb';
    image.alt = `${card.label} on the 3D body model`;
    image.dataset.thumb = card.key;
    image.hidden = true;

    el.append(label, value, image);
    host.append(el);
  });
  host.hidden = false;
  if(hasAvatar !== false) requestBodygramThumbnails(cards.map(card => card.key));
}

function requestBodygramThumbnails(keys){
  if(!keys.length || !window.BodygramAvatar || !window.BodygramAvatar.thumbnails) return;
  window.BodygramAvatar.thumbnails(keys).then(urls => {
    Object.keys(urls || {}).forEach(key => {
      document.querySelectorAll(`.bodygram-card-thumb[data-thumb="${key}"]`).forEach(image => {
        image.src = urls[key];
        image.hidden = false;
      });
    });
  }).catch(() => {});
}

function setBodygramDownload(url){
  const link = $('#bodygram-avatar-download');
  if(!link) return;
  if(!url){
    link.hidden = true;
    link.removeAttribute('href');
    return;
  }
  link.href = url;
  link.download = url.split('/').pop() || 'bodygram-avatar.obj';
  link.hidden = false;
}

function toggleBodygramFullscreen(){
  const stage = $('#bodygram-avatar-stage');
  if(!stage) return;
  const active = document.fullscreenElement || document.webkitFullscreenElement;
  if(active){
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if(exit) exit.call(document);
    return;
  }
  const request = stage.requestFullscreen || stage.webkitRequestFullscreen;
  if(!request){
    toast('Fullscreen is not available in this browser.');
    return;
  }
  const pending = request.call(stage);
  if(pending && pending.catch) pending.catch(() => toast('Fullscreen was blocked by the browser.'));
}

function syncBodygramFullscreenLabel(){
  const button = $('#bodygram-avatar-full');
  if(!button) return;
  const active = document.fullscreenElement || document.webkitFullscreenElement;
  button.textContent = active ? 'Exit 360° view' : '360° view';
}

['fullscreenchange', 'webkitfullscreenchange'].forEach(name => {
  document.addEventListener(name, syncBodygramFullscreenLabel);
});

function renderBodygramAvatar(result){
  const url = result.avatar_url;
  const section = $('#bodygram-visuals');
  const stage = $('#bodygram-avatar-stage');
  if(!stage) return;
  if(!url){
    if(window.BodygramAvatar) window.BodygramAvatar.destroy();
    if(section) section.hidden = true;
    setBodygramDownload('');
    return;
  }
  if(section) section.hidden = false;
  setBodygramDownload(url);
  if(window.BodygramAvatar){
    const all = result.all_measurements || result.measurements;
    window.BodygramAvatar.load(url, {
      bands: bodygramBands(all),
      lines: bodygramLines(all),
      heightCm: Number(result.height_cm) || 0,
    });
  } else {
    const status = $('#bodygram-avatar-status');
    if(status){
      status.textContent = '3D viewer could not load.';
      status.classList.add('is-error');
      status.hidden = false;
    }
  }
}

function deleteBodygramPhotos(){
  const button = $('#bodygram-delete-photos');
  if(button){ button.disabled = true; }
  fetch('/api/measurements/bodygram/photos/delete/', { method: 'POST' })
    .then(response => {
      if(!response.ok) throw new Error('Could not delete the photos.');
      const strip = $('#bodygram-saved-photos');
      if(strip) strip.hidden = true;
      const saved = readLocal('bodygram-result', null);
      if(saved){
        saved.front_photo_url = '';
        saved.right_photo_url = '';
        saveLocal('bodygram-result', saved);
      }
      toast('Scan photos deleted.');
    })
    .catch(error => toast(error.message || 'Could not delete the photos.'))
    .finally(() => { if(button){ button.disabled = false; } });
}

function renderBodygramResult(result){
  if(!result) return;
  const all = result.all_measurements || result.measurements || [];
  renderBodyComposition(result.body_composition, result.scan_id, result.scanned_at);
  renderBodygramCards(all, Boolean(result.avatar_url));
  renderAllMeasurements(all);
  renderBodygramPhotos(result.front_photo_url, result.right_photo_url);
  renderPosture(result.posture);
  renderBodygramAvatar(result);
  saveLocal('bodygram-result', {
    scan_id: result.scan_id || '',
    scanned_at: result.scanned_at || '',
    body_composition: result.body_composition || null,
    posture: result.posture || null,
    avatar_url: result.avatar_url || '',
    height_cm: result.height_cm || 0,
    front_photo_url: result.front_photo_url || '',
    right_photo_url: result.right_photo_url || '',
    all_measurements: all,
  });
}

function loadBodygramResult(){
  let saved = null;
  const embedded = $('#bodygram-saved');
  if(embedded){
    try { saved = JSON.parse(embedded.textContent || 'null'); } catch(e){ saved = null; }
  }
  if(!saved) saved = readLocal('bodygram-result', null);
  if(!saved) return;
  renderBodygramResult(saved);
}

function runBodygramScan(){
  const front = $('#bodygram-front')?.files?.[0];
  const right = $('#bodygram-right')?.files?.[0];
  const button = $('#bodygram-submit');
  const age = $('#bodygram-age')?.value;
  const height = $('#bodygram-height')?.value;
  const weight = $('#bodygram-weight')?.value;

  if(!front || !right){
    setBodygramStatus('Upload both a front photo and a right-side photo.', 'error');
    toast('Upload both photos for a Bodygram scan.');
    return;
  }
  if(!age || !height || !weight){
    setBodygramStatus('Enter your age, height, and weight before scanning.', 'error');
    toast('Add age, height, and weight first.');
    return;
  }

  const formData = new FormData();
  formData.append('front_photo', front);
  formData.append('right_photo', right);
  formData.append('gender', $('#bodygram-gender')?.value || 'female');
  formData.append('age', age);
  formData.append('height', height);
  formData.append('weight', weight);

  const originalLabel = button?.textContent;
  if(button){ button.disabled = true; button.textContent = 'Scanning with Bodygram…'; }
  setBodygramStatus('Bodygram is estimating your measurements. This can take up to a minute.');

  fetch('/api/measurements/bodygram/', { method: 'POST', body: formData })
    .then(async response => {
      let payload = {};
      try { payload = await response.json(); } catch(e) {}
      if(!response.ok) throw new Error(payload.error || `Bodygram scan failed (HTTP ${response.status}).`);
      return payload;
    })
    .then(payload => {
      const values = payload.measurements || {};
      Object.entries(values).forEach(([field, value]) => {
        $$(`[data-measure="${field}"]`).forEach(el => {
          el.dataset.cm = value;
          el.value = value;
        });
      });
      if(Object.keys(values).length){
        switchUnit('cm');
        const stored = {};
        $$('[data-measure]').forEach(el => stored[el.dataset.measure] = el.value);
        stored.unit = 'cm';
        saveLocal('measurements', stored);
      }
      renderBodygramResult(payload);
      const count = Object.keys(values).length;
      const total = (payload.all_measurements || []).length;
      const fat = bodygramCompositionValue('bodyFatPercentage',
        payload.body_composition?.bodyFatPercentage);
      const extra = fat ? ` Body fat estimate: ${fat}.` : '';
      const detail = total > count ? ` Bodygram returned ${total} in total — open the full list.` : '';
      setBodygramStatus(`Bodygram estimated ${count} tailoring measurement${count === 1 ? '' : 's'} and saved them to your profile.${detail}${extra} Review the form below.`, 'success');
      toast('Measurements estimated with Bodygram.');
    })
    .catch(error => {
      const message = error.message || 'Bodygram scan failed. Please try again.';
      setBodygramStatus(message, 'error');
      toast(message);
    })
    .finally(() => {
      if(button){ button.disabled = false; button.textContent = originalLabel || 'Estimate measurements from photos'; }
    });
}

function updateBudget(value){
  const el = $('#budget-value') || $('#brief-budget-display');
  if(el) el.textContent = '₦' + Number(value).toLocaleString('en-NG');
}

/* ==========================================================================
   STYLE INTELLIGENCE & FASHN VTON 1.5 INTEGRATION ENGINE
   ========================================================================== */

const FASHION_CATALOG = [
  {
    id: 'senator-navy',
    title: 'Classic Royal Navy Senator Set',
    category: 'senator',
    vtonCategory: 'one-pieces',
    price: 45000,
    priceLabel: '₦45,000',
    fabric: 'Italian Cashmere Wool',
    silhouette: 'Tailored Native',
    image: 'https://images.unsplash.com/photo-1617137968427-85924c800a22?auto=format&fit=crop&w=900&q=85',
    tryonImage: 'https://images.unsplash.com/photo-1617137968427-85924c800a22?auto=format&fit=crop&w=900&q=85',
    description: 'Structured navy tailoring with clean Mandarin collar and matching trousers.',
    stylingAdvice: 'Pair with burnished cognac monkstrap shoes, a silver timepiece, and an optional navy velvet fila cap for owambes.'
  },
  {
    id: 'ankara-heritage',
    title: 'Ankara Heritage Celebration Gown',
    category: 'ankara',
    vtonCategory: 'one-pieces',
    price: 38000,
    priceLabel: '₦38,000',
    fabric: 'Authentic Dutch Wax Print',
    silhouette: 'Hourglass Wrap',
    image: 'https://upload.wikimedia.org/wikipedia/commons/4/4d/Ankara_dress.jpg',
    tryonImage: 'https://upload.wikimedia.org/wikipedia/commons/4/4d/Ankara_dress.jpg',
    description: 'Rich jewel tones with geometric wax print, sweetheart neckline and structured sleeves.',
    stylingAdvice: 'Complement with gold drop earrings, neutral block heels, and a minimalist metallic clutch.'
  },
  {
    id: 'senator-charcoal',
    title: 'Modern Charcoal & Wine Senator',
    category: 'senator',
    vtonCategory: 'one-pieces',
    price: 52000,
    priceLabel: '₦52,000',
    fabric: 'Super 120s Polished Wool',
    silhouette: 'Slim Fit',
    image: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=900&q=85',
    tryonImage: 'https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=900&q=85',
    description: 'Crisp charcoal base highlighted with subtle wine embroidery along the chest placket.',
    stylingAdvice: 'Wear with black patent loafers or Oxford shoes. Excellent for both formal ceremonies and evening receptions.'
  },
  {
    id: 'ankara-maxi',
    title: 'Cowries Print Statement Maxi Gown',
    category: 'ankara',
    vtonCategory: 'one-pieces',
    price: 42000,
    priceLabel: '₦42,000',
    fabric: 'African Cotton Wax Print',
    silhouette: 'Flowing Maxi',
    image: 'https://upload.wikimedia.org/wikipedia/commons/0/0b/Cowries_Print_Maxi_Dress.JPG',
    tryonImage: 'https://upload.wikimedia.org/wikipedia/commons/0/0b/Cowries_Print_Maxi_Dress.JPG',
    description: 'Floor-length dramatic African print silhouette with flared movement.',
    stylingAdvice: 'Style with chunky bronze bangles, strappy sandals, and understated ear studs to let the print lead.'
  },
  {
    id: 'formal-double-breasted',
    title: 'Executive Midnight Double-Breasted Suit',
    category: 'formal',
    vtonCategory: 'tops',
    price: 65000,
    priceLabel: '₦65,000',
    fabric: 'Italian Wool Blend',
    silhouette: 'Executive Tailored',
    image: 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=900&q=85',
    tryonImage: 'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=900&q=85',
    description: 'Sharp peak-lapel jacket with structured shoulders and tapered trousers.',
    stylingAdvice: 'Ideal for boardrooms and galas. Pair with a crisp white poplin shirt, silk pocket square, and derby shoes.'
  },
  {
    id: 'casual-ankara-blazer',
    title: 'Contemporary Ankara Fusion Blazer',
    category: 'ankara',
    vtonCategory: 'tops',
    price: 36000,
    priceLabel: '₦36,000',
    fabric: 'Wax Print & Cotton Twill',
    silhouette: 'Smart Casual',
    image: 'https://upload.wikimedia.org/wikipedia/commons/8/8e/A_Nigerian_lady_in_Ankara_clothing.jpg',
    tryonImage: 'https://upload.wikimedia.org/wikipedia/commons/8/8e/A_Nigerian_lady_in_Ankara_clothing.jpg',
    description: 'Vibrant print panels tailored into a modern unlined blazer.',
    stylingAdvice: 'Pair with high-waisted neutral slacks or dark denim and sleek mules for creative business casual.'
  },
  {
    id: 'agbada-grandeur',
    title: 'Grandeur 3-Piece Agbada Set',
    category: 'agbada',
    vtonCategory: 'one-pieces',
    price: 85000,
    priceLabel: '₦85,000',
    fabric: 'Swiss Damask & Brocade',
    silhouette: 'Regal Flow',
    image: 'https://images.unsplash.com/photo-1525507119028-ed4c629a60a3?auto=format&fit=crop&w=900&q=85',
    tryonImage: 'https://images.unsplash.com/photo-1525507119028-ed4c629a60a3?auto=format&fit=crop&w=900&q=85',
    description: 'Intricate cord embroidery across chest and wide flowing sleeves.',
    stylingAdvice: 'Complete with a traditional Abeti Aja or Gobi cap, coral bead necklace, and hand-crafted velvet slippers.'
  }
];

let activeGarment = FASHION_CATALOG[0];
let dedicatedTryonDesign = null;
let dedicatedPersonFile = null;
let dedicatedGarmentFile = null;

function selectTryonDesign(button){
  dedicatedTryonDesign = {
    id: button.dataset.designId,
    image: button.dataset.designImage,
    category: button.dataset.designCategory || 'one-pieces'
  };
  markActive(button);
  const status = $('#dedicated-garment-status');
  if(status) status.textContent = 'Catalog garment selected. Upload a custom garment to replace it.';
  const preview = $('#dedicated-garment-card-preview');
  if(preview){
    preview.src = button.dataset.designImage;
    preview.style.display = 'block';
  }
  const name = $('#dedicated-garment-name');
  if(name) name.textContent = button.querySelector('span')?.textContent || 'Catalog garment selected';
  toast('Garment selected for virtual try-on.');
}

function runDedicatedTryOn(){
  const status = $('#tryon-status');
  const preview = $('#user-photo-preview');
  const personFile = dedicatedPersonFile || $('#dedicated-person-upload')?.files?.[0];
  const garmentFile = dedicatedGarmentFile || $('#dedicated-garment-upload')?.files?.[0];
  const selected = dedicatedTryonDesign || document.querySelector('.mini-design.selected');
  const designId = selected?.id || selected?.dataset?.designId;
  const garmentUrl = dedicatedTryonDesign?.image || selected?.dataset?.designImage;
  const category = dedicatedTryonDesign?.category || selected?.dataset?.designCategory || 'one-pieces';

  if(!personFile){
    if(status){ status.textContent = 'Upload a person photo before generating.'; status.style.display = 'block'; }
    toast('Upload your person photo first.');
    return;
  }
  if(!garmentFile && !garmentUrl){
    if(status){ status.textContent = 'Select a catalog garment or upload your own garment.'; status.style.display = 'block'; }
    toast('Select or upload a garment first.');
    return;
  }

  const formData = new FormData();
  formData.append('design_id', designId || '');
  formData.append('category', category);
  formData.append('model_preset', 'custom');
  formData.append('garment_photo_type', garmentFile ? 'flat-lay' : 'model');
  formData.append('person_image', personFile);
  if(garmentFile) formData.append('garment_image', garmentFile);
  else formData.append('garment_image_url', garmentUrl);

  if(status){
    status.textContent = 'Rendering your look with FASHN VTON 1.5. This can take up to a minute...';
    status.style.display = 'block';
  }
  $('#dedicated-vton-loader')?.style.setProperty('display', 'flex');
  fetch('/api/vton/tryon/', { method: 'POST', body: formData })
    .then(async response => {
      let data = {};
      try { data = await response.json(); } catch (e) {}
      if(!response.ok) throw new Error(data.error || `Try-on failed (HTTP ${response.status}).`);
      return data;
    })
    .then(data => {
      if(preview){
        preview.src = data.result_image;
        preview.style.display = 'block';
      }
      $('#tryon-stage-label').textContent = 'Generated result';
      $('.tryon-result-copy')?.style.setProperty('display', 'none');
      if(status){
        const engine = data.provider === 'gemini' ? 'Gemini' : 'FASHN VTON 1.5';
        status.textContent = `Your generated look is ready (${engine}).`;
        status.className = 'tryon-status is-success';
        status.style.display = 'block';
      }
      toast('Virtual try-on generated.');
    })
    .catch(error => {
      const message = error.message || 'Virtual try-on failed. Please try again.';
      if(status){
        status.textContent = message;
        status.className = 'tryon-status is-error';
        status.style.display = 'block';
      }
      toast(message);
    })
    .finally(() => {
      $('#dedicated-vton-loader')?.style.setProperty('display', 'none');
    });
}

/* Transfer garment to FASHN VTON Studio */
function loadGarmentToStudio(garmentId){
  let found = FASHION_CATALOG.find(x => x.id === garmentId || String(x.id) === String(garmentId));
  if(!found){
    // search by title or slug
    found = FASHION_CATALOG.find(x => x.slug === garmentId);
  }
  if(!found && window.__serverLooks){
    found = window.__serverLooks.find(x => String(x.id) === String(garmentId) || x.slug === garmentId);
  }
  if(!found) return;
  activeGarment = found;

  const box = $('#active-garment-box');
  if(box){
    box.classList.remove('highlight');
    void box.offsetWidth;
    box.classList.add('highlight');
  }

  const img = $('#ag-image');
  const title = $('#ag-title');
  const desc = $('#ag-desc');
  const price = $('#ag-price');
  const tag = $('#ag-tag');
  const categoryPill = $('#ag-category');
  const catSelect = $('#vton-category-select');

  if(img) img.src = found.image;
  if(title) title.textContent = found.title;
  if(desc) desc.textContent = found.description;
  if(price) price.textContent = found.priceLabel;
  if(tag) tag.textContent = found.fabric;
  if(categoryPill) categoryPill.textContent = (found.category || 'Senator').toUpperCase();
  if(catSelect) catSelect.value = found.vtonCategory || 'one-pieces';

  const resultBadge = $('#result-badge');
  if(resultBadge) resultBadge.textContent = 'Garment Loaded: ' + found.title;

  toast(`Loaded "${found.title}" into FASHN VTON Studio!`);

  if(window.innerWidth <= 1050){
    switchMobileTab('studio');
  }
}

/* Run FASHN VTON Try-On Process */
function runVTONTryOn(){
  const loader = $('#vton-loader');
  const loaderTitle = $('#vton-loader-title');
  const loaderStep = $('#vton-loader-step');
  const outputImg = $('#vton-output-image');
  const badge = $('#result-badge');
  const status = $('#vton-status');

  if(!loader) return;

  if(status){
    status.textContent = '';
    status.className = 'tryon-status';
    status.style.display = 'none';
  }

  loader.style.display = 'flex';
  if(loaderTitle) loaderTitle.textContent = 'FASHN VTON 1.5 Neural Rendering...';
  if(loaderStep) loaderStep.textContent = 'Step 1/3: Analyzing pose & person segmentation...';

  setTimeout(() => {
    if(loaderStep) loaderStep.textContent = 'Step 2/3: Applying pixel-space MMDiT diffusion...';
  }, 900);

  setTimeout(() => {
    if(loaderStep) loaderStep.textContent = 'Step 3/3: Harmonizing fabric drape & lighting...';
  }, 1800);

  // Send the original images to Django; the server calls the AI provider.
  const modelPreset = $('.model-thumb.selected')?.dataset.model || 'male-1';
  const formData = new FormData();
  if(/^\d+$/.test(String(activeGarment.id))) formData.append('design_id', activeGarment.id);
  formData.append('model_preset', modelPreset);
  formData.append('category', $('#vton-category-select')?.value || activeGarment.vtonCategory || 'one-pieces');
  formData.append('garment_photo_type', 'model');
  const personUpload = $('#vton-user-upload')?.files?.[0];
  if(personUpload) formData.append('person_image', personUpload);
  else formData.append('person_image_url', $('.model-thumb.selected')?.dataset.img || '');
  formData.append('garment_image_url', activeGarment.image);

  fetch('/api/vton/tryon/', { method: 'POST', body: formData })
    .then(async response => {
      let data = {};
      try { data = await response.json(); } catch (e) {}
      if(!response.ok) throw new Error(data.error || `Try-on failed (HTTP ${response.status}).`);
      return data;
    })
    .then(data => {
      const engine = data.provider === 'gemini' ? 'Gemini' : 'FASHN VTON 1.5';
      if(outputImg) outputImg.src = data.result_image;
      if(badge) badge.textContent = `✨ ${engine} Render: ${activeGarment.title}`;
      if(status){
        status.textContent = `Look generated with ${engine}. Save it to your wardrobe when you are happy.`;
        status.className = 'tryon-status is-success';
        status.style.display = 'block';
      }
      toast('Virtual try-on generated!');
    })
    .catch(error => {
      const message = error.message || 'Virtual try-on failed. Please try again.';
      if(badge) badge.textContent = 'Try-On Failed';
      if(status){
        status.textContent = message;
        status.className = 'tryon-status is-error';
        status.style.display = 'block';
      }
      toast(message);
    })
    .finally(() => {
      loader.style.display = 'none';
    });
}

/* Fallback local generator */
function generateStylistFallback(userInput){
  const text = userInput.toLowerCase();
  const occasion = $('#brief-occasion')?.value || 'any';
  const styleBrief = $('#brief-style')?.value || 'any';
  const budget = Number($('#brief-budget')?.value || 50000);

  let advice = '';
  let matchedLooks = [];

  if(text.includes('senator') || styleBrief === 'senator' || text.includes('native') || text.includes('traditional')){
    advice = "For modern Senator wear, structured Italian cashmere or high-twist polished wool delivers that sharp, non-creasing drape. Keep the collar clean and pair with tailored trousers that break just above your loafers.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'senator');
  } else if(text.includes('ankara') || styleBrief === 'ankara' || text.includes('print') || text.includes('wax')){
    advice = "With Ankara styling, the key is balancing vibrant patterns with thoughtful tailoring. Pair an authentic wax print with minimalist accessories (burnished gold or neutral leather) so the pattern speaks with elegance.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'ankara');
  } else if(text.includes('wedding') || text.includes('owambe') || occasion === 'wedding' || text.includes('party')){
    advice = "For weddings and celebratory Owambes, rich jewel tones (Navy, Wine, Emerald, Champagne) are timeless favorites. A sharp Senator set or a regal Agbada gives an authoritative, celebratory presence.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'senator' || x.category === 'agbada');
  } else if(text.includes('work') || text.includes('corporate') || text.includes('office') || occasion === 'work' || text.includes('meeting') || text.includes('suit')){
    advice = "For boardroom presence, choose tailored silhouettes with clean lines. Double-breasted cuts or structured blazer sets project authority while keeping you comfortable throughout a busy day.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'formal' || x.id === 'casual-ankara-blazer');
  } else if(text.includes('budget') || text.includes('cheap') || text.includes('cost') || text.includes('price') || text.includes('under')){
    advice = `Here are standout pieces that deliver luxury craftsmanship within your budget range (up to ₦${budget.toLocaleString('en-NG')}). Fabric quality and clean finishing make all the difference.`;
    matchedLooks = FASHION_CATALOG.filter(x => x.price <= budget);
    if(matchedLooks.length === 0) matchedLooks = [FASHION_CATALOG[1], FASHION_CATALOG[0]];
  } else if(text.includes('color') || text.includes('colour') || text.includes('wine') || text.includes('navy') || text.includes('emerald') || text.includes('gold')){
    advice = "Color harmony tip: Royal Navy pairs masterfully with Cognac brown and Silver. Wine and Burgundy look majestic when balanced with Champagne Gold or Charcoal accents. Emerald green looks striking against warm skin tones.";
    matchedLooks = [FASHION_CATALOG[0], FASHION_CATALOG[2]];
  } else {
    advice = "Here is a hand-picked recommendation that balances contemporary fit with rich texture. You can preview this look on a model using FASHN VTON 1.5 in the fitting studio on the right!";
    matchedLooks = [FASHION_CATALOG[0], FASHION_CATALOG[1]];
  }

  return { advice, looks: matchedLooks.slice(0, 2) };
}

/* Send Stylist Message Flow with Django API */
function sendStylistMessage(){
  const input = $('#stylist-input');
  if(!input || !input.value.trim()) return;

  const userQuery = input.value.trim();
  const list = $('#chat-messages');

  // Append user bubble
  const userMsg = document.createElement('div');
  userMsg.className = 'message user';
  const up = document.createElement('p');
  up.textContent = userQuery;
  userMsg.appendChild(up);
  list.appendChild(userMsg);
  input.value = '';
  list.scrollTop = list.scrollHeight;

  // Append typing bubble
  const typing = document.createElement('div');
  typing.className = 'typing-bubble';
  typing.id = 'chat-typing';
  typing.innerHTML = '<span></span><span></span><span></span>';
  list.appendChild(typing);
  list.scrollTop = list.scrollHeight;

  const occasion = $('#brief-occasion')?.value || 'any';
  const styleBrief = $('#brief-style')?.value || 'any';
  const budget = Number($('#brief-budget')?.value || 50000);

  // Call Django API
  fetch('/api/stylist/chat/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: userQuery,
      occasion: occasion,
      style: styleBrief,
      budget: budget
    })
  })
  .then(r => r.json())
  .then(data => {
    renderStylistResponse(data.advice, data.looks);
  })
  .catch(() => {
    // Local fallback if API unavailable
    const fallback = generateStylistFallback(userQuery);
    renderStylistResponse(fallback.advice, fallback.looks);
  });
}

function renderStylistResponse(advice, looks){
  const list = $('#chat-messages');
  const typingEl = $('#chat-typing');
  if(typingEl) typingEl.remove();

  window.__serverLooks = looks;

  const stylistMsg = document.createElement('div');
  stylistMsg.className = 'message';

  const author = document.createElement('div');
  author.className = 'message-author';
  author.textContent = 'Fitverse Stylist';
  stylistMsg.appendChild(author);

  const ap = document.createElement('p');
  ap.textContent = advice;
  stylistMsg.appendChild(ap);

  looks.forEach(look => {
    const card = document.createElement('div');
    card.className = 'look-card';
    card.innerHTML = `
      <img class="look-thumb" src="${look.image}" alt="${look.title}">
      <div class="look-info">
        <div>
          <div class="look-title-row">
            <h4 class="look-title">${look.title}</h4>
          </div>
          <p class="look-desc">${look.description}</p>
          <div class="look-meta">
            <span class="price">${look.priceLabel || '₦' + Number(look.price).toLocaleString('en-NG')}</span>
            <span class="tag">${look.fabric || 'Native Textile'}</span>
            <span class="tag">${look.silhouette || 'Tailored'}</span>
          </div>
        </div>
        <div class="look-actions">
          <button type="button" class="btn-tryon-card" onclick="loadGarmentToStudio('${look.id}')">
            ⚡ Try On in Studio
          </button>
          <button type="button" class="btn-save-look-card" onclick="toggleFavorite(this, '${look.id}')" title="Save to wardrobe">
            ♡
          </button>
        </div>
      </div>
    `;
    stylistMsg.appendChild(card);
  });

  list.appendChild(stylistMsg);
  list.scrollTop = list.scrollHeight;
}

/* Mobile View Switcher */
function switchMobileTab(target){
  const chatPanel = $('#studio-chat-panel');
  const tryonPanel = $('#studio-tryon-panel');
  const btnChat = $('#btn-mobile-chat');
  const btnStudio = $('#btn-mobile-studio');

  if(target === 'chat'){
    if(chatPanel) chatPanel.style.display = 'flex';
    if(tryonPanel) tryonPanel.style.display = 'none';
    btnChat?.classList.add('active');
    btnStudio?.classList.remove('active');
  } else {
    if(chatPanel) chatPanel.style.display = 'none';
    if(tryonPanel) tryonPanel.style.display = 'flex';
    btnStudio?.classList.add('active');
    btnChat?.classList.remove('active');
  }
}

/* Setup Studio Event Handlers */
function setupStudioEvents(){
  $('#btn-clear-chat')?.addEventListener('click', () => {
    const list = $('#chat-messages');
    if(list){
      list.innerHTML = `
        <div class="message">
          <div class="message-author">Fitverse Stylist</div>
          <p>Conversation reset. What look or occasion shall we explore today?</p>
        </div>
      `;
    }
    toast('Chat conversation reset.');
  });

  const briefBudget = $('#brief-budget');
  if(briefBudget){
    briefBudget.addEventListener('input', () => {
      updateBudget(briefBudget.value);
    });
  }

  $$('.model-thumb').forEach(btn => {
    btn.addEventListener('click', () => {
      markActive(btn);
      const imgUrl = btn.dataset.img;
      const previewImg = $('#vton-output-image');
      if(previewImg && imgUrl){
        previewImg.src = imgUrl;
        const badge = $('#result-badge');
        if(badge) badge.textContent = 'Model Selected: ' + btn.querySelector('span')?.textContent;
      }
    });
  });

  const uploadInput = $('#vton-user-upload');
  if(uploadInput){
    uploadInput.addEventListener('change', () => {
      const file = uploadInput.files?.[0];
      if(!file) return;
      if(!file.type.startsWith('image/')){
        toast('Please upload a valid image file.');
        return;
      }

      const url = URL.createObjectURL(file);
      const previewImg = $('#vton-output-image');
      if(previewImg){
        previewImg.src = url;
        const badge = $('#result-badge');
        if(badge) badge.textContent = 'Custom Photo Loaded';
      }
      $$('.model-thumb').forEach(x => x.classList.remove('selected'));
      toast('Custom photo loaded into fitting canvas!');
    });
  }

  const dedicatedPersonUpload = $('#dedicated-person-upload');
  if(dedicatedPersonUpload){
    dedicatedPersonUpload.addEventListener('change', () => {
      const file = dedicatedPersonUpload.files?.[0];
      if(!file || !file.type.startsWith('image/')) return toast('Please upload a valid person image.');
      if(file.size > 12 * 1024 * 1024) return toast('Choose a person image smaller than 12 MB.');
      dedicatedPersonFile = file;
      const objectUrl = URL.createObjectURL(file);
      const preview = $('#user-photo-preview');
      if(preview) preview.src = objectUrl;
      const cardPreview = $('#dedicated-person-card-preview');
      if(cardPreview){ cardPreview.src = objectUrl; cardPreview.style.display = 'block'; }
      const cardName = $('#dedicated-person-name');
      if(cardName) cardName.textContent = file.name;
      $('#tryon-stage-label').textContent = 'Your photo';
      toast('Person photo loaded.');
    });
  }

  const dedicatedGarmentUpload = $('#dedicated-garment-upload');
  if(dedicatedGarmentUpload){
    dedicatedGarmentUpload.addEventListener('change', () => {
      const file = dedicatedGarmentUpload.files?.[0];
      if(!file || !file.type.startsWith('image/')) return toast('Please upload a valid garment image.');
      if(file.size > 12 * 1024 * 1024) return toast('Choose a garment image smaller than 12 MB.');
      dedicatedGarmentFile = file;
      const status = $('#dedicated-garment-status');
      if(status) status.textContent = `${file.name} selected. It will replace the catalog garment.`;
      const preview = $('#dedicated-garment-card-preview');
      if(preview){ preview.src = URL.createObjectURL(file); preview.style.display = 'block'; }
      const name = $('#dedicated-garment-name');
      if(name) name.textContent = file.name;
      toast('Custom garment loaded.');
    });
  }

  $('#btn-run-tryon')?.addEventListener('click', runVTONTryOn);

  $('#tab-canvas-btn')?.addEventListener('click', () => {
    $('#tab-canvas-btn')?.classList.add('active');
    $('#tab-live-btn')?.classList.remove('active');
    const cView = $('#vton-canvas-view');
    const lView = $('#vton-live-view');
    if(cView) cView.style.display = 'block';
    if(lView) lView.style.display = 'none';
  });

  $('#tab-live-btn')?.addEventListener('click', () => {
    $('#tab-live-btn')?.classList.add('active');
    $('#tab-canvas-btn')?.classList.remove('active');
    const cView = $('#vton-canvas-view');
    const lView = $('#vton-live-view');
    if(cView) cView.style.display = 'none';
    if(lView) lView.style.display = 'block';
  });

  $('#btn-mobile-chat')?.addEventListener('click', () => switchMobileTab('chat'));
  $('#btn-mobile-studio')?.addEventListener('click', () => switchMobileTab('studio'));

  $('#btn-save-look')?.addEventListener('click', saveLook);

  $('#btn-copy-garment-url')?.addEventListener('click', () => {
    if(navigator.clipboard && activeGarment.image){
      navigator.clipboard.writeText(activeGarment.image).then(() => {
        toast('Garment image URL copied to clipboard!');
      }).catch(() => {
        toast('Link ready: ' + activeGarment.title);
      });
    } else {
      toast('Garment: ' + activeGarment.title);
    }
  });
}

/* Global Click & Init Listeners */
document.addEventListener('click', e => {
  const toastTrigger = e.target.closest('[data-toast]');
  if(toastTrigger){
    e.preventDefault();
    toast(toastTrigger.dataset.toast);
  }

  const favTrigger = e.target.closest('[data-favorite]');
  if(favTrigger) toggleFavorite(favTrigger, favTrigger.dataset.favorite);

  const choiceTrigger = e.target.closest('[data-choice]');
  if(choiceTrigger) markActive(choiceTrigger);

  const promptTrigger = e.target.closest('[data-prompt]');
  if(promptTrigger && $('#stylist-input')){
    $('#stylist-input').value = promptTrigger.dataset.prompt;
    sendStylistMessage();
  }

  const suggestionTrigger = e.target.closest('[data-suggestion]');
  if(suggestionTrigger && $('#stylist-input')){
    $('#stylist-input').value = suggestionTrigger.dataset.suggestion;
    sendStylistMessage();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  loadMeasurements();
  loadBodygramResult();

  const favs = readLocal('favorites', []);
  $$('[data-favorite]').forEach(b => {
    if(favs.includes(String(b.dataset.favorite))) b.textContent = '♥';
  });

  const form = $('#stylist-form');
  if(form){
    form.addEventListener('submit', e => {
      e.preventDefault();
      sendStylistMessage();
    });
  }

  const search = $('#design-search');
  if(search) search.addEventListener('input', filterProducts);

  const cat = $('#category-filter');
  if(cat) cat.addEventListener('change', filterProducts);

  const budget = $('#budget');
  if(budget){
    updateBudget(budget.value);
    budget.addEventListener('input', () => updateBudget(budget.value));
  }

  setupStudioEvents();

  const firstTryonDesign = $('#dedicated-tryon .mini-design');
  if(firstTryonDesign) selectTryonDesign(firstTryonDesign);
});
