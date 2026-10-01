"""Generate 12 CJK visual-QA fixtures in a new output directory (stdlib only)."""
import sys,json
from pathlib import Path
from xml.etree import ElementTree as ET
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/one-slide-update/scripts'));import fill_update as f
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
data=json.loads((REPO/'examples/inputs/chinese-mixed-update.json').read_text())
manifest,metrics=f.resources('zh-CN')
for layout in manifest['layouts']:
 for kind,d in [('chinese-mixed',data),('chinese-missing',{'language':'zh-CN'}),('chinese-original',json.loads((REPO/'examples/inputs/chinese-update.json').read_text()))]:
  f.fill(d,layout,root/(kind+'-'+layout+'.pptx'),language='zh-CN')
 # Fill every slot to its exact maximum number of explicit lines, close to the width budget.
 parts=f.load_package(root/('chinese-mixed-'+layout+'.pptx'));slide,shapes=f.check_package(parts,layout)
 for key,shape in shapes.items():
  spec=manifest['layouts'][layout]['slots'][key];m=metrics['bold' if spec['bold'] else 'regular'];unit='中A測g'
  n=1
  while f.text_width(unit*n,m,spec['font_size_px'])<=f.width_budget(spec):n+=1
  text=unit*(n-1)
  while f.text_width(text+'中',m,spec['font_size_px'])<=f.width_budget(spec):text+='中'
  lines=[text]*f.line_cap(spec)
  f.replace_text(shape,lines,spec)
 parts['ppt/slides/slide1.xml']=ET.tostring(slide,encoding='utf-8',xml_declaration=True);f.check_package(parts,layout)
 import zipfile
 with zipfile.ZipFile(root/('boundary-'+layout+'.pptx'),'x',zipfile.ZIP_DEFLATED) as z:
  for name,blob in parts.items():z.writestr(name,blob)
print(root)
