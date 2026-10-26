#!/usr/bin/env node
/* Regression tests for article sizing, trusted height messages and original mode. */
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {buildDiagram} from './build-diagram.mjs';
import {skillRoot, fixtureOrigin, launchBrowser, openArticle, injectHelper, settleArticle,
  auditArticle, articleMetrics, saveArticleScreenshots} from './verify-article.mjs';

const args = process.argv.slice(2), options = {};
for (let index = 0; index < args.length; index += 2) {
  if (!['--output', '--browser'].includes(args[index]) || !args[index + 1]) {
    throw new Error('Usage: test-presentation.mjs --output /tmp/qa [--browser /path/to/chromium]');
  }
  options[args[index].slice(2)] = args[index + 1];
}
if (!options.output) throw new Error('--output is required.');
const output = resolve(options.output);
await mkdir(output, {recursive: true});
const base = JSON.parse(await readFile(join(skillRoot, 'assets/base-model.json'), 'utf8'));
const aaos = JSON.parse(await readFile(join(skillRoot, 'assets/models/aaos-audio-overview.json'), 'utf8'));
const wide = structuredClone(base); wide.meta.id = 'qa-oversized-article'; wide.canvas.width = 2400;
const artifacts = {};
for (const [name, model, presentation] of [['base', base, 'article'], ['aaos', aaos, 'article'],
  ['wide', wide, 'article'], ['original', base, 'original']]) {
  const path = join(output, `${name}.html`);
  await buildDiagram(model, path, {presentation});
  artifacts[name] = await readFile(path, 'utf8');
}
const browser = await launchBrowser(options.browser), results = [];
const check = async (name, test) => {
  try { const details = await test(); results.push({name, passed: true, details}); console.log(`PASS ${name}`); }
  catch (error) { results.push({name, passed: false, error: error.stack || error.message}); console.error(`FAIL ${name}: ${error.message}`); }
};
const requirePass = result => assert(result.ok, JSON.stringify({errors: result.errors, warnings: result.warnings}));
const hasError = (result, code) => result.errors.some(error => error.code === code);
const useArticle = async (settings, run) => {
  const session = await openArticle(browser, settings);
  try { return await run(session); } finally { await session.context.close(); }
};

try {
  await check('compact-models-at-real-article-widths', async () => {
    const reports = [];
    for (const name of ['base', 'aaos']) for (const width of [1200, 960]) {
      await useArticle({diagrams: [artifacts[name]], width}, async session => {
        const report = await auditArticle(session); requirePass(report);
        await saveArticleScreenshots(session, output, `${name}-${width}`);
        reports.push({name, width, metrics: report.metrics, presentation: report.diagrams[0].presentation});
      });
    }
    return reports;
  });

  await check('resize-updates-the-existing-iframe-height', () => useArticle({diagrams: [artifacts.aaos], width: 1200}, async session => {
    const before = await session.page.evaluate(articleMetrics);
    await session.page.setViewportSize({width: 960 + 48, height: 900});
    await settleArticle(session);
    const report = await auditArticle(session); requirePass(report);
    assert(report.metrics.frames[0].height < before.frames[0].height - 10, 'A narrower scaled diagram should reduce the iframe height.');
    return {before, after: report.metrics};
  }));

  await check('missing-helper-fails-then-late-and-duplicate-helper-recover', () => useArticle({diagrams: [artifacts.aaos], helper: false}, async session => {
    const absent = await auditArticle(session);
    assert(hasError(absent, 'frame-vertical-clipping'), 'A short iframe without the helper must fail.');
    await session.page.evaluate(() => {
      const original = window.addEventListener;
      window.__messageListenerCount = 0;
      window.addEventListener = function(type, ...rest) {
        if (type === 'message') window.__messageListenerCount++;
        return original.call(this, type, ...rest);
      };
    });
    await injectHelper(session); requirePass(await auditArticle(session));
    await injectHelper(session); requirePass(await auditArticle(session));
    const listeners = await session.page.evaluate(() => window.__messageListenerCount);
    assert.equal(listeners, 1, 'Loading the helper twice must register one message listener.');
    return {missingHelperErrors: absent.errors, listeners, recovered: await session.page.evaluate(articleMetrics)};
  }));

  await check('multiple-frames-reject-forged-messages-and-remain-isolated', () => useArticle({diagrams: [artifacts.base, artifacts.aaos]}, async session => {
    requirePass(await auditArticle(session));
    const rejections = await session.page.evaluate(() => {
      const frames = [...document.querySelectorAll('iframe')];
      const target = frames[0], origin = new URL(target.src).origin;
      const type = `${target.dataset.architectureDiagram}-height`;
      const heights = () => frames.map(frame => frame.style.height);
      const before = JSON.stringify(heights()), results = [];
      const reject = (name, data, source = target.contentWindow, messageOrigin = origin) => {
        window.dispatchEvent(new MessageEvent('message', {data, source, origin: messageOrigin}));
        results.push({name, rejected: JSON.stringify(heights()) === before});
      };
      reject('wrong-origin', {type, height: 444}, target.contentWindow, 'https://other.test');
      reject('opaque-origin', {type, height: 444}, target.contentWindow, 'null');
      reject('wrong-window', {type, height: 444}, window);
      reject('other-iframe', {type, height: 444}, frames[1].contentWindow);
      reject('null-source', {type, height: 444}, null);
      reject('wrong-type', {type: `${type}-other`, height: 444});
      for (const value of [null, '444', NaN, Infinity, -1, 0, 12001, undefined]) {
        reject(`invalid-height-${String(value)}`, {type, height: value});
      }
      reject('array-payload', [type, 444]);
      reject('null-payload', null);
      return results;
    });
    assert(rejections.every(result => result.rejected), JSON.stringify(rejections));
    const before = await session.page.evaluate(articleMetrics);
    await session.frames[0].evaluate(origin => {
      const root = document.querySelector('.architecture-document');
      const height = Math.ceil(root.getBoundingClientRect().bottom + scrollY
        + parseFloat(getComputedStyle(document.body).paddingBottom));
      parent.postMessage({type: `${architectureModel.meta.id}-height`, height: height + 40}, origin);
    }, fixtureOrigin);
    await session.page.waitForFunction(previous => document.querySelector('iframe').getBoundingClientRect().height > previous + 20,
      before.frames[0].height, {timeout: 2000});
    const changed = await session.page.evaluate(articleMetrics);
    assert.equal(changed.frames[1].height, before.frames[1].height, 'One child must not resize another frame.');
    await session.page.evaluate(origin => {
      const frame = document.querySelector('iframe');
      frame.contentWindow.postMessage({type: `${frame.dataset.architectureDiagram}-request-height`}, origin);
    }, fixtureOrigin);
    await settleArticle(session); requirePass(await auditArticle(session));
    return {rejections, before, changed};
  }));

  for (const [name, html, width] of [['oversized-canvas', artifacts.wide, 1200], ['phone-detail-view', artifacts.aaos, 390]]) {
    await check(`${name}-fails-the-actual-font-minimum`, () => useArticle({diagrams: [html], width}, async session => {
      const report = await auditArticle(session);
      assert(hasError(report, 'article-font-min'), JSON.stringify(report.errors));
      await saveArticleScreenshots(session, output, name);
      return {errors: report.errors, metrics: report.metrics, presentation: report.diagrams[0].presentation};
    }));
  }

  await check('parent-transform-cannot-hide-small-screen-text', () => useArticle({diagrams: [artifacts.base]}, async session => {
    await session.page.locator('figure').evaluate(element => { element.style.transform = 'scale(.5)'; element.style.transformOrigin = 'top left'; });
    const report = await auditArticle(session);
    assert(hasError(report, 'host-scale'), JSON.stringify(report.errors));
    return {errors: report.errors, metrics: report.metrics};
  }));

  await check('html-legend-transform-fails-the-text-minimum', () => useArticle({diagrams: [artifacts.base]}, async session => {
    await session.frames[0].locator('.diagram-legend').evaluate(element => { element.style.transform = 'scale(.5)'; element.style.transformOrigin = 'top left'; });
    const report = await auditArticle(session);
    assert(hasError(report, 'article-font-min'), JSON.stringify(report.errors));
    return {errors: report.errors};
  }));

  await check('original-mode-still-rejects-forced-scaling', () => useArticle({diagrams: [artifacts.original], width: 1200}, async session => {
    const frame = session.frames[0];
    const before = await frame.evaluate(() => checkDiagram({quiet: true}));
    assert(before.ok && !before.warnings.length, JSON.stringify(before));
    await frame.locator('svg#architecture').evaluate(element => { element.style.width = '50%'; element.style.height = 'auto'; });
    const after = await frame.evaluate(() => checkDiagram({quiet: true}));
    assert(hasError(after, 'diagram-scaled'), JSON.stringify(after.errors));
    return {errors: after.errors};
  }));
} finally {
  await writeFile(join(output, 'presentation-report.json'), JSON.stringify({results}, null, 2));
  await browser.close();
}
const failed = results.filter(result => !result.passed);
console.log(`${results.length - failed.length}/${results.length} presentation regressions passed.`);
if (failed.length) process.exitCode = 1;
