"""Patch only the known VCUpro legend; preserve all other native cells exactly."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET
from native_builder import Builder

OUT = Path(__file__).resolve().parent
path = OUT / 'vcupro-system-architecture.drawio'
tree = ET.parse(path)
root = tree.find('./diagram/mxGraphModel/root')
families = [('video','Video'),('audio','Audio'),('communication','Communication'),('control','Discrete control'),('rf','RF')]
old_ids = {'legend-'+family for family,_ in families} | {'legend-status'}
before = {e.get('id'): ET.tostring(e) for e in root if e.get('id') not in old_ids}

builder = Builder()
builder.page('legend-patch','Legend patch','',3520,4096)
for i,(family,label) in enumerate(families):
    builder.legend_entry('legend-'+family,label,40+i*232,120,220,family=family)
for identity,label,x,w,kind,value in [
    ('single','Signal direction',1344,256,'direction','single'),
    ('both','Bidirectional',1632,240,'direction','bidirectional'),
    ('physical','Physical connection',1904,280,'direction','physical'),
    ('reserved','Reserved link',2216,256,'linestyle','dashed')]:
    builder.legend_entry('legend-'+identity,label,x,120,w,legend_type=kind,value=value)
builder.text('legend-status','TBD = unresolved configuration',2504,120,944,24,
             size=13,color=builder.tokens['colors']['muted'])
new_cells = [deepcopy(e) for e in builder.root if e.get('id','').startswith('legend-')]
new_ids = {e.get('id') for e in new_cells}
for element in list(root):
    if element.get('id') in old_ids | new_ids:
        root.remove(element)
root.extend(new_cells)
after = {e.get('id'): ET.tostring(e) for e in root if e.get('id') not in new_ids}
# Previous corrected legends can be updated without treating their children as architecture cells.
before = {k:v for k,v in before.items() if k not in new_ids}
assert before == after, 'Non-legend cells changed; refusing to save.'
tree.write(path,encoding='utf-8',xml_declaration=True)
print(f'Patched {len(new_cells)} legend cells; preserved {len(before)} non-legend cells unchanged.')
