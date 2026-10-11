/* Shared semantic contract for architecture-diagram v2; works in Node and browsers. */
(function (root) {
  'use strict';
  const enums = {
    scope: ['system', 'subsystem'], view: ['layered', 'dataflow'],
    colorMode: ['technical', 'origin', 'responsibility'],
    responsibilityBasis: ['development', 'delivery', 'integration', 'maintenance'],
    container: ['domain', 'layer', 'process', 'group', 'hypervisor', 'hardware-region'],
    domainType: ['os', 'vm', 'soc', 'mcu', 'tee'],
    entityType: ['subsystem', 'process', 'library', 'class', 'interface', 'kernel-interface', 'driver', 'hardware', 'memory', 'firmware', 'runtime'],
    executionContext: ['userspace', 'kernel', 'hypervisor', 'firmware'],
    relation: ['dependency', 'call', 'ipc', 'read', 'write', 'transfer', 'notification', 'configuration'],
    origin: ['oem', 'native', 'vendor', 'unknown'],
    category: ['oem', 'tier1', 'soc-vendor', 'os-vendor', 'other'],
    paletteKey: ['blue', 'green', 'amber', 'purple', 'cyan', 'orange', 'pink', 'indigo'],
    side: ['top', 'bottom', 'left', 'right']
  };
  const fields = {
    model: 'version meta canvas sources parties containers nodes edges junctions',
    meta: 'id title subtitle description scope view colorMode responsibilityBasis specimen',
    source: 'id title locator', party: 'id label category paletteKey',
    container: 'id kind title subtitle parent x y w h domainType order hosts evidence',
    node: 'id entityType canonicalName description parent x y w h origin responsibleParty configured evidence resourceId interfacePath moduleName executionContext',
    edge: 'id from to relation mechanism label fromSide toSide fromOffset toOffset keepAnchor anchorReason via labelPosition evidence dataKind',
    junction: 'id edges'
  };
  const categoryPalette = {oem: 'blue', tier1: 'amber', 'soc-vendor': 'purple', 'os-vendor': 'green', other: 'cyan'};
  const nonSoftware = new Set(['hardware', 'memory']);
  const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  const nonempty = x => typeof x === 'string' && x.trim().length > 0;
  const finite = x => typeof x === 'number' && Number.isFinite(x);
  const identifier = x => nonempty(x) && /^[A-Za-z_][A-Za-z0-9_.$:+/@-]*$/.test(x);
  const displayName = node => node.entityType === 'kernel-interface' ? `${node.interfacePath} · ${node.moduleName}` : node.canonicalName;
  const edgeType = edge => ({dependency: 'dependency', call: 'control', ipc: 'control', read: 'data', write: 'data', transfer: 'data', notification: 'notification', configuration: 'config'})[edge.relation];

  function validateModel(model) {
    const errors = [], warnings = [];
    const error = (code, message) => errors.push({code, message});
    const warn = (code, message) => warnings.push({code, message});
    const result = () => ({ok: errors.length === 0, errors, warnings});
    const keys = (item, kind, location) => {
      if (!object(item)) {error('object', `${location} must be an object.`); return false;}
      const allowed = fields[kind].split(' ');
      for (const key of Object.keys(item)) if (!allowed.includes(key)) error('unknown-field', `${location}.${key} is not a v2 field.`);
      return true;
    };
    const choice = (value, name, location, optional = false) => {
      if (optional && value === undefined) return;
      if (!enums[name].includes(value)) error('enum', `${location} must be one of: ${enums[name].join(', ')}.`);
    };
    const english = (value, location, required = false) => {
      if (value === undefined && !required) return;
      if (!nonempty(value)) {error('text', `${location} must be nonempty text.`); return;}
      // A language detector cannot establish English. This catches common accidental CJK labels.
      if (/[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\u3040-\u30ff]/u.test(value)) error('english', `${location} must use English diagram text.`);
      if (/[\r\n]/.test(value)) error('text-line', `${location} must be a single logical line; wrapping is measured by the renderer.`);
    };
    if (!keys(model, 'model', 'model')) return result();
    if (model.version !== 2) error('version', 'Model version must be 2.');
    if (!keys(model.meta, 'meta', 'meta')) return result();
    const meta = model.meta;
    if (!nonempty(meta.id) || !/^[a-z][a-z0-9-]*$/.test(meta.id)) error('id', 'meta.id must be a lower-case kebab identifier.');
    ['title', 'subtitle', 'description'].forEach(k => english(meta[k], `meta.${k}`, k === 'title'));
    ['scope', 'view', 'colorMode'].forEach(k => choice(meta[k], k, `meta.${k}`));
    if (meta.specimen !== undefined && typeof meta.specimen !== 'boolean') error('type', 'meta.specimen must be boolean.');
    if (meta.specimen && !/\b(layout|specimen)\b/i.test(meta.title || '')) error('specimen', 'An abstract specimen must identify itself as a layout specimen in its title.');
    if (meta.colorMode === 'responsibility') choice(meta.responsibilityBasis, 'responsibilityBasis', 'meta.responsibilityBasis');
    else if (meta.responsibilityBasis !== undefined) error('color-mode', 'responsibilityBasis applies only to responsibility mode.');
    if (!object(model.canvas) || !finite(model.canvas.width) || !finite(model.canvas.height) || model.canvas.width <= 0 || model.canvas.height <= 0) error('canvas', 'canvas needs positive finite width and height.');
    else for (const key of Object.keys(model.canvas)) if (!['width', 'height'].includes(key)) error('unknown-field', `canvas.${key} is not a v2 field.`);
    const arrays = {};
    for (const field of ['sources', 'parties', 'containers', 'nodes', 'edges', 'junctions']) {
      const optional = ['parties', 'junctions'].includes(field);
      if (!Array.isArray(model[field]) && !(optional && model[field] === undefined)) error('array', `${field} must be an array.`);
      arrays[field] = Array.isArray(model[field]) ? model[field] : [];
    }
    if (!arrays.nodes.length) error('empty-model', 'A diagram must contain at least one node.');
    if (!arrays.containers.length) error('empty-model', 'A diagram must contain at least one container.');
    const maps = {};
    for (const [plural, kind] of [['sources', 'source'], ['parties', 'party'], ['containers', 'container'], ['nodes', 'node'], ['edges', 'edge']]) {
      maps[plural] = new Map();
      arrays[plural].forEach((item, i) => {
        const location = `${plural}[${i}]`;
        if (!keys(item, kind, location)) return;
        if (!nonempty(item.id) || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(item.id)) error('id', `${location}.id must be a stable identifier.`);
        else if (maps[plural].has(item.id)) error('duplicate-id', `${location}.id duplicates ${item.id}.`);
        else maps[plural].set(item.id, item);
      });
    }
    for (const id of maps.nodes.keys()) if (maps.containers.has(id)) error('duplicate-id', `Node and container ids must be distinct: ${id}.`);
    for (const source of maps.sources.values()) {
      if (!nonempty(source.title)) error('source', `Source ${source.id} needs a title.`);
      if (!nonempty(source.locator)) error('source', `Source ${source.id} needs a URL or repository path locator.`);
      else if (/^\s*(javascript|data):/i.test(source.locator)) error('source', `Source ${source.id} uses an invalid evidence locator.`);
    }
    const evidence = (item, required) => {
      if (item.evidence === undefined && !required) return;
      if (!Array.isArray(item.evidence) || (required && !item.evidence.length)) {error('evidence', `${item.id} needs nonempty evidence source ids.`); return;}
      for (const ref of item.evidence) if (!maps.sources.has(ref)) error('evidence-ref', `${item.id} references unknown source ${ref}.`);
    };
    const ancestors = item => {
      const list = [], seen = new Set([item.id]);
      while (item.parent !== undefined) {
        if (seen.has(item.parent)) {error('parent-cycle', `Containment cycle at ${item.id}.`); break;}
        seen.add(item.parent);
        const parent = maps.containers.get(item.parent);
        if (!parent) {error('parent', `${item.id} has unknown container ${item.parent}.`); break;}
        list.push(parent); item = parent;
      }
      return list;
    };
    const box = item => {
      if (!['x', 'y', 'w', 'h'].every(k => finite(item[k])) || item.w <= 0 || item.h <= 0) {error('bounds', `${item.id} needs finite x/y and positive w/h.`); return;}
      if (item.x < 0 || item.y < 0 || item.x + item.w > model.canvas?.width || item.y + item.h > model.canvas?.height) error('canvas-bounds', `${item.id} lies outside the canvas.`);
      const parent = maps.containers.get(item.parent);
      if (parent && (item.x < parent.x || item.y < parent.y || item.x + item.w > parent.x + parent.w || item.y + item.h > parent.y + parent.h)) error('containment', `${item.id} lies outside its parent ${parent.id}.`);
    };
    for (const c of maps.containers.values()) {
      choice(c.kind, 'container', `container ${c.id}.kind`);
      english(c.title, `${c.id}.title`, true); english(c.subtitle, `${c.id}.subtitle`);
      box(c); ancestors(c); evidence(c, c.kind === 'process' && !meta.specimen);
      if (c.kind === 'process' && !meta.specimen && !identifier(c.title)) error('process-name', `${c.id} must name a real process; put its role in subtitle.`);
      choice(c.domainType, 'domainType', `${c.id}.domainType`, true);
      if (c.domainType !== undefined && c.kind !== 'domain') error('domain-type', `Only domain containers have domainType: ${c.id}.`);
      if (c.kind === 'layer' && (!Number.isInteger(c.order) || c.order < 0)) error('layer-order', `Layer ${c.id} needs a nonnegative integer order.`);
      if (c.kind !== 'layer' && c.order !== undefined) error('layer-order', `Only layer containers have order: ${c.id}.`);
      if (c.kind !== 'hypervisor' && c.hosts !== undefined) error('hypervisor', `Only hypervisor containers have hosts: ${c.id}.`);
      if (c.kind === 'hypervisor') {
        if (!Array.isArray(c.hosts) || !c.hosts.length || new Set(c.hosts).size !== c.hosts.length) {error('hypervisor-hosts', `${c.id} needs distinct hosted VM domain ids.`); continue;}
        const hosted = c.hosts.map(id => maps.containers.get(id));
        if (hosted.some(vm => !vm || vm.kind !== 'domain' || vm.domainType !== 'vm')) {error('hypervisor-hosts', `${c.id} may host only VM domains.`); continue;}
        const left = Math.min(...hosted.map(v => v.x)), right = Math.max(...hosted.map(v => v.x + v.w));
        if (Math.abs(c.x - left) > 0.5 || Math.abs(c.x + c.w - right) > 0.5) error('hypervisor-span', `${c.id} must align with the combined left/right boundaries of its hosted VMs.`);
        if (c.y < Math.max(...hosted.map(v => v.y + v.h))) error('hypervisor-position', `${c.id} must be below all hosted VMs.`);
        const ancestorsOfHosted = new Set(hosted.flatMap(vm => ancestors(vm).map(a => a.id)));
        for (const other of maps.containers.values()) if (other.kind === 'domain' && !c.hosts.includes(other.id) && !ancestorsOfHosted.has(other.id) && !ancestors(other).some(a => c.hosts.includes(a.id)) && other.x < right && other.x + other.w > left && other.y < c.y) error('hypervisor-scope', `${c.id} spans unrelated domain ${other.id}.`);
      }
    }
    const layers = [...maps.containers.values()].filter(c => c.kind === 'layer');
    for (let i = 0; i < layers.length; i++) for (let j = i + 1; j < layers.length; j++) {
      const a = layers[i], b = layers[j];
      if (a.parent !== b.parent || a.order === b.order) continue;
      const top = a.order < b.order ? a : b, bottom = top === a ? b : a;
      if (top.y + top.h > bottom.y) error('layer-order', `${top.id} must be entirely above ${bottom.id}; a horizontal flow does not replace major layers.`);
    }
    const resources = new Map(), usedParties = new Set();
    for (const n of maps.nodes.values()) {
      choice(n.entityType, 'entityType', `${n.id}.entityType`);
      choice(n.executionContext, 'executionContext', `${n.id}.executionContext`, true);
      if (!nonempty(n.parent)) error('parent', `Node ${n.id} needs a parent container.`);
      const chain = ancestors(n); box(n); evidence(n, !meta.specimen);
      english(n.description, `${n.id}.description`);
      choice(n.origin, 'origin', `${n.id}.origin`, true);
      if (n.configured !== undefined && typeof n.configured !== 'boolean') error('type', `${n.id}.configured must be boolean.`);
      if (n.entityType === 'kernel-interface') {
        if (!nonempty(n.interfacePath) || !/^\/(dev|sys|proc)\/[^\s<>\\]+$/.test(n.interfacePath)) error('kernel-interface', `${n.id} needs an exported device or filesystem path; do not invent one for a driver.`);
        if (!identifier(n.moduleName)) error('kernel-interface', `${n.id} needs a real moduleName.`);
        if (n.canonicalName !== undefined && n.canonicalName !== displayName(n)) error('kernel-name-order', `${n.id} must use file path before module name.`);
      } else english(n.canonicalName, `${n.id}.canonicalName`, true);
      if (!meta.specimen) {
        if (meta.scope === 'subsystem' && n.entityType === 'subsystem') error('concrete-name', `${n.id} uses a logical subsystem block in a concrete subsystem view.`);
        if (n.entityType === 'library' && (!nonempty(n.canonicalName) || !/^[A-Za-z0-9_+.-]+(?:\.so(?:\.[A-Za-z0-9_.-]+)?|\.a|\.jar|\.dll|\.dylib)$/.test(n.canonicalName))) error('library-name', `${n.id} must use one actual library artifact name, not a role or combined names.`);
        if (['process', 'class', 'interface', 'driver'].includes(n.entityType) && !identifier(n.canonicalName)) error('concrete-name', `${n.id} must use a concrete implementation identifier; move role wording into description.`);
        if (meta.scope === 'subsystem' && ['library', 'class', 'interface'].includes(n.entityType) && (n.executionContext || 'userspace') === 'userspace' && !chain.some(c => c.kind === 'process')) error('process-membership', `${n.id} must belong to its real process container in a subsystem view.`);
        if (n.entityType === 'process' && chain.some(c => c.kind === 'process' && c.title === n.canonicalName)) error('duplicate-process', `${n.id} duplicates its containing process; show internals directly within that process.`);
      }
      if (n.entityType === 'memory') {
        if (!nonempty(n.resourceId)) error('resource-id', `Memory ${n.id} needs a physical resourceId.`);
        else if (resources.has(n.resourceId)) error('duplicate-resource', `${n.id} duplicates physical memory ${resources.get(n.resourceId)}.`);
        else resources.set(n.resourceId, n.id);
      } else if (n.resourceId !== undefined) error('resource-id', `Only memory nodes use resourceId: ${n.id}.`);
      if (!nonSoftware.has(n.entityType) && meta.colorMode === 'origin' && n.origin === undefined) error('origin', `${n.id} needs explicit origin or unknown.`);
      if (n.responsibleParty !== undefined && n.responsibleParty !== 'unknown' && !maps.parties.has(n.responsibleParty)) error('party-ref', `${n.id} references unknown responsibleParty ${n.responsibleParty}.`);
      if (!nonSoftware.has(n.entityType) && meta.colorMode === 'responsibility') {
        if (n.responsibleParty === undefined) error('responsibility', `${n.id} needs explicit responsibleParty or unknown.`);
        if (n.responsibleParty !== undefined && n.responsibleParty !== 'unknown') usedParties.add(n.responsibleParty);
      }
    }
    const usedColors = new Map();
    for (const party of maps.parties.values()) {
      english(party.label, `${party.id}.label`, true); choice(party.category, 'category', `${party.id}.category`);
      choice(party.paletteKey, 'paletteKey', `${party.id}.paletteKey`, true);
      if (meta.colorMode === 'responsibility' && usedParties.has(party.id)) {
        const color = party.paletteKey || categoryPalette[party.category];
        if (usedColors.has(color)) error('party-color', `${party.id} and ${usedColors.get(color)} need distinct paletteKey values in responsibility mode.`);
        else usedColors.set(color, party.id);
      }
    }
    for (const e of maps.edges.values()) {
      choice(e.relation, 'relation', `${e.id}.relation`); evidence(e, !meta.specimen);
      for (const end of ['from', 'to']) if (!maps.nodes.has(e[end])) error('edge-endpoint', `${e.id}.${end} must reference a node, not a container or unknown id.`);
      if (e.from === e.to) error('self-edge', `${e.id} must connect different nodes.`);
      english(e.label, `${e.id}.label`); english(e.mechanism, `${e.id}.mechanism`);
      if (e.relation === 'ipc' && !nonempty(e.mechanism)) error('ipc-mechanism', `${e.id} must name the IPC mechanism.`);
      if (e.dataKind !== undefined && !['payload', 'handle'].includes(e.dataKind)) error('data-kind', `${e.id}.dataKind must be payload or handle.`);
      if (['read', 'write', 'transfer'].includes(e.relation) && e.dataKind === 'handle') error('handle-not-data', `${e.id} passes a handle; use a control relation, not a payload data edge.`);
      for (const end of ['from', 'to']) {
        choice(e[`${end}Side`], 'side', `${e.id}.${end}Side`, true);
        const offset = e[`${end}Offset`];
        if (offset !== undefined && !finite(offset)) error('port-offset', `${e.id}.${end}Offset must be finite pixels.`);
      }
      if (e.keepAnchor !== undefined && typeof e.keepAnchor !== 'boolean') error('type', `${e.id}.keepAnchor must be boolean.`);
      if (e.keepAnchor && !nonempty(e.anchorReason)) error('anchor-reason', `${e.id} needs an anchorReason for its preserved or named port.`);
      if (e.via !== undefined) {
        if (!Array.isArray(e.via)) error('route', `${e.id}.via must be an array.`);
        else for (const step of e.via) if (!object(step) || Object.keys(step).length !== 1 || !['x', 'y'].includes(Object.keys(step)[0]) || !finite(Object.values(step)[0])) error('route', `${e.id} via step must have exactly one finite x or y.`);
      }
      if (e.labelPosition !== undefined && (!object(e.labelPosition) || !finite(e.labelPosition.x) || !finite(e.labelPosition.y) || ![undefined, 'start', 'middle', 'end'].includes(e.labelPosition.anchor) || Object.keys(e.labelPosition).some(k => !['x', 'y', 'anchor'].includes(k)))) error('label-position', `${e.id}.labelPosition needs finite x/y and an optional text anchor.`);
      // Crossing process/VM boundaries is legitimate; endpoints and mechanisms must come from evidence.
      if (e.relation === 'call' && maps.nodes.has(e.from) && maps.nodes.has(e.to)) {
        const owner = id => ancestors(maps.nodes.get(id)).find(c => c.kind === 'process');
        const a = owner(e.from), b = owner(e.to);
        if (a && b && a.id !== b.id) warn('cross-process-call', `${e.id} crosses processes; verify whether this should be IPC with a mechanism.`);
      }
    }
    const junctionIds = new Set();
    arrays.junctions.forEach((j, i) => {
      if (!keys(j, 'junction', `junctions[${i}]`)) return;
      if (!nonempty(j.id) || !/^[A-Za-z][A-Za-z0-9_-]*$/.test(j.id)) error('id', `junctions[${i}] needs a stable id.`);
      else if (junctionIds.has(j.id)) error('duplicate-id', `Duplicate junction id: ${j.id}.`);
      else junctionIds.add(j.id);
      if (!Array.isArray(j.edges) || j.edges.length < 2 || new Set(j.edges).size !== j.edges.length) {error('junction', `junctions[${i}] needs at least two distinct edge ids.`); return;}
      const edges = j.edges.map(id => maps.edges.get(id));
      if (edges.some(e => !e)) error('junction', `junctions[${i}] references an unknown edge.`);
      else if (edges.some(e => e.from !== edges[0].from || e.relation !== edges[0].relation || e.mechanism !== edges[0].mechanism || e.dataKind !== edges[0].dataKind)) error('junction', 'A branch may share a common source, relation and mechanism; unrelated channels must not merge.');
    });
    return result();
  }
  function validate(model) {
    try {return validateModel(model);}
    catch (error) {
      // Invalid JSON field types must produce a failed report, never a renderer crash or a pass.
      return {ok: false, errors: [{code: 'invalid-input', message: `Invalid model field type: ${error.message}`}], warnings: []};
    }
  }
  const api = {validate, displayName, edgeType};
  root.ArchitectureModel = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
