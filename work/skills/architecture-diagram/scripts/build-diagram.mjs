#!/usr/bin/env node
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const skillRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(import.meta.url);
const {validate} = require('../assets/model.js');
const escapeHTML = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const escapeJSON = s => s.replaceAll('<', '\\u003c').replaceAll('>', '\\u003e').replaceAll('&', '\\u0026').replaceAll('\u2028', '\\u2028').replaceAll('\u2029', '\\u2029');
const kebab = s => s.replace(/[A-Z]/g, ch => `-${ch.toLowerCase()}`);

async function readThemeBundle() {
  const theme = JSON.parse(await readFile(resolve(skillRoot, 'assets/theme.json'), 'utf8'));
  for (const key of ['minNodeFontSize', 'minTextFontSize']) if (!Number.isFinite(theme.presentation?.[key]) || theme.presentation[key] <= 0) throw new Error(`Invalid presentation threshold: ${key}.`);
  const fontRoot = resolve(skillRoot, 'assets/fonts');
  const manifest = JSON.parse(await readFile(resolve(fontRoot, 'manifest.json'), 'utf8'));
  const license = await readFile(resolve(fontRoot, manifest.licenseFile), 'utf8');
  const variables = [];
  for (const [name, font] of Object.entries(theme.fonts)) {
    const asset = manifest.fonts.find(f => f.family === font.family);
    if (!asset || font.weights.some(weight => !asset.requiredWeights.includes(weight))) {
      throw new Error(`Theme font ${font.family} does not match the pinned font manifest.`);
    }
    variables.push(`  --font-${kebab(name)}: ${font.stack};`);
  }
  for (const [section, prefix] of [['type', 'type'], ['radii', 'radius'], ['strokes', 'stroke']]) {
    for (const [name, value] of Object.entries(theme[section])) {
      if (!Number.isFinite(value) || value <= 0) throw new Error(`Invalid theme token ${section}.${name}.`);
      variables.push(`  --${prefix}-${kebab(name)}: ${value}px;`);
    }
  }
  const faces = await Promise.all(manifest.fonts.map(async font => {
    const bytes = await readFile(resolve(fontRoot, font.file));
    const hash = createHash('sha256').update(bytes).digest('hex');
    if (hash !== font.sha256) throw new Error(`Font checksum mismatch: ${font.file}.`);
    if (bytes.subarray(0, 4).toString('ascii') !== 'wOF2') throw new Error(`Not a WOFF2 font: ${font.file}.`);
    return `@font-face {\n  font-family: '${font.family}';\n  font-style: normal;\n  font-weight: ${font.weightRange};\n  font-display: block;\n  src: url(data:font/woff2;base64,${bytes.toString('base64')}) format('woff2');\n}`;
  }));
  return {
    theme,
    fontMetadata: {...manifest, licenseText: license},
    css: `${faces.join('\n')}\n:root {\n${variables.join('\n')}\n}`
  };
}

export async function buildDiagram(input, output, {presentation = 'original'} = {}) {
  if (!['original', 'article'].includes(presentation)) throw new Error('presentation must be original or article.');
  const model = typeof input === 'string' ? JSON.parse(await readFile(input, 'utf8')) : input;
  const report = validate(model);
  if (!report.ok) throw new Error(report.errors.map(e => `${e.code}: ${e.message}`).join('\n'));
  const [[style, validator, runtime], bundle] = await Promise.all([
    Promise.all(['style.css', 'model.js', 'runtime.js'].map(f => readFile(resolve(skillRoot, 'assets', f), 'utf8'))),
    readThemeBundle()
  ]);
  for (const source of [validator, runtime]) if (/<\/script/i.test(source)) throw new Error('Runtime contains an unsafe inline script terminator.');
  if (/<\/style/i.test(style + bundle.css)) throw new Error('Styles contain an unsafe inline style terminator.');
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="generator" content="architecture-diagram v2">
  <title>${escapeHTML(model.meta.title)}</title>
  <style>\n${bundle.css}\n${style}\n  </style>
</head>
<body>
  <main id="diagram-root"></main>
  <script id="diagram-model" type="application/json">${escapeJSON(JSON.stringify(model, null, 2))}</script>
  <script id="diagram-theme" type="application/json">${escapeJSON(JSON.stringify(bundle.theme, null, 2))}</script>
  <script id="diagram-presentation" type="application/json">${escapeJSON(JSON.stringify({mode: presentation}))}</script>
  <script id="diagram-font-metadata" type="application/json">${escapeJSON(JSON.stringify(bundle.fontMetadata, null, 2))}</script>
  <script>window.ArchitectureTheme = JSON.parse(document.getElementById('diagram-theme').textContent); window.ArchitecturePresentation = JSON.parse(document.getElementById('diagram-presentation').textContent);</script>
  <script>\n${validator}\n  </script>
  <script>\n${runtime}\n  </script>
  <script>
  window.architectureRenderError = null;
  window.architectureModel = undefined;
  window.architectureGeometry = undefined;
  window.architectureFontsLoaded = [];
  window.architectureReady = (async () => {
      const model = JSON.parse(document.getElementById('diagram-model').textContent);
      const report = ArchitectureModel.validate(model);
      if (!report.ok) throw new Error(report.errors.map(e => e.code + ': ' + e.message).join('\\n'));
      if (!document.fonts || typeof document.fonts.load !== 'function') {
        throw new Error('This browser does not support required embedded font loading.');
      }
      // Explicitly load every measured weight before creating any SVG text.
      // document.fonts.ready alone does not request fonts unused by the current DOM.
      const checks = Object.values(ArchitectureTheme.fonts).flatMap(font =>
        font.weights.map(weight => ({family: font.family, weight, query: weight + ' 16px "' + font.family + '"'})));
      await Promise.all(checks.map(async check => {
        let faces;
        try {faces = await document.fonts.load(check.query, 'Architecture /dev/hgsl · libgsl.so');}
        catch {throw new Error('Embedded font could not be loaded: ' + check.query);}
        if (!faces.length || faces.some(face => face.status !== 'loaded') || !document.fonts.check(check.query)) {
          throw new Error('Embedded font could not be loaded: ' + check.query);
        }
      }));
      await document.fonts.ready;
      window.architectureFontsLoaded = checks;
      renderArchitecture(model);
      return {ok: true};
  })().catch(error => {
      const message = document.createElement('pre');
      message.className = 'render-error';
      message.textContent = 'Diagram rendering failed: ' + error.message;
      document.getElementById('diagram-root').replaceChildren(message);
      window.architectureRenderError = error.message;
      return {ok: false, error: error.message};
  });
  </script>
</body>
</html>
`;
  await mkdir(dirname(resolve(output)), {recursive: true});
  await writeFile(output, html, 'utf8');
  return {model, output, report, presentation};
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  if (!(args.length === 2 || (args.length === 4 && args[2] === '--presentation'))) {console.error('Usage: node scripts/build-diagram.mjs input.diagram.json output.html [--presentation original|article]'); process.exitCode = 2;}
  else try {
    const {model, report} = await buildDiagram(resolve(args[0]), resolve(args[1]), {presentation: args[3] || 'original'});
    for (const warning of report.warnings) console.warn(`${warning.code}: ${warning.message}`);
    console.log(`Built ${model.meta.id}: ${args[1]}`);
  } catch (error) {console.error(error.message); process.exitCode = 1;}
}
