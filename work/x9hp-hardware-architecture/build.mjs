import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const taskDirectory=path.dirname(fileURLToPath(import.meta.url));
// Reuse the approved native glyphs, palette, theme and embedded fonts, not a new icon set.
const approved=fs.readFileSync(path.resolve(taskDirectory,'../cockpit-symbol-library-review/build-template.mjs'),'utf8');
const primitives=approved.slice(0,approved.indexOf('// Page 1:'))
  .replace(/^#!.*\n/,'').replace(/^import .*;\n/gm,'')
  .replace('const here = path.dirname(fileURLToPath(import.meta.url));','const here = taskDirectory;');
const layout=fs.readFileSync(path.join(taskDirectory,'layout.js'),'utf8');
vm.compileFunction(primitives+'\n'+layout,['fs','path','fileURLToPath','createHash','taskDirectory'])(fs,path,fileURLToPath,createHash,taskDirectory);
