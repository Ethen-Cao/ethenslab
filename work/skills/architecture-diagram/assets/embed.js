/* Shared article host for same-origin architecture diagram iframes. */
(() => {
  'use strict';

  const installation = Symbol.for('architecture-diagram.embed');
  if (window[installation]) return;
  window[installation] = true;

  const selector = 'iframe[data-architecture-diagram][src]';
  const maximumContentHeight = 12000;
  const frames = new WeakMap();

  function describe(frame) {
    const id = frame.getAttribute('data-architecture-diagram')?.trim();
    const source = frame.getAttribute('src')?.trim();
    if (!id || !source || !frame.isConnected) return null;
    try {
      const url = new URL(source, document.baseURI);
      if (url.origin === 'null' || url.origin !== window.location.origin) return null;
      return {id, url};
    } catch {
      return null;
    }
  }

  function requestHeight(frame) {
    const info = describe(frame);
    if (!info || !frame.contentWindow) return;
    frame.contentWindow.postMessage({type: `${info.id}-request-height`}, info.url.origin);
  }

  function applyHeight(frame, contentHeight) {
    // Messages contain the child document height, not the iframe's outer border box.
    frame.style.boxSizing = 'border-box';
    const style = getComputedStyle(frame);
    const extra = ['borderTopWidth', 'borderBottomWidth', 'paddingTop', 'paddingBottom']
      .reduce((sum, property) => sum + (parseFloat(style[property]) || 0), 0);
    const height = `${Math.ceil(contentHeight + extra)}px`;
    if (frame.style.height !== height) frame.style.height = height;
  }

  window.addEventListener('message', event => {
    if (!event.source) return;
    const data = event.data;
    if (!data || typeof data !== 'object' || Array.isArray(data)
        || typeof data.type !== 'string' || typeof data.height !== 'number'
        || !Number.isFinite(data.height) || data.height <= 0
        || data.height > maximumContentHeight) return;

    for (const frame of document.querySelectorAll(selector)) {
      if (event.source !== frame.contentWindow) continue;
      const info = describe(frame);
      if (info && event.origin === info.url.origin && data.type === `${info.id}-height`) {
        applyHeight(frame, data.height);
      }
      return;
    }
  });

  function connectFrames() {
    for (const frame of document.querySelectorAll(selector)) {
      const info = describe(frame);
      if (!info) continue;
      const signature = `${info.id}\n${info.url.href}`;
      if (frames.get(frame) === signature) continue;
      if (!frames.has(frame)) frame.addEventListener('load', () => requestHeight(frame));
      frames.set(frame, signature);
      // Also covers a deferred host script loaded after the child's initial report.
      requestHeight(frame);
    }
  }

  function start() {
    connectFrames();
    // Support lazy article components without observing our own height/style writes.
    new MutationObserver(connectFrames).observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['src', 'data-architecture-diagram']
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, {once: true});
  } else {
    start();
  }
})();
