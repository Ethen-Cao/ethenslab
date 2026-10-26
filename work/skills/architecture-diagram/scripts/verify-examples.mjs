#!/usr/bin/env node
/* Isolated render QA: no user browser state, no external network requests. */
import assert from 'node:assert/strict';
import {readFile, readdir, mkdir, writeFile} from 'node:fs/promises';
import {resolve, dirname, join, basename} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {buildDiagram} from './build-diagram.mjs';
const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2), options = {};
for (let i = 0; i < args.length; i += 2) {
  if (!['--output', '--browser', '--input'].includes(args[i]) || !args[i + 1]) throw new Error('Usage: node scripts/verify-examples.mjs --output /tmp/qa [--browser /path/to/chromium] [--input diagram.html]');
  options[args[i].slice(2)] = args[i + 1];
}
if (!options.output) throw new Error('--output is required.');
const output = resolve(options.output);
await mkdir(output, {recursive: true});
let playwright;
try {playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright');}
catch {throw new Error('Playwright is unavailable. Use an existing installation via NODE_PATH or PLAYWRIGHT_MODULE; do not install dependencies just for this test.');}
const browser = await playwright.chromium.launch({headless: true, chromiumSandbox: true, ...(options.browser ? {executablePath: options.browser} : {})});
const results = [], negatives = [];
try {
  const page = await browser.newPage({viewport: {width: 1500, height: 1050}, deviceScaleFactor: 1});
  const externalRequests = [];
  await page.route('**/*', route => {externalRequests.push(route.request().url()); return route.abort();});
  const ready = () => page.evaluate(async () => {
    if (!window.architectureReady || typeof window.architectureReady.then !== 'function') throw new Error('The artifact must expose architectureReady for font-safe rendering.');
    await window.architectureReady;
    await document.fonts.ready;
  });
  const checker = await readFile(resolve(root, 'scripts/check-diagram.js'), 'utf8');
  const files = options.input ? [{name: basename(options.input).replace(/\.html$/, ''), path: resolve(options.input)}] :
    (await readdir(resolve(root, 'assets/architecture_diagrams'))).filter(f => f.endsWith('.html')).sort().map(f => ({name: f.replace(/\.html$/, ''), path: resolve(root, 'assets/architecture_diagrams', f)}));
  if (!options.input) files.push({name: 'base-template', path: resolve(root, 'assets/base-template.html')});
  // Purpose variants reuse one identical model/layout; no second hand-maintained template.
  const base = JSON.parse(await readFile(resolve(root, 'assets/base-model.json'), 'utf8'));
  for (const mode of options.input ? [] : ['origin', 'responsibility']) {
    const model = structuredClone(base); model.meta.id = `qa-${mode}`; model.meta.colorMode = mode;
    if (mode === 'origin') model.nodes.forEach(n => {n.origin = 'native';});
    else {
      model.meta.responsibilityBasis = 'integration';
      model.parties = [{id: 'a', label: 'Integrator A', category: 'tier1'}, {id: 'b', label: 'Integrator B', category: 'tier1', paletteKey: 'cyan'}];
      model.nodes.forEach((n, i) => {n.responsibleParty = i ? 'b' : 'a';});
    }
    const path = join(output, `${model.meta.id}.html`); await buildDiagram(model, path); files.push({name: model.meta.id, path});
  }
  for (const file of files) {
    const errors = [];
    const listener = e => errors.push(e.message); page.on('pageerror', listener);
    const requestStart = externalRequests.length;
    await page.setContent(await readFile(file.path, 'utf8'), {waitUntil: 'load'});
    await ready();
    await page.addScriptTag({content: checker});
    const result = await page.evaluate(() => ({...checkDiagram({quiet: true}), renderError: window.architectureRenderError || null}));
    result.name = file.name; result.pageErrors = errors;
    result.externalRequests = externalRequests.slice(requestStart);
    result.fonts = await page.evaluate(() => [...document.fonts].map(f => ({family: f.family, weight: f.weight, status: f.status})));
    result.controls = await page.locator('button,input,select,textarea').count();
    // Keep the declared viewport. Full-page evidence never implies a one-screen or embedded pass.
    await page.screenshot({path: join(output, `${file.name}-viewport.png`)});
    await page.screenshot({path: join(output, `${file.name}.png`), fullPage: true});
    // A narrow host must preserve the diagram's logical width rather than shrinking fonts.
    const wide = await page.locator('svg').first().boundingBox();
    await page.setViewportSize({width: 760, height: 900});
    const narrow = await page.locator('svg').first().boundingBox();
    result.naturalWidthPreserved = !!wide && !!narrow && Math.abs(wide.width - narrow.width) < 1;
    result.presentationBehavior = result.presentation.mode === 'original' ? result.naturalWidthPreserved : !!narrow && narrow.width <= 760 && narrow.width <= wide.width;
    await page.setViewportSize({width: 1500, height: 1050});
    results.push(result);
    console.log(`${file.name}: ${result.errors.length} errors, ${result.warnings.length} warnings; ${JSON.stringify(result.counts)}`);
    page.off('pageerror', listener);
  }
  const negative = async (name, mutate, input = 'assets/base-template.html', expectedCode) => {
    await page.setContent(await readFile(resolve(root, input), 'utf8'), {waitUntil: 'load'});
    await ready();
    await page.addScriptTag({content: checker});
    await page.evaluate(mutate);
    const result = await page.evaluate(() => checkDiagram({quiet: true}));
    negatives.push({name, rejected: !result.ok && (!expectedCode || result.errors.some(error => error.code === expectedCode)), ...(expectedCode ? {expectedCode} : {}), errors: result.errors});
  };
  if (!options.input) {
    await negative('missing-node', () => document.querySelector('[data-node]').remove());
    await negative('missing-edge', () => document.querySelector('[data-edge]').remove());
    await negative('missing-frame', () => document.querySelector('.container-frame').remove());
    await negative('mutated-visible-path', () => document.querySelector('path.edge').setAttribute('d', 'M 20 20 H 50'));
    await negative('empty-dom', () => document.querySelector('svg').remove());
    await negative('unknown-model', () => {window.architectureModel = undefined;});
    await negative('missing-theme', () => {window.ArchitectureTheme = undefined;});
    await negative('wrong-sans-family', () => document.querySelector('.node-name').style.fontFamily = 'Arial');
    await negative('wrong-monospace-family', () => document.querySelector('.node.library .node-name').style.fontFamily = 'Arial', 'assets/architecture_diagrams/process-library-subsystem.html');
    await negative('old-node-name-size', () => document.querySelector('.node-name').style.fontSize = '16px', undefined, 'node-font-size');
    await negative('old-node-subtitle-size', () => document.querySelector('.node-subtitle').style.fontSize = '12px', undefined, 'node-font-size');
    await negative('old-domain-title-size', () => document.querySelector('.container.domain > .container-title').style.fontSize = '20px', undefined, 'container-font-size');
    await negative('old-container-title-size', () => document.querySelector('.container.layer > .container-title').style.fontSize = '18px', undefined, 'container-font-size');
    await negative('old-container-subtitle-size', () => document.querySelector('.container-subtitle').style.fontSize = '12px', 'assets/architecture_diagrams/layout-primitives.html', 'container-font-size');
    await negative('old-edge-label-size', () => document.querySelector('.edge-label text').style.fontSize = '13px', undefined, 'label-font-size');
    await negative('old-figure-title-size', () => document.querySelector('#diagram-title').style.fontSize = '24px', undefined, 'diagram-title-size');
    await negative('old-figure-subtitle-size', () => document.querySelector('#diagram-subtitle').style.fontSize = '14px', 'assets/architecture_diagrams/layout-primitives.html', 'diagram-subtitle-size');
    await negative('old-legend-size', () => document.querySelector('.diagram-legend').style.fontSize = '12px', undefined, 'legend-font-size');
    await negative('missing-loaded-font', () => {
      // CSS-connected FontFace objects cannot be deleted from document.fonts;
      // remove their defining CSS rule to exercise a genuinely missing face.
      for (const sheet of document.styleSheets) for (let i = sheet.cssRules.length - 1; i >= 0; i--) {
        const rule = sheet.cssRules[i];
        if (rule.type === CSSRule.FONT_FACE_RULE && rule.style.fontFamily.replace(/["']/g, '') === 'Roboto Mono') sheet.deleteRule(i);
      }
      if ([...document.fonts].some(face => face.family.replace(/["']/g, '') === 'Roboto Mono')) throw new Error('Font-removal fixture did not remove the CSS-connected face.');
    });
    await negative('old-data-stroke', () => document.querySelector('path.edge.data').style.strokeWidth = '3.3px');
    await negative('old-node-radius', () => document.querySelector('.node rect.face').setAttribute('rx', '6'));
    await negative('wrong-legend-stroke', () => document.querySelector('.legend-line .edge').style.strokeWidth = '5px');
    await negative('wrong-arrow-stroke', () => document.querySelector('.marker.data').style.strokeWidth = '4px');
    await negative('wrong-bridge-halo', () => document.querySelector('.bridge-halo').style.strokeWidth = '1px', 'assets/architecture_diagrams/layout-primitives.html');
    // A failed embedded font must surface a render error, not silently lay out using a fallback.
    const goodHTML = await readFile(resolve(root, 'assets/base-template.html'), 'utf8');
    const damagedHTML = goodHTML.replace(/data:font\/woff2;base64,[A-Za-z0-9+/=]+/, 'data:font/woff2;base64,AA==');
    assert.notEqual(damagedHTML, goodHTML, 'Expected an embedded WOFF2 face to corrupt.');
    await page.setContent(damagedHTML, {waitUntil: 'load'});
    await ready();
    const failedFont = await page.evaluate(() => ({error: window.architectureRenderError, svgCount: document.querySelectorAll('svg#architecture').length}));
    negatives.push({name: 'corrupt-embedded-font', rejected: Boolean(failedFont.error) && failedFont.svgCount === 0, details: failedFont});
  }
  await writeFile(join(output, 'report.json'), JSON.stringify({results, negatives}, null, 2));
  for (const result of results) assert(result.ok && !result.errors.length && !result.warnings.length && !result.renderError && !result.pageErrors.length && !result.externalRequests.length && !result.controls && result.presentationBehavior, `${result.name} failed; see ${output}/report.json`);
  for (const test of negatives) assert(test.rejected, `Checker falsely passed ${test.name}`);
  console.log(`${results.length} render cases and ${negatives.length} negative DOM cases passed. Screenshots: ${output}`);
} finally {await browser.close();}
