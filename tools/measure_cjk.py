#!/usr/bin/env python3
"""Development-only metric regeneration. Requires fontTools, not used at runtime.

Usage: python tools/measure_cjk.py regular.ttc bold.ttc output.json
Uses the Noto Sans CJK SC face, preserving actual cmap coverage. No font downloads.
"""
import hashlib
import json
import sys
from pathlib import Path
from fontTools.ttLib import TTCollection, TTFont
from fontTools.pens.boundsPen import BoundsPen

RANGES = [(0x20,0x7e),(0xa0,0x24f),(0x3000,0x301f),(0x3400,0x4dbf),
          (0x4e00,0x9fff),(0xf900,0xfaff),(0xff01,0xff5e)]
PUNCTUATION = '‐‑‒–—‘’“”•…‰€'

def measure(path, weight):
    path = Path(path)
    fonts = TTCollection(path).fonts if path.suffix.lower() in ('.ttc','.otc') else [TTFont(path)]
    matches = [f for f in fonts if f['name'].getDebugName(1)=='Noto Sans CJK SC' and f['name'].getDebugName(2)==weight]
    if len(matches)!=1: raise ValueError('Expected exactly one Noto Sans CJK SC '+weight+' face')
    f=matches[0]; cmap=f.getBestCmap(); units=f['head'].unitsPerEm
    permitted={c for lo,hi in RANGES for c in range(lo,hi+1)} | {ord(c) for c in PUNCTUATION}
    values={c:f['hmtx'][g][0] / units for c,g in cmap.items() if c in permitted and g!='.notdef'}
    # Exclude glyphs outside the tested horizontal-text ink envelope, including
    # unusually tall stacked accents. Unsupported input must fail visibly.
    glyphs=f.getGlyphSet(); excluded=[]; xmin=0; ymin=0; ymax=0
    for c in list(values):
        pen=BoundsPen(glyphs);glyphs[cmap[c]].draw(pen)
        if pen.bounds:
            x0,y0,x1,y1=pen.bounds
            if y0 < -.30*units or y1 > 1.015*units:
                excluded.append(c); del values[c]; continue
            xmin=min(xmin,x0/units);ymin=min(ymin,y0/units);ymax=max(ymax,y1/units)
    ranges=[]
    for c,w in sorted(values.items()):
        if ranges and c==ranges[-1][1]+1 and w==ranges[-1][2]: ranges[-1][1]=c
        else: ranges.append([c,c,w])
    return {'ranges':ranges,'glyph_count':len(values),'excluded_by_ink_envelope':excluded,'ink_envelope_em':{'left':xmin,'bottom':ymin,'top':ymax}}, {'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'family':f['name'].getDebugName(1),'weight':weight,'version':f['name'].getDebugName(5),'units_per_em':units,
        'ascent_em':f['hhea'].ascent/units,'descent_em':f['hhea'].descent/units,
        'copyright':f['name'].getDebugName(0)}

if __name__=='__main__':
    result={'description':'Measured cmap coverage and hmtx advances, compacted only across equal-width consecutive supported code points. OFL-1.1; see CJK_FONT_LICENSE.txt.',
            'font':'Noto Sans CJK SC','units':'em','sources':{}}
    for path,weight in zip(sys.argv[1:3],['Regular','Bold']):
        result[weight.lower()],result['sources'][weight.lower()]=measure(path,weight)
    Path(sys.argv[3]).write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
