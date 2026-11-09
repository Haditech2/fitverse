/*
 * Fitverse motion direction powered by @charmingdc/scrolljs.
 * Motion is intentionally limited to a few complete compositions instead of
 * animating every card. No feature depends on these transitions.
 */
(function () {
  'use strict';

  const MOMENT_GROUPS = [
    '.hero-copy',
    '.hero-visual',
    '.cta',
    '.dashboard-hero',
    '.detail-gallery',
    '.tryon-redesign-art',
    '.bodygram-panel',
    '.measurement-layout',
    '.split-studio',
    '.auth-visual',
    '.auth-form'
  ];

  const SEQUENCE_GROUPS = [
    ['.trust-strip', '.trust-item'],
    ['.collection-grid', '.collection-card'],
    ['.feature-list', '.feature-row'],
    ['.how-grid', '.how-step'],
    ['.quick-grid', '.quick-link'],
    ['.product-grid', '.product-card']
  ];

  const COLOR_MOMENTS = [
    '.trust-strip',
    '.collection-grid',
    '.feature-band',
    '.how-grid',
    '.cta',
    '.dashboard-hero',
    '.quick-grid',
    '.product-grid'
  ];

  function setupHeroMotion() {
    const video = document.querySelector('[data-hero-motion]');
    const toggle = document.querySelector('[data-hero-motion-toggle]');
    const label = toggle?.querySelector('[data-motion-label]');
    if(!video || !toggle) return;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const syncControl = () => {
      const paused = video.paused;
      if(label) label.textContent = paused ? 'Play' : 'Pause';
      toggle.setAttribute('aria-label', paused ? 'Play logo motion' : 'Pause logo motion');
    };

    if(reduceMotion){
      video.pause();
      video.currentTime = 0;
      syncControl();
    } else {
      video.play().then(syncControl).catch(syncControl);
    }

    toggle.addEventListener('click', () => {
      if(video.paused) video.play().catch(() => {});
      else video.pause();
      syncControl();
    });
    video.addEventListener('play', syncControl);
    video.addEventListener('pause', syncControl);
  }

  function setupMobileDock() {
    const dock = document.querySelector('.mobile-bottom');
    if(!dock) return;

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(reduced) return;

    let lastY = -1;
    let tipFrame = null;

    const hide = () => dock.classList.add('dock-hidden');
    const show = () => dock.classList.remove('dock-hidden');

    const tip = () => {
      if(tipFrame) return;
      tipFrame = window.requestAnimationFrame(() => {
        tipFrame = null;
        const y = window.scrollY;
        const max = (document.documentElement.scrollHeight - window.innerHeight) * 0.92;
        // At the very top the dock always returns so landing pages feel alive.
        if(y <= 120) show();
        // Within the last stretch (or at absolute bottom) it must never
        // hover over content: park it out of the way unless the reader
        // pulls upward again.
        else if(y >= max && y > lastY) hide();
        else if(y > lastY + 4) hide();
        else if(y < lastY - 4) show();
        lastY = y;
      });
    };

    window.addEventListener('scroll', tip, { passive: true });
    tip();
  }

  function initScrollMoments() {
    setupMobileDock();
    setupHeroMotion();
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion || !window.IntersectionObserver || typeof window.ScrollObserver !== 'function') {
      document.documentElement.classList.add('motion-reduced');
      return;
    }

    const elements = [...new Set(
      MOMENT_GROUPS.flatMap(selector => [...document.querySelectorAll(selector)])
    )];

    if(elements.length){
      elements.forEach((element, index) => {
        element.classList.add('fitverse-scroll-moment');
        element.style.setProperty('--reveal-order', String(index % 3));
      });

      const observer = new window.ScrollObserver(true, {
        root: null,
        threshold: 0.12,
        rootMargin: '0px 0px -7% 0px'
      });

      observer.observe(elements, null, 'fitverse-in-view');
    }

    document.documentElement.classList.add('scrolljs-ready');

    const sequenceItems = [];
    SEQUENCE_GROUPS.forEach(([groupSelector, itemSelector]) => {
      document.querySelectorAll(groupSelector).forEach(group => {
        group.querySelectorAll(itemSelector).forEach((item, index) => {
          item.classList.add('fitverse-scroll-item');
          item.style.setProperty('--item-order', String(Math.min(index, 5)));
          sequenceItems.push(item);
        });
      });
    });

    if(sequenceItems.length){
      const itemObserver = new window.ScrollObserver(true, {
        root: null,
        threshold: 0.08,
        rootMargin: '0px 0px -5% 0px'
      });
      itemObserver.observe(sequenceItems, null, 'fitverse-item-in-view');
    }

    const colorMoments = [...new Set(
      COLOR_MOMENTS.flatMap(selector => [...document.querySelectorAll(selector)])
    )];
    colorMoments.forEach(element => element.classList.add('fitverse-color-moment'));
    if(colorMoments.length){
      const colorObserver = new window.ScrollObserver(true, {
        root: null,
        threshold: 0.16,
        rootMargin: '0px 0px -12% 0px'
      });
      colorObserver.observe(colorMoments, null, 'fitverse-color-active');
    }

  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScrollMoments, { once: true });
  } else {
    initScrollMoments();
  }
})();
