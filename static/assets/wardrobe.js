/* ================================================================
   FITVERSE / MY WARDROBE
   Upload personal clothing photos, tag them with AI, and build
   outfits from what the user already owns.
   ================================================================ */
(function () {
  'use strict';

  const MAX_BATCH = 6;
  const uploadState = { busy: false };
  let wardrobeLimit = 60;

  /* ---------------------------------------------------------------- utils */

  function $(selector, root) {
    return (root || document).querySelector(selector);
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function setStatus(target, message, tone) {
    const node = typeof target === 'string' ? document.getElementById(target) : target;
    if (!node) return;
    if (!message) {
      node.hidden = true;
      node.textContent = '';
      node.removeAttribute('data-tone');
      return;
    }
    node.hidden = false;
    node.textContent = message;
    node.dataset.tone = tone || '';
  }

  function notify(message) {
    if (typeof window.toast === 'function') window.toast(message);
  }

  async function readJson(response) {
    try {
      return await response.json();
    } catch (error) {
      return {};
    }
  }

  function errorMessage(payload, fallback) {
    if (payload && typeof payload.error === 'string' && payload.error) return payload.error;
    return fallback;
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.idleLabel = button.textContent;
      button.textContent = label || 'Working…';
      button.disabled = true;
    } else {
      button.textContent = button.dataset.idleLabel || button.textContent;
      button.disabled = false;
      delete button.dataset.idleLabel;
    }
  }

  /* ---------------------------------------------------------------- cards */

  function wearLabel(count) {
    return 'Worn ' + count + '\u00d7';
  }

  function wardrobeCard(item) {
    const card = el('article', 'wardrobe-item');
    card.dataset.itemId = item.id;

    const media = el('div', 'wardrobe-item-media');
    const img = el('img');
    img.src = item.thumb_url;
    img.alt = item.name || 'Wardrobe item';
    img.loading = 'lazy';
    img.decoding = 'async';
    media.appendChild(img);

    const remove = el('button', 'wardrobe-item-delete', '\u00d7');
    remove.type = 'button';
    remove.setAttribute('aria-label', 'Remove ' + (item.name || 'this piece'));
    remove.addEventListener('click', function () {
      wardrobeDelete(item.id);
    });
    media.appendChild(remove);

    const worn = el('span', 'wardrobe-item-worn', wearLabel(item.wear_count || 0));
    if (!item.wear_count) worn.hidden = true;
    media.appendChild(worn);
    card.appendChild(media);

    const body = el('div', 'wardrobe-item-body');
    body.appendChild(el('strong', 'wardrobe-item-name', item.name || 'Untitled piece'));

    const meta = el('div', 'wardrobe-item-meta');
    meta.appendChild(el('span', 'tag', item.category_label || 'Other'));
    (item.colours || []).forEach(function (colour) {
      meta.appendChild(el('span', 'wardrobe-colour', colour));
    });
    body.appendChild(meta);

    if (item.formality) {
      body.appendChild(el('span', 'wardrobe-formality', item.formality));
    }

    if (!item.tagged) {
      const retag = el('button', 'text-button wardrobe-retag', 'Tag with AI');
      retag.type = 'button';
      retag.addEventListener('click', function () {
        wardrobeTag(item.id, retag);
      });
      body.appendChild(retag);
    }

    card.appendChild(body);
    return card;
  }

  function replaceCard(item) {
    const grid = document.getElementById('wardrobe-grid');
    if (!grid) return;
    const existing = grid.querySelector('[data-item-id="' + item.id + '"]');
    const next = wardrobeCard(item);
    next.classList.add('is-updated');
    if (existing) {
      grid.replaceChild(next, existing);
    } else {
      grid.appendChild(next);
    }
    void next.offsetWidth;
    next.classList.remove('is-updated');
    refreshEmptyState();
  }

  function refreshEmptyState() {
    const grid = document.getElementById('wardrobe-grid');
    const empty = document.getElementById('wardrobe-empty');
    if (!grid) return;
    const count = grid.querySelectorAll('.wardrobe-item').length;
    grid.classList.toggle('is-empty', count === 0);
    if (empty) empty.hidden = count > 0;
    const counter = document.getElementById('wardrobe-count');
    if (counter) counter.textContent = count + ' of ' + wardrobeLimit + ' pieces';
    updateTabCount(count);
  }

  function updateTabCount(count) {
    const tab = document.querySelector('.wardrobe-tabs button');
    if (tab) tab.textContent = 'My clothes (' + count + ')';
  }

  /* --------------------------------------------------------------- upload */

  async function uploadPhotos(files) {
    if (!files || !files.length) return;
    if (uploadState.busy) {
      notify('Hold on — your last upload is still finishing.');
      return;
    }

    const list = Array.prototype.slice.call(files);
    uploadState.busy = true;
    setStatus('wardrobe-upload-status', 'Preparing ' + list.length + ' photo' + (list.length > 1 ? 's' : '') + '…');

    const uploaded = [];
    const problems = [];
    try {
      for (let start = 0; start < list.length; start += MAX_BATCH) {
        const batch = list.slice(start, start + MAX_BATCH);
        const form = new FormData();
        batch.forEach(function (file) {
          form.append('photos', file);
        });

        setStatus(
          'wardrobe-upload-status',
          'Uploading ' + Math.min(start + batch.length, list.length) + ' of ' + list.length + '…'
        );

        let response;
        try {
          response = await fetch('/api/wardrobe/upload/', { method: 'POST', body: form });
        } catch (error) {
          problems.push('Could not reach Fitverse. Check your connection and try again.');
          break;
        }

        const payload = await readJson(response);
        if (!response.ok) {
          problems.push(errorMessage(payload, 'Those photos could not be added.'));
          continue;
        }

        (payload.items || []).forEach(function (item) {
          uploaded.push(item);
          const grid = document.getElementById('wardrobe-grid');
          if (grid) grid.appendChild(wardrobeCard(item));
        });
        (payload.errors || []).forEach(function (message) {
          problems.push(message);
        });
        refreshEmptyState();
      }
    } finally {
      uploadState.busy = false;
    }

    if (!uploaded.length) {
      setStatus('wardrobe-upload-status', problems[0] || 'No photos were added. Try again.', 'error');
      return;
    }

    if (problems.length) {
      setStatus('wardrobe-upload-status', problems[0], 'error');
    } else {
      setStatus(
        'wardrobe-upload-status',
        'Added ' + uploaded.length + ' piece' + (uploaded.length > 1 ? 's' : '') + '. Reading them with AI…',
        'ok'
      );
    }
    notify(uploaded.length + ' piece' + (uploaded.length > 1 ? 's' : '') + ' added to your wardrobe');

    // Tag one at a time so a slow AI call never floods the endpoint.
    let tagFailures = 0;
    for (let index = 0; index < uploaded.length; index += 1) {
      const item = uploaded[index];
      setStatus(
        'wardrobe-upload-status',
        'Reading photo ' + (index + 1) + ' of ' + uploaded.length + ' with AI…'
      );
      const result = await tagItem(item.id);
      if (result && result.item) {
        uploaded[index] = result.item;
        replaceCard(result.item);
      } else {
        tagFailures += 1;
      }
    }

    if (tagFailures) {
      setStatus(
        'wardrobe-upload-status',
        'Your pieces are saved, but ' + tagFailures + ' could not be read by the AI. Tap “Tag with AI” on ' +
          (tagFailures > 1 ? 'those cards' : 'that card') + ' to try again.',
        ''
      );
      notify('Some pieces still need tagging');
      return;
    }

    setStatus(
      'wardrobe-upload-status',
      'Your wardrobe is ready. Ask the stylist what to wear.',
      'ok'
    );
    notify('Wardrobe tagged — ask the stylist what to wear');
  }

  function wardrobeUpload(files) {
    return uploadPhotos(files);
  }

  /* ----------------------------------------------------------------- tags */

  async function tagItem(itemId) {
    let response;
    try {
      response = await fetch('/api/wardrobe/items/' + itemId + '/tag/', { method: 'POST' });
    } catch (error) {
      return { error: 'Could not reach Fitverse. Try tagging again.' };
    }
    const payload = await readJson(response);
    if (!response.ok) {
      return { error: errorMessage(payload, 'The AI could not tag this piece.'), fallback: payload.fallback };
    }
    return payload;
  }

  async function tagWardrobeItem(itemId, button) {
    setBusy(button, true, 'Reading…');
    const result = await tagItem(itemId);
    if (result.item) {
      replaceCard(result.item);
      return;
    }
    setBusy(button, false);
    setStatus(
      'wardrobe-upload-status',
      result.error || 'The AI could not tag this piece. You can try again.',
      'error'
    );
    if (result.fallback) notify('AI tagging is unavailable — your piece is saved');
  }

  function wardrobeTag(itemId) {
    const grid = document.getElementById('wardrobe-grid');
    const button = grid ? grid.querySelector('[data-item-id="' + itemId + '"] .wardrobe-retag') : null;
    return tagWardrobeItem(itemId, button);
  }

  /* --------------------------------------------------------------- delete */

  async function deleteItem(itemId) {
    let response;
    try {
      response = await fetch('/api/wardrobe/items/' + itemId + '/delete/', { method: 'POST' });
    } catch (error) {
      setStatus('wardrobe-upload-status', 'Could not reach Fitverse. Try removing the piece again.', 'error');
      return;
    }
    if (!response.ok) {
      const payload = await readJson(response);
      setStatus(
        'wardrobe-upload-status',
        errorMessage(payload, 'That piece could not be removed.'),
        'error'
      );
      return;
    }
    const grid = document.getElementById('wardrobe-grid');
    const card = grid ? grid.querySelector('[data-item-id="' + itemId + '"]') : null;
    if (card) card.remove();
    refreshEmptyState();
    setStatus('wardrobe-upload-status', 'Piece removed from your wardrobe.', 'ok');
  }

  function wardrobeDelete(itemId) {
    if (!window.confirm('Remove this piece from your wardrobe?')) return;
    return deleteItem(itemId);
  }

  /* ---------------------------------------------------------------- worn */

  async function markWorn(itemIds, button) {
    setBusy(button, true, 'Saving…');
    let response;
    try {
      response = await fetch('/api/wardrobe/worn/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: itemIds }),
      });
    } catch (error) {
      setBusy(button, false);
      setStatus('wardrobe-status', 'Could not reach Fitverse. Try again in a moment.', 'error');
      return;
    }
    const payload = await readJson(response);
    if (!response.ok) {
      setBusy(button, false);
      setStatus('wardrobe-status', errorMessage(payload, 'Could not save this wear.'), 'error');
      return;
    }

    if (button) {
      button.textContent = 'Wear logged \u2713';
      button.disabled = true;
      delete button.dataset.idleLabel;
    }

    // Bump the wear badges on the closet cards without refetching the page.
    const grid = document.getElementById('wardrobe-grid');
    if (grid) {
      itemIds.forEach(function (itemId) {
        const badge = grid.querySelector('[data-item-id="' + itemId + '"] .wardrobe-item-worn');
        if (!badge) return;
        const match = /(\d+)/.exec(badge.textContent || '');
        const next = (match ? parseInt(match[1], 10) : 0) + 1;
        badge.textContent = wearLabel(next);
        badge.hidden = false;
      });
    }
    setStatus('wardrobe-status', 'Wear logged. Your stylist will remember it.', 'ok');
    notify('Wear logged');
  }

  /* ----------------------------------------------------------- recommend */

  function outfitCard(outfit, index) {
    const card = el('article', 'outfit-card');

    const pieces = el('div', 'outfit-pieces');
    (outfit.items || []).forEach(function (item) {
      const figure = el('figure', 'outfit-piece');
      const img = el('img');
      img.src = item.thumb_url;
      img.alt = item.name || 'Wardrobe piece';
      img.loading = 'lazy';
      img.decoding = 'async';
      figure.appendChild(img);
      figure.appendChild(el('figcaption', '', item.name || 'Untitled piece'));
      pieces.appendChild(figure);
    });
    card.appendChild(pieces);

    const copy = el('div', 'outfit-copy');
    copy.appendChild(el('div', 'eyebrow', 'Outfit ' + (index + 1)));
    copy.appendChild(el('h4', '', outfit.title || 'Outfit idea'));
    if (outfit.why) copy.appendChild(el('p', 'outfit-why', outfit.why));
    if (outfit.tip) {
      const tip = el('p', 'outfit-tip');
      tip.appendChild(el('strong', '', 'Styling tip: '));
      tip.appendChild(document.createTextNode(outfit.tip));
      copy.appendChild(tip);
    }

    const ids = (outfit.items || []).map(function (item) {
      return item.id;
    });
    if (ids.length) {
      const worn = el('button', 'button secondary small', 'I wore this');
      worn.type = 'button';
      worn.addEventListener('click', function () {
        markWorn(ids, worn);
      });
      copy.appendChild(worn);
    }

    card.appendChild(copy);
    return card;
  }

  function renderOutfits(outfits) {
    const section = document.getElementById('wardrobe-results');
    const target = document.getElementById('wardrobe-outfits');
    const title = document.getElementById('wardrobe-results-title');
    if (!section || !target) return;

    target.textContent = '';
    outfits.forEach(function (outfit, index) {
      target.appendChild(outfitCard(outfit, index));
    });
    if (title) {
      title.textContent = outfits.length + ' outfit idea' + (outfits.length > 1 ? 's' : '');
    }
    section.hidden = false;
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function recommendOutfits() {
    const button = document.getElementById('wardrobe-recommend');
    const occasion = ($('#wardrobe-occasion') || {}).value || '';
    const weather = ($('#wardrobe-weather') || {}).value || '';
    const note = ($('#wardrobe-note') || {}).value || '';

    const grid = document.getElementById('wardrobe-grid');
    const pieces = grid ? grid.querySelectorAll('.wardrobe-item').length : 0;
    if (pieces < 2) {
      setStatus(
        'wardrobe-status',
        'Add at least two pieces — a top and a bottom, or a dress — so the stylist has something to work with.',
        'error'
      );
      return;
    }

    const shuffle = $('.wardrobe-results-head .button');
    setBusy(button, true, 'Styling…');
    if (shuffle) shuffle.disabled = true;
    setStatus('wardrobe-status', 'Reading your wardrobe and building outfits…');

    let response;
    try {
      response = await fetch('/api/wardrobe/recommend/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ occasion: occasion, weather: weather, note: note }),
      });
    } catch (error) {
      setBusy(button, false);
      if (shuffle) shuffle.disabled = false;
      setStatus('wardrobe-status', 'Could not reach Fitverse. Check your connection and try again.', 'error');
      return;
    }

    const payload = await readJson(response);
    setBusy(button, false);
    if (shuffle) shuffle.disabled = false;

    if (!response.ok || !payload.outfits || !payload.outfits.length) {
      setStatus(
        'wardrobe-status',
        errorMessage(payload, 'The stylist could not build an outfit right now. Try again.'),
        'error'
      );
      return;
    }

    setStatus('wardrobe-status', 'Styled from your own wardrobe.', 'ok');
    renderOutfits(payload.outfits);
  }

  function wardrobeRecommend() {
    return recommendOutfits();
  }

  /* ----------------------------------------------------------------- boot */

  function boot() {
    const counter = document.getElementById('wardrobe-count');
    if (counter) {
      const match = /of\s+(\d+)/.exec(counter.textContent || '');
      if (match) wardrobeLimit = parseInt(match[1], 10) || wardrobeLimit;
    }
    refreshEmptyState();
  }

  window.wardrobeUpload = wardrobeUpload;
  window.wardrobeTag = wardrobeTag;
  window.wardrobeDelete = wardrobeDelete;
  window.wardrobeRecommend = wardrobeRecommend;
  window.markWardrobeWorn = markWorn;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
