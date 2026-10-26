#!/usr/bin/env node
/* Offline browser QA of a real same-origin article and its diagram iframes. */
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, dirname, join, basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';

export const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const fixtureOrigin = 'https://architecture.test';
const require = createRequire(import.meta.url);
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('"', '&quot;')
  .replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export async function launchBrowser(executablePath) {
  let playwright;
  try { playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright'); }
  catch { throw new Error('Playwright is unavailable. Set PLAYWRIGHT_MODULE to an existing installation; do not install dependencies just for QA.'); }
  return playwright.chromium.launch({headless: true, chromiumSandbox: true,
    ...(executablePath ? {executablePath} : {})});
}

export function modelFromHTML(html) {
  const source = html.match(/<script\b[^>]*\bid="diagram-model"[^>]*>([\s\S]*?)<\/script>/i)?.[1];
  if (!source) throw new Error('Input must be a generated architecture diagram with a diagram-model script.');
  return JSON.parse(source);
}

export async function openArticle(browser, {diagrams, width = 1200, height = 900,
  helper = true, initialHeight = 160} = {}) {
  // width is the requested iframe border-box width; 48px is fixed article padding.
  const context = await browser.newContext({viewport: {width: width + 48, height}, deviceScaleFactor: 1});
  const page = await context.newPage();
  const pageErrors = [], externalRequests = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  const embed = await readFile(join(skillRoot, 'assets/embed.js'), 'utf8');
  const checker = await readFile(join(skillRoot, 'scripts/check-diagram.js'), 'utf8');
  const children = diagrams.map(html => ({html, model: modelFromHTML(html)}));
  const host = `<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Article diagram QA</title>
<style>*{box-sizing:border-box}body{margin:0;padding:24px;font:18px/1.5 sans-serif}
main{max-width:${width}px;margin:auto}figure{margin:24px 0}iframe{display:block;width:100%;height:${initialHeight}px;border:3px solid #aaa;border-bottom-width:5px}
p{overflow-wrap:anywhere}a{color:#356dc9}</style></head><body><main><h1>Architecture article</h1>
<p>This article fixture preserves the requested viewport and normal page scrolling.</p>
${children.map(({model}, index) => `<figure><iframe src="../diagrams/${index}.html" data-architecture-diagram="${escape(model.meta.id)}" title="${escape(model.meta.title)}"></iframe><figcaption><a href="../diagrams/${index}.html">Open diagram</a></figcaption></figure>`).join('\n')}
<p id="after-diagrams">Article content after the diagrams.</p></main>
${helper ? '<script src="../assets/embed.js"></script>' : ''}</body></html>`;
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    let body, contentType = 'text/html; charset=utf-8';
    if (url.origin === fixtureOrigin && url.pathname === '/article/') body = host;
    else if (url.origin === fixtureOrigin && url.pathname === '/assets/embed.js') {
      body = embed; contentType = 'text/javascript; charset=utf-8';
    } else if (url.origin === fixtureOrigin && /^\/diagrams\/\d+\.html$/.test(url.pathname)) {
      body = children[Number(url.pathname.match(/\d+/)[0])]?.html;
    }
    if (body === undefined) { externalRequests.push(url.href); return route.abort(); }
    return route.fulfill({status: 200, contentType, body});
  });
  try {
    await page.goto(`${fixtureOrigin}/article/`, {waitUntil: 'load'});
    const frames = [];
    for (let index = 0; index < children.length; index++) {
      const frame = await (await page.locator('iframe').nth(index).elementHandle()).contentFrame();
      await frame.evaluate(async () => {
        if (!window.architectureReady) throw new Error('Missing architectureReady.');
        const result = await window.architectureReady;
        if (!result?.ok) throw new Error(result?.error || 'Diagram rendering failed.');
        await document.fonts.ready;
      });
      await frame.addScriptTag({content: checker});
      frames.push(frame);
    }
    const session = {context, page, frames, children, pageErrors, externalRequests};
    await settleArticle(session, {expectFit: helper});
    return session;
  } catch (error) { await context.close(); throw error; }
}

// Evaluate in the parent page: child coordinates alone cannot detect a scaled host.
export function articleMetrics() {
  const host = document.documentElement;
  const frames = [...document.querySelectorAll('iframe[data-architecture-diagram]')].map(frame => {
    const child = frame.contentWindow, doc = frame.contentDocument;
    const root = doc?.querySelector('.architecture-document');
    if (!child || !root) return {id: frame.dataset.architectureDiagram, ready: false};
    const style = getComputedStyle(frame), rect = frame.getBoundingClientRect();
    const extra = ['borderTopWidth', 'borderBottomWidth', 'paddingTop', 'paddingBottom']
      .reduce((sum, key) => sum + (parseFloat(style[key]) || 0), 0);
    const contentHeight = Math.ceil(root.getBoundingClientRect().bottom + child.scrollY
      + (parseFloat(child.getComputedStyle(doc.body).paddingBottom) || 0));
    const shell = doc.querySelector('.diagram-shell');
    return {id: frame.dataset.architectureDiagram, ready: true,
      width: rect.width, contentWidth: child.innerWidth, height: rect.height, contentHeight, expectedHeight: Math.ceil(contentHeight + extra),
      viewportHeight: doc.documentElement.clientHeight,
      scrollHeight: Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight),
      horizontalOverflow: Math.max(doc.documentElement.scrollWidth - doc.documentElement.clientWidth,
        shell ? shell.scrollWidth - shell.clientWidth : 0, 0),
      hostScaleX: rect.width / frame.offsetWidth, hostScaleY: rect.height / frame.offsetHeight,
      hostTransformed: Math.abs(rect.width - frame.offsetWidth) > 1.25
        || Math.abs(rect.height - frame.offsetHeight) > 1.25};
  });
  return {viewport: {width: innerWidth, height: innerHeight},
    horizontalOverflow: Math.max(0, host.scrollWidth - host.clientWidth), frames};
}

export async function settleArticle(session, {expectFit = true} = {}) {
  // Let resize observers, postMessage and layout settle without arbitrary long sleeps.
  await session.page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  if (expectFit) {
    await session.page.waitForFunction(`(() => {
      const value = (${articleMetrics.toString()})();
      return value.frames.length && value.frames.every(f => f.ready
        && Math.abs(f.height - f.expectedHeight) <= 2
        && f.scrollHeight <= f.viewportHeight + 1);
    })()`, undefined, {timeout: 3000}).catch(() => {});
  }
}

export async function injectHelper(session) {
  await session.page.addScriptTag({url: `${fixtureOrigin}/assets/embed.js`});
  await settleArticle(session);
}

export async function auditArticle(session) {
  const metrics = await session.page.evaluate(articleMetrics);
  const diagrams = await Promise.all(session.frames.map(frame => frame.evaluate(() => ({
    ...checkDiagram({quiet: true}), mode: window.ArchitecturePresentation?.mode,
    renderError: window.architectureRenderError || null
  }))));
  const errors = [], warnings = [];
  const error = (code, message, frame) => errors.push({code, message, ...(frame === undefined ? {} : {frame})});
  if (metrics.horizontalOverflow > 1) error('host-horizontal-overflow', 'The article overflows its actual viewport.');
  metrics.frames.forEach((frame, index) => {
    if (!frame.ready) return error('frame-not-ready', 'The child document did not render.', index);
    if (frame.hostTransformed) error('host-scale', 'Scaling the iframe or its ancestors is unsupported: child font metrics would be misleading.', index);
    if (frame.horizontalOverflow > 1) error('frame-horizontal-overflow', 'The embedded diagram needs horizontal scrolling.', index);
    if (frame.scrollHeight > frame.viewportHeight + 1 || frame.contentHeight > frame.viewportHeight + 1) {
      error('frame-vertical-clipping', 'The iframe is shorter than its child document.', index);
    }
    if (Math.abs(frame.height - frame.expectedHeight) > 2) error('frame-height-mismatch', 'The iframe did not adopt the measured content height and actual borders.', index);
    const diagram = diagrams[index];
    if (diagram.mode !== 'article') error('not-article-mode', 'An article fixture must embed an article-mode artifact.', index);
    for (const issue of diagram.errors) errors.push({...issue, frame: index});
    for (const issue of diagram.warnings) warnings.push({...issue, frame: index});
    if (diagram.renderError) error('render-error', diagram.renderError, index);
  });
  for (const message of session.pageErrors) error('page-error', message);
  for (const url of session.externalRequests) error('external-request', url);
  return {ok: !errors.length && !warnings.length, errors, warnings, metrics, diagrams};
}

export async function saveArticleScreenshots(session, output, name) {
  await mkdir(output, {recursive: true});
  await session.page.screenshot({path: join(output, `${name}-viewport.png`), fullPage: false});
  await session.page.screenshot({path: join(output, `${name}-full.png`), fullPage: true});
}

async function main() {
  const args = process.argv.slice(2), options = {};
  for (let index = 0; index < args.length; index += 2) {
    if (!['--input', '--output', '--widths', '--browser'].includes(args[index]) || !args[index + 1]) {
      throw new Error('Usage: verify-article.mjs --input diagram.html --output /tmp/qa [--widths 1200,960] [--browser /path/to/chromium]');
    }
    options[args[index].slice(2)] = args[index + 1];
  }
  if (!options.input || !options.output) throw new Error('--input and --output are required.');
  const widths = (options.widths || '1200,960').split(',').map(Number);
  if (!widths.length || widths.some(width => !Number.isInteger(width) || width < 240 || width > 7680)) throw new Error('Widths must be integer CSS pixels from 240 to 7680.');
  const html = await readFile(resolve(options.input), 'utf8'), output = resolve(options.output);
  await mkdir(output, {recursive: true});
  const browser = await launchBrowser(options.browser), results = [];
  try {
    for (const width of widths) {
      const session = await openArticle(browser, {diagrams: [html], width});
      try {
        const result = await auditArticle(session);
        results.push({width, ...result});
        await saveArticleScreenshots(session, output, `${basename(options.input, '.html')}-${width}`);
        console.log(`${width}px iframe: ${result.errors.length} errors, ${result.warnings.length} warnings`);
      } finally { await session.context.close(); }
    }
    await writeFile(join(output, 'report.json'), JSON.stringify({input: resolve(options.input), results}, null, 2));
    if (results.some(result => !result.ok)) process.exitCode = 1;
  } finally { await browser.close(); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
