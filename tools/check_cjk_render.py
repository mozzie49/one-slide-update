"""Optional rendered QA: python tools/check_cjk_render.py output_dir regular.ttc bold.ttc
Requires PyMuPDF and fontTools. This does not certify other renderers.
"""
import json,sys
from pathlib import Path
import fitz
from fontTools.ttLib import TTFont
from fontTools.pens.boundsPen import BoundsPen
from xml.etree import ElementTree as ET
REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO/'skills/one-slide-update/scripts'));import fill_update as f
fonts={w:TTFont(p,fontNumber=2) for w,p in zip(('Regular','Bold'),sys.argv[2:4])}
glyphs={w:font.getGlyphSet() for w,font in fonts.items()}; bounds={}
def ink(ch,weight):
 key=(ch,weight)
 if key not in bounds:
  font=fonts[weight];name=font.getBestCmap()[ord(ch)];pen=BoundsPen(glyphs[weight]);glyphs[weight][name].draw(pen);bounds[key]=pen.bounds
 return bounds[key]
results=[]
for path in sorted((Path(sys.argv[1])/'pdf').glob('*.pdf')):
 layout=path.stem.rsplit('-',1)[1];parts=f.load_package(path.parent.parent/(path.stem+'.pptx'));slide,shapes=f.check_package(parts,layout)
 shapes=slide.findall('.//p:sp',f.NS)
 expected=[]
 for sh in shapes:
  off=sh.find('p:spPr/a:xfrm/a:off',f.NS);ext=sh.find('p:spPr/a:xfrm/a:ext',f.NS)
  box=tuple(int(e.get(k))/12700 for e,k in [(off,'x'),(off,'y'),(ext,'cx'),(ext,'cy')])
  for p in sh.findall('p:txBody/a:p',f.NS):
   text=''.join(t.text or '' for t in p.findall('.//a:t',f.NS));expected.append((f.shape_name(sh),text,box))
 doc=fitz.open(path);page=doc[0];actual=[l for b in page.get_text('rawdict')['blocks'] for l in b.get('lines',[])]
 assert len(actual)==len(expected),(path,len(actual),len(expected))
 max_out=0;count=0
 for line,(name,text,(x,y,w,h)) in zip(actual,expected):
  rendered=''.join(c['c'] for s in line['spans'] for c in s['chars'] if not c.get('synthetic'))
  assert rendered.replace(' ','')==text.replace(' ',''),(path,name,rendered,text)
  for span in line['spans']:
   assert span['font'].startswith('NotoSansCJKsc-'),(path,span['font'])
   weight='Bold' if 'Bold' in span['font'] else 'Regular'
   for c in span['chars']:
    if c.get('synthetic') or c['c'].isspace():continue
    bound=ink(c['c'],weight)
    if not bound:continue
    left,bottom,right,top=bound;scale=span['size']/1000;ox,oy=c['origin']
    xx0,yy0,xx1,yy1=ox+left*scale,oy-top*scale,ox+right*scale,oy-bottom*scale
    over=max(x-xx0,y-yy0,xx1-(x+w),yy1-(y+h),0)
    max_out=max(max_out,over);count+=1
    assert over<=.75,(path,name,c['c'],over,(x,y,w,h),(xx0,yy0,xx1,yy1))
 results.append({'file':path.name,'lines':len(actual),'glyphs':count,'max_outline_overrun_pt':round(max_out,5),'fonts':'NotoSansCJKsc-Regular/Bold only','text_preserved':True})
print(json.dumps(results,ensure_ascii=False,indent=2))
