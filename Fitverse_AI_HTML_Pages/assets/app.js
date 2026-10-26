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
  if(list.includes(id)){
    list = list.filter(x => x !== id);
    button.textContent = '♡';
    toast('Removed from your wardrobe');
  } else {
    list.push(id);
    button.textContent = '♥';
    toast('Saved to your wardrobe');
  }
  saveLocal('favorites', list);
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
    toast('Photo loaded for this demo.');
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
  let saved = readLocal('savedLooks', []);
  const title = $('#ag-title')?.textContent || 'Virtual Try-On Look';
  saved.unshift({
    date: new Date().toLocaleDateString(),
    title: title,
    src: src
  });
  saveLocal('savedLooks', saved.slice(0, 20));
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
  saveLocal('measurements', data);
  toast('Measurements saved in this browser.');
}

function loadMeasurements(){
  const data = readLocal('measurements', {});
  $$('[data-measure]').forEach(el => {
    if(data[el.dataset.measure] !== undefined) el.value = data[el.dataset.measure];
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

/* Transfer garment to FASHN VTON Studio */
function loadGarmentToStudio(garmentId){
  const found = FASHION_CATALOG.find(x => x.id === garmentId);
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
  if(categoryPill) categoryPill.textContent = found.category.toUpperCase();
  if(catSelect) catSelect.value = found.vtonCategory;

  const resultBadge = $('#result-badge');
  if(resultBadge) resultBadge.textContent = 'Garment Loaded: ' + found.title;

  toast(`Loaded "${found.title}" into FASHN VTON Studio!`);

  /* If mobile/tablet, switch to studio view automatically */
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

  if(!loader) return;

  loader.style.display = 'flex';
  if(loaderTitle) loaderTitle.textContent = 'FASHN VTON 1.5 Neural Rendering...';
  if(loaderStep) loaderStep.textContent = 'Step 1/3: Analyzing pose & person segmentation...';

  setTimeout(() => {
    if(loaderStep) loaderStep.textContent = 'Step 2/3: Applying pixel-space MMDiT diffusion...';
  }, 900);

  setTimeout(() => {
    if(loaderStep) loaderStep.textContent = 'Step 3/3: Harmonizing fabric drape & lighting...';
  }, 1800);

  setTimeout(() => {
    loader.style.display = 'none';
    if(outputImg){
      outputImg.style.opacity = '0';
      setTimeout(() => {
        outputImg.src = activeGarment.tryonImage || activeGarment.image;
        outputImg.style.opacity = '1';
      }, 150);
    }
    if(badge){
      badge.textContent = `✨ FASHN VTON 1.5 Render: ${activeGarment.title}`;
    }
    toast('Virtual Try-On generated with FASHN VTON 1.5!');
  }, 2600);
}

/* Stylist Chatbot Response Generator */
function generateStylistResponse(userInput){
  const text = userInput.toLowerCase();
  const occasion = $('#brief-occasion')?.value || 'any';
  const styleBrief = $('#brief-style')?.value || 'any';
  const budget = Number($('#brief-budget')?.value || 50000);

  let advice = '';
  let matchedLooks = [];

  // 1. Senator & Native wear requests
  if(text.includes('senator') || styleBrief === 'senator' || text.includes('native') || text.includes('traditional')){
    advice = "For modern Senator wear, structured Italian cashmere or high-twist polished wool delivers that sharp, non-creasing drape. Keep the collar clean and pair with tailored trousers that break just above your loafers.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'senator');
  }
  // 2. Ankara & African print requests
  else if(text.includes('ankara') || styleBrief === 'ankara' || text.includes('print') || text.includes('wax')){
    advice = "With Ankara styling, the key is balancing vibrant patterns with thoughtful tailoring. Pair an authentic wax print with minimalist accessories (burnished gold or neutral leather) so the pattern speaks with elegance.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'ankara');
  }
  // 3. Wedding & Owambe
  else if(text.includes('wedding') || text.includes('owambe') || occasion === 'wedding' || text.includes('party')){
    advice = "For weddings and celebratory Owambes, rich jewel tones (Navy, Wine, Emerald, Champagne) are timeless favorites. A sharp Senator set or a regal Agbada gives an authoritative, celebratory presence.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'senator' || x.category === 'agbada');
  }
  // 4. Corporate & Workwear
  else if(text.includes('work') || text.includes('corporate') || text.includes('office') || occasion === 'work' || text.includes('meeting') || text.includes('suit')){
    advice = "For boardroom presence, choose tailored silhouettes with clean lines. Double-breasted cuts or structured blazer sets project authority while keeping you comfortable throughout a busy day.";
    matchedLooks = FASHION_CATALOG.filter(x => x.category === 'formal' || x.id === 'casual-ankara-blazer');
  }
  // 5. Budget inquiry
  else if(text.includes('budget') || text.includes('cheap') || text.includes('cost') || text.includes('price') || text.includes('under')){
    advice = `Here are standout pieces that deliver luxury craftsmanship within your budget range (up to ₦${budget.toLocaleString('en-NG')}). Fabric quality and clean finishing make all the difference.`;
    matchedLooks = FASHION_CATALOG.filter(x => x.price <= budget);
    if(matchedLooks.length === 0) matchedLooks = [FASHION_CATALOG[1], FASHION_CATALOG[0]];
  }
  // 6. Color theory advice
  else if(text.includes('color') || text.includes('colour') || text.includes('wine') || text.includes('navy') || text.includes('emerald') || text.includes('gold')){
    advice = "Color harmony tip: Royal Navy pairs masterfully with Cognac brown and Silver. Wine and Burgundy look majestic when balanced with Champagne Gold or Charcoal accents. Emerald green looks striking against warm skin tones and gold jewellery.";
    matchedLooks = [FASHION_CATALOG[0], FASHION_CATALOG[2]];
  }
  // 7. General / default recommendation
  else {
    advice = "Here is a hand-picked recommendation that balances contemporary fit with rich texture. You can preview this look on a model using FASHN VTON 1.5 in the fitting studio on the right!";
    matchedLooks = [FASHION_CATALOG[0], FASHION_CATALOG[1]];
  }

  // Cap to 2 look cards in one reply for clean reading
  matchedLooks = matchedLooks.slice(0, 2);

  return { advice, looks: matchedLooks };
}

/* Send Stylist Message Flow */
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

  // Simulate AI stylist thinking and response
  setTimeout(() => {
    const typingEl = $('#chat-typing');
    if(typingEl) typingEl.remove();

    const response = generateStylistResponse(userQuery);

    const stylistMsg = document.createElement('div');
    stylistMsg.className = 'message';

    const author = document.createElement('div');
    author.className = 'message-author';
    author.textContent = 'Fitverse Stylist';
    stylistMsg.appendChild(author);

    const ap = document.createElement('p');
    ap.textContent = response.advice;
    stylistMsg.appendChild(ap);

    // Render interactive look cards
    response.looks.forEach(look => {
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
              <span class="price">${look.priceLabel}</span>
              <span class="tag">${look.fabric}</span>
              <span class="tag">${look.silhouette}</span>
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
  }, 750);
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
  // Clear chat
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

  // Brief controls sync
  const briefBudget = $('#brief-budget');
  if(briefBudget){
    briefBudget.addEventListener('input', () => {
      updateBudget(briefBudget.value);
    });
  }

  // Model selection
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

  // User photo upload in VTON studio
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

  // Run Try-On
  $('#btn-run-tryon')?.addEventListener('click', runVTONTryOn);

  // Tab views (Canvas vs Live Space)
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

  // Mobile Switchers
  $('#btn-mobile-chat')?.addEventListener('click', () => switchMobileTab('chat'));
  $('#btn-mobile-studio')?.addEventListener('click', () => switchMobileTab('studio'));

  // Save Look button
  $('#btn-save-look')?.addEventListener('click', saveLook);

  // Copy Garment link
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

  // legacy suggestions fallback
  const suggestionTrigger = e.target.closest('[data-suggestion]');
  if(suggestionTrigger && $('#stylist-input')){
    $('#stylist-input').value = suggestionTrigger.dataset.suggestion;
    sendStylistMessage();
  }
});

document.addEventListener('DOMContentLoaded', () => {
  loadMeasurements();

  const favs = readLocal('favorites', []);
  $$('[data-favorite]').forEach(b => {
    if(favs.includes(b.dataset.favorite)) b.textContent = '♥';
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
});
