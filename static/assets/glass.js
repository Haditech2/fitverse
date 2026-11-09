/*
 * Fitverse liquid-glass adapter.
 * Uses @real-human/liquid-glass for a small number of navigation and overlay
 * surfaces. The UI remains fully usable when backdrop filters are unavailable.
 */
(function () {
  'use strict';

  const GLASS_SELECTOR = '[data-glass]';
  const GLASS_TONES = {
    cream: {
      base: 'rgba(245, 243, 236, 0.18)',
      hover: 'rgba(255, 254, 248, 0.32)'
    },
    brand: {
      base: 'rgba(8, 106, 46, 0.11)',
      hover: 'rgba(8, 106, 46, 0.24)'
    },
    gold: {
      base: 'rgba(203, 155, 20, 0.13)',
      hover: 'rgba(238, 201, 92, 0.28)'
    },
    dark: {
      base: 'rgba(4, 70, 37, 0.20)',
      hover: 'rgba(3, 47, 27, 0.34)'
    },
    sage: {
      base: 'rgba(64, 105, 68, 0.12)',
      hover: 'rgba(64, 105, 68, 0.24)'
    }
  };

  function numberAttribute(element, name, fallback) {
    const value = Number(element.dataset[name]);
    return Number.isFinite(value) ? value : fallback;
  }

  function enhanceGlassSurface(surface) {
    if (surface.dataset.glassReady === 'true') return;

    const GlassElement = customElements.get('glass-element');
    if (!GlassElement || !window.ResizeObserver) return;

    // The layer is absolutely positioned inside the surface, so a static
    // surface would let it escape to the initial containing block and smear
    // a translucent band over unrelated content. Glass surfaces that
    // already have a meaningful position (sticky header, fixed dock,
    // absolute notes) are left untouched.
    if (getComputedStyle(surface).position === 'static') {
      surface.classList.add('glass-contained');
    }

    const tone = GLASS_TONES[surface.dataset.glassTone] || GLASS_TONES.cream;
    const baseColor = surface.dataset.glassColor || tone.base;
    const hoverColor = surface.dataset.glassHoverColor || tone.hover;

    const layer = document.createElement('glass-element');
    layer.className = 'liquid-glass-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.setAttribute('radius', String(numberAttribute(surface, 'glassRadius', 18)));
    layer.setAttribute('depth', String(numberAttribute(surface, 'glassDepth', 8)));
    layer.setAttribute('blur', String(numberAttribute(surface, 'glassBlur', 10)));
    layer.setAttribute('strength', String(numberAttribute(surface, 'glassStrength', 35)));
    layer.setAttribute('chromatic-aberration', String(numberAttribute(surface, 'glassChromatic', 1)));
    layer.setAttribute('background-color', baseColor);

    surface.classList.add('has-liquid-glass');
    surface.prepend(layer);
    surface.dataset.glassReady = 'true';

    const syncSize = () => {
      const rect = surface.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      layer.setAttribute('width', String(Math.ceil(rect.width)));
      layer.setAttribute('height', String(Math.ceil(rect.height)));
    };

    const observer = new ResizeObserver(syncSize);
    observer.observe(surface);
    syncSize();

    if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
      surface.addEventListener('pointerenter', () => {
        layer.setAttribute('background-color', hoverColor);
        surface.classList.add('is-glass-hovered');
      });
      surface.addEventListener('pointerleave', () => {
        layer.setAttribute('background-color', baseColor);
        surface.classList.remove('is-glass-hovered');
      });
    }
  }

  function initLiquidGlass() {
    const supportsBackdrop = window.CSS && (
      CSS.supports('backdrop-filter', 'blur(2px)') ||
      CSS.supports('-webkit-backdrop-filter', 'blur(2px)')
    );

    if (!supportsBackdrop || !window.customElements) {
      document.documentElement.classList.add('glass-fallback');
      return;
    }

    document.querySelectorAll(GLASS_SELECTOR).forEach(enhanceGlassSurface);
    document.documentElement.classList.add('glass-ready');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLiquidGlass, { once: true });
  } else {
    initLiquidGlass();
  }
})();
