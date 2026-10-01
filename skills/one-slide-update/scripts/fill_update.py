#!/usr/bin/env python3
"""Fill/check the original One Slide Update PPTX assets. Python 3.10+, stdlib only."""
from __future__ import annotations
import argparse
import copy
import json
import math
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ASSETS = Path(__file__).resolve().parents[1] / 'assets'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
for prefix, uri in NS.items(): ET.register_namespace(prefix, uri)
A, P = '{'+NS['a']+'}', '{'+NS['p']+'}'
EMU = 9525  # one pixel at 96dpi
MAX_BYTES = 20 * 1024 * 1024
KEYS = {'layout','project','period','as_of','status','headline','progress','next',
        'decision','milestone','owner','source_notes'}

class InputError(ValueError): pass

def resources():
    return (json.loads((ASSETS/'layouts.json').read_text()),
            json.loads((ASSETS/'font-metrics.json').read_text()))

def string(value, name, default):
    if value is None or value == '': return default
    if not isinstance(value, str): raise InputError(f'{name}: expected text or null')
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', value):
        raise InputError(f'{name}: unsupported control character')
    if len(value) > 5000: raise InputError(f'{name}: text is too long for one slide')
    return value.strip() or default

def items(value, name, default):
    if value is None or value == []: return default
    if not isinstance(value, list): raise InputError(f'{name}: expected an array of text')
    if len(value) > 10: raise InputError(f'{name}: at most 10 items; shorten this one-slide update')
    if any(not isinstance(item,str) or not item.strip() for item in value):
        raise InputError(f'{name}: every item must be nonempty text')
    return '\n'.join('• '+string(item,name,'') for item in value)

def prepare(data):
    if not isinstance(data,dict): raise InputError('Input must be a JSON object')
    unknown=set(data)-KEYS
    if unknown: raise InputError('Unknown input field(s): '+', '.join(sorted(unknown)))
    milestone=data.get('milestone')
    if milestone is None: milestone={}
    if not isinstance(milestone,dict) or set(milestone)-{'label','date'}:
        raise InputError('milestone: expected an object containing only label and date')
    label=string(milestone.get('label'),'milestone.label','Milestone not provided')
    date=string(milestone.get('date'),'milestone.date','Date not provided')
    owner=string(data.get('owner'),'owner','Owner not provided')
    period=string(data.get('period'),'period','Period not provided')
    as_of=string(data.get('as_of'),'as_of','not provided')
    notes=data.get('source_notes')
    if notes is None: notes=[]
    if not isinstance(notes,list) or any(not isinstance(x,str) for x in notes):
        raise InputError('source_notes: expected an array of text')
    notes=[string(x,'source_notes','') for x in notes]
    fields={
        'project':string(data.get('project'),'project','Project not provided'),
        'metadata':period+' / As of '+as_of,
        'status':string(data.get('status'),'status','Not assessed'),
        'headline':string(data.get('headline'),'headline','Update not provided'),
        'progress':items(data.get('progress'),'progress','Progress not provided'),
        'next':items(data.get('next'),'next','Next step not provided'),
        'decision':string(data.get('decision'),'decision','Decision not provided'),
        'checkpoint':label+'\n'+date+'\n'+owner,
        'milestone_date':date,'milestone_label':label,'owner':owner,
    }
    return fields,notes

def text_width(text, metrics, size):
    missing=sorted(set(text)-set(metrics))
    if missing:
        raise InputError('Unsupported character(s) in fit metrics: '+repr(''.join(missing))+
                         '. Adapt the template/font and visually verify it; this helper supports Latin-script text.')
    return sum(metrics[ch] for ch in text)*size

def fit_lines(text, slot, metrics, name):
    """Explicit wraps with a 6% width guard; estimates, not a rendering guarantee."""
    width=slot['width']*.94
    size=slot['font_size_px']
    lines=[]
    for paragraph in text.splitlines():
        if not paragraph: lines.append(''); continue
        line=''
        continuation='  ' if paragraph.startswith('• ') else ''
        for word in paragraph.split():
            if text_width(word,metrics,size)>width:
                raise InputError(f'{name}: a word/URL is wider than its fixed box; shorten it')
            candidate=(line+' '+word) if line else word
            if text_width(candidate,metrics,size)>width:
                lines.append(line); line=continuation+word
            else: line=candidate
        lines.append(line)
    cap=min(slot['max_lines'],math.floor(slot['height']/(size*slot['line_height'])))
    if len(lines)>cap:
        raise InputError(f'{name}: needs {len(lines)} lines, but this layout allows {cap}; shorten it or choose another layout')
    return lines

def load_package(path):
    if path.stat().st_size>MAX_BYTES: raise InputError('PPTX exceeds the 20 MiB safety limit')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>500 or sum(i.file_size for i in infos)>MAX_BYTES:
            raise InputError('PPTX package exceeds bounded size limits')
        if len({i.filename for i in infos})!=len(infos): raise InputError('Duplicate ZIP members')
        return {i.filename:z.read(i) for i in infos}

def shape_name(shape):
    item=shape.find('p:nvSpPr/p:cNvPr',NS)
    return item.get('name','') if item is not None else ''

def check_package(parts, layout, allow_placeholders=False):
    manifest,_=resources()
    if not isinstance(layout,str) or layout not in manifest['layouts']: raise InputError('Unknown layout: '+str(layout))
    slide_names=[n for n in parts if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
    if slide_names!=['ppt/slides/slide1.xml']: raise InputError('Expected exactly one slide')
    try:
        pres=ET.fromstring(parts['ppt/presentation.xml'])
        slide=ET.fromstring(parts[slide_names[0]])
    except (ET.ParseError,KeyError) as e: raise InputError('Invalid presentation XML') from e
    size=pres.find('p:sldSz',NS)
    expected=[round(x*EMU) for x in manifest['slide_size_px']]
    if size is None or [int(size.get(k,0)) for k in ('cx','cy')]!=expected:
        raise InputError('Slide dimensions changed; expected the fixed 16:9 canvas')
    if any(slide.find('.//p:'+tag,NS) is not None for tag in ('grpSp','pic','graphicFrame','cxnSp')):
        raise InputError('Only the packaged flat text layouts are supported; other objects need separate review')
    slots=manifest['layouts'][layout]['slots']
    found={}
    boxes=[]
    for shape in slide.findall('.//p:sp',NS):
        name=shape_name(shape)
        xfrm=shape.find('p:spPr/a:xfrm',NS)
        if xfrm is None: raise InputError(f'{name}: missing shape geometry')
        off,ext=xfrm.find('a:off',NS),xfrm.find('a:ext',NS)
        if off is None or ext is None: raise InputError(f'{name}: incomplete shape geometry')
        vals=[int(off.get(k,0)) for k in ('x','y')]+[int(ext.get(k,0)) for k in ('cx','cy')]
        x,y,w,h=vals
        if x<0 or y<0 or w<=0 or h<=0 or x+w>expected[0]+1 or y+h>expected[1]+1:
            raise InputError(f'{name}: shape is outside fixed slide bounds')
        if int(xfrm.get('rot',0)) or xfrm.get('flipH')=='1' or xfrm.get('flipV')=='1':
            raise InputError(f'{name}: rotated/flipped shapes need separate layout review')
        boxes.append((name,x,y,w,h))
        if name.startswith('slot.'):
            key=name[5:]
            if key not in slots or key in found: raise InputError('Unexpected/duplicate text slot: '+name)
            spec=slots[key]
            target=[round(spec[k]*EMU) for k in ('x','y','width','height')]
            if any(abs(a-b)>1 for a,b in zip(vals,target)):
                raise InputError(f'{name}: fixed template geometry changed')
            found[key]=shape
            runs=shape.findall('p:txBody/a:p/a:r/a:rPr',NS)
            if not runs: raise InputError(f'{name}: no editable styled text')
            for run in runs:
                font=run.find('a:latin',NS)
                if font is None or font.get('typeface')!=manifest['font']:
                    raise InputError(f'{name}: font changed; fit estimate no longer applies')
                if (run.get('b','0')=='1') != spec['bold']:
                    raise InputError(f'{name}: font weight changed')
                if int(run.get('sz',0))!=round(spec['font_size_px']*75):
                    raise InputError(f'{name}: text size changed')
            if any(shape.find('p:txBody/a:bodyPr/a:'+tag,NS) is not None for tag in ('normAutofit','spAutoFit')):
                raise InputError(f'{name}: automatic text/shape resizing is not allowed')
    if set(found)!=set(slots): raise InputError('Template is missing expected editable slots')
    for i,(name,x,y,w,h) in enumerate(boxes):
        for other,xx,yy,ww,hh in boxes[i+1:]:
            if min(x+w,xx+ww)-max(x,xx)>EMU and min(y+h,yy+hh)-max(y,yy)>EMU:
                raise InputError(f'Text boxes overlap: {name} / {other}')
    if not allow_placeholders:
        _,all_metrics=resources()
        for key,shape in found.items():
            spec=slots[key]
            body=shape.find('p:txBody/a:bodyPr',NS)
            if body is None or body.get('wrap')!='none' or any(int(body.get(k,0)) for k in ('lIns','rIns','tIns','bIns')):
                raise InputError(f'{key}: wrapping or text insets changed')
            if shape.find('.//a:br',NS) is not None:
                raise InputError(f'{key}: extra manual breaks need separate fit review')
            lines=[''.join(t.text or '' for t in p.findall('.//a:t',NS)) for p in shape.findall('p:txBody/a:p',NS)]
            for paragraph in shape.findall('p:txBody/a:p',NS):
                pp=paragraph.find('a:pPr',NS)
                line_space=paragraph.find('a:pPr/a:lnSpc/a:spcPts',NS)
                expected_space=round(spec['font_size_px']*.75*spec['line_height']*100)
                if pp is None or line_space is None or int(line_space.get('val',0))!=expected_space:
                    raise InputError(f'{key}: line spacing changed')
                if any(int(pp.get(k,0)) for k in ('marL','indent')):
                    raise InputError(f'{key}: paragraph indentation changed')
                for tag in ('spcBef','spcAft'):
                    spacing=pp.find('a:'+tag+'/a:spcPts',NS)
                    if spacing is None or int(spacing.get('val',0))!=0:
                        raise InputError(f'{key}: paragraph spacing changed')
            metrics=all_metrics['bold' if spec['bold'] else 'regular']
            cap=min(spec['max_lines'],math.floor(spec['height']/(spec['font_size_px']*spec['line_height'])))
            if len(lines)>cap: raise InputError(f'{key}: too many rendered text lines')
            for line in lines:
                if text_width(line,metrics,spec['font_size_px'])>spec['width']*.94+.1:
                    raise InputError(f'{key}: line exceeds fixed text width budget')
    return slide,found

def replace_text(shape, lines, spec):
    body=shape.find('p:txBody',NS)
    base=copy.deepcopy(body.find('a:p/a:r/a:rPr',NS))
    for p in list(body.findall('a:p',NS)): body.remove(p)
    bp=body.find('a:bodyPr',NS)
    bp.set('wrap','none'); bp.set('anchor','t')
    for k in ('lIns','rIns','tIns','bIns'): bp.set(k,'0')
    for kind in ('normAutofit','spAutoFit','noAutofit'):
        for child in list(bp.findall('a:'+kind,NS)): bp.remove(child)
    ET.SubElement(bp,A+'noAutofit')
    for line in lines:
        p=ET.SubElement(body,A+'p')
        pp=ET.SubElement(p,A+'pPr',{'marL':'0','indent':'0'})
        ET.SubElement(pp,A+'buNone')
        spacing=ET.SubElement(pp,A+'lnSpc')
        ET.SubElement(spacing,A+'spcPts',{'val':str(round(spec['font_size_px']*.75*spec['line_height']*100))})
        for tag in ('spcBef','spcAft'):
            ET.SubElement(ET.SubElement(pp,A+tag),A+'spcPts',{'val':'0'})
        r=ET.SubElement(p,A+'r'); r.append(copy.deepcopy(base))
        ET.SubElement(r,A+'t',{'{http://www.w3.org/XML/1998/namespace}space':'preserve'}).text=line
        ET.SubElement(p,A+'endParaRPr',{'sz':str(round(spec['font_size_px']*75))})


def fill(data, layout, output):
    manifest,metrics=resources()
    if not isinstance(layout,str) or layout not in manifest['layouts']: raise InputError('Unknown layout: '+str(layout))
    fields,notes=prepare(data)
    spec=manifest['layouts'][layout]
    prepared={k:fit_lines(fields[k],v,metrics['bold' if v['bold'] else 'regular'],k) for k,v in spec['slots'].items()}
    template=ASSETS/spec['template']
    parts=load_package(template)
    slide,shapes=check_package(parts,layout,allow_placeholders=True)
    for key,shape in shapes.items(): replace_text(shape,prepared[key],spec['slots'][key])
    parts['ppt/slides/slide1.xml']=ET.tostring(slide,encoding='utf-8',xml_declaration=True)
    # Replace only the notes body, keeping native slide-number placeholders.
    note_name='ppt/notesSlides/notesSlide1.xml'
    if note_name in parts:
        note=ET.fromstring(parts[note_name])
        for shape in note.findall('.//p:sp',NS):
            ph=shape.find('p:nvSpPr/p:nvPr/p:ph',NS)
            if ph is not None and ph.get('type')=='body':
                body=shape.find('p:txBody',NS)
                for p in list(body.findall('a:p',NS)): body.remove(p)
                p=ET.SubElement(body,A+'p'); r=ET.SubElement(p,A+'r')
                ET.SubElement(r,A+'t').text='Source notes supplied with this update:\n'+('\n'.join(notes) if notes else 'No source notes provided.')
        parts[note_name]=ET.tostring(note,encoding='utf-8',xml_declaration=True)
    check_package(parts,layout)
    output=Path(output)
    if output.suffix.lower()!='.pptx': raise InputError('Output must have a .pptx extension')
    if output.exists(): raise InputError('Output already exists; choose a new filename')
    if not output.parent.is_dir(): raise InputError('Output directory does not exist')
    # Exclusive creation prevents accidental overwrite, including after a race.
    try:
        with output.open('xb') as handle:
            with zipfile.ZipFile(handle,'w',zipfile.ZIP_DEFLATED) as z:
                for name,payload in parts.items(): z.writestr(name,payload)
    except FileExistsError as e: raise InputError('Output already exists') from e
    return {'output':str(output),'layout':layout,'editable_text_slots':len(shapes),
            'checks':'fixed slide bounds, fixed slot geometry, non-overlap, font/size and conservative text-fit budgets',
            'visual_review':'Render and inspect before sharing; font substitution can change appearance.'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    fill_p=sub.add_parser('fill',help='Fill a supplied layout from JSON, without overwriting')
    fill_p.add_argument('input',type=Path); fill_p.add_argument('output',type=Path)
    fill_p.add_argument('--layout',choices=['standard','blocker','milestone'])
    check_p=sub.add_parser('check',help='Check a generated slide against the packaged layout')
    check_p.add_argument('pptx',type=Path);check_p.add_argument('--layout',required=True,choices=['standard','blocker','milestone'])
    args=parser.parse_args(argv)
    try:
        if args.command=='fill':
            if args.input.stat().st_size>100_000: raise InputError('Input JSON exceeds 100 KiB')
            data=json.loads(args.input.read_text(encoding='utf-8'))
            layout=args.layout or (data.get('layout','standard') if isinstance(data,dict) else 'standard')
            result=fill(data,layout,args.output)
        else:
            check_package(load_package(args.pptx),args.layout)
            result={'checked':str(args.pptx),'layout':args.layout,'result':'PASS',
                    'limit':'Structural and conservative fit checks; visual rendering still needs review.'}
        print(json.dumps(result,indent=2)); return 0
    except (InputError,OSError,ValueError,zipfile.BadZipFile,ET.ParseError) as e:
        print('Error: '+str(e),file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
