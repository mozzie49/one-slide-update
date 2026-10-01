#!/usr/bin/env python3
"""Fill/check the original One Slide Update PPTX assets. Python 3.10+, stdlib only."""
from __future__ import annotations
import argparse
import copy
import json
import math
import re
import sys
import unicodedata
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
KEYS = {'language','layout','project','period','as_of','status','headline','progress','next',
        'decision','milestone','owner','source_notes'}

class InputError(ValueError): pass

LANGUAGES = {'en': ('Liberation Sans', 'font-metrics.json'),
             'zh-CN': ('Noto Sans CJK SC', 'cjk-font-metrics.json')}
LABELS = {'zh-CN': {'progress':'本周进展','next':'下一步','checkpoint':'检查点',
                   'decision':'决策 / 支持','milestone':'下一里程碑'}}

class CJKMetrics(dict):
    """Profile marker: widths include conservative East Asian auto-spacing."""

def resources(language='en'):
    if language not in LANGUAGES: raise InputError('language: expected en or zh-CN')
    manifest=json.loads((ASSETS/'layouts.json').read_text())
    metrics=json.loads((ASSETS/LANGUAGES[language][1]).read_text())
    if language=='zh-CN':
        for weight in ('regular','bold'):
            metrics[weight]=CJKMetrics({chr(c):w for lo,hi,w in metrics[weight]['ranges'] for c in range(lo,hi+1)})
    if language=='zh-CN':
        for layout in manifest['layouts'].values():
            # Noto's Latin descenders need more vertical room on a two-line
            # headline. This is a fixed, checked profile adaptation, not autofit.
            layout['slots']['headline']['height']=130
            for slot in list(layout['slots'].values())+list(layout['labels'].values()):
                slot['inset_px']=4
            for slot in layout['slots'].values(): slot['vertical_guard_em']=.12
    manifest['font']=LANGUAGES[language][0]
    return manifest,metrics


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

def prepare(data, language='en'):
    if not isinstance(data,dict): raise InputError('Input must be a JSON object')
    if 'language' in data and data['language'] not in ('en','zh-CN'): raise InputError('language: expected en or zh-CN')
    unknown=set(data)-KEYS
    if unknown: raise InputError('Unknown input field(s): '+', '.join(sorted(unknown)))
    milestone=data.get('milestone')
    if milestone is None: milestone={}
    if not isinstance(milestone,dict) or set(milestone)-{'label','date'}:
        raise InputError('milestone: expected an object containing only label and date')
    defaults = ({'milestone.label':'里程碑未提供','milestone.date':'日期未提供',
        'owner':'负责人未提供','period':'报告周期未提供','as_of':'未提供','project':'项目未提供',
        'status':'未评估','headline':'更新未提供','progress':'进展未提供','next':'下一步未提供',
        'decision':'决策信息未提供'} if language=='zh-CN' else {})
    def get(value,name,default): return string(value,name,defaults.get(name,default))
    label=get(milestone.get('label'),'milestone.label','Milestone not provided')
    date=get(milestone.get('date'),'milestone.date','Date not provided')
    owner=get(data.get('owner'),'owner','Owner not provided')
    period=get(data.get('period'),'period','Period not provided')
    as_of=get(data.get('as_of'),'as_of','not provided')
    notes=data.get('source_notes')
    if notes is None: notes=[]
    if not isinstance(notes,list) or any(not isinstance(x,str) for x in notes):
        raise InputError('source_notes: expected an array of text')
    notes=[string(x,'source_notes','') for x in notes]
    fields={
        'project':get(data.get('project'),'project','Project not provided'),
        'metadata':period+(' / 截至 ' if language=='zh-CN' else ' / As of ')+as_of,
        'status':get(data.get('status'),'status','Not assessed'),
        'headline':get(data.get('headline'),'headline','Update not provided'),
        'progress':items(data.get('progress'),'progress',defaults.get('progress','Progress not provided')),
        'next':items(data.get('next'),'next',defaults.get('next','Next step not provided')),
        'decision':get(data.get('decision'),'decision','Decision not provided'),
        'checkpoint':label+'\n'+date+'\n'+owner,
        'milestone_date':date,'milestone_label':label,'owner':owner,
    }
    return fields,notes

def text_width(text, metrics, size):
    missing=sorted({ch for ch in text if ch not in metrics})
    if missing:
        raise InputError('Unsupported character(s) in fit metrics: '+repr(''.join(missing))+
                         '. No fallback glyph is allowed. Use language zh-CN for supported Chinese; otherwise adapt and render a suitable template.')
    width=sum(metrics[ch] for ch in text)
    if isinstance(metrics,CJKMetrics):
        # LibreOffice adds about 1/4 em at adjacent CJK/Latin boundaries.
        # Count punctuation too, deliberately overestimating some boundaries.
        wide=lambda c: unicodedata.east_asian_width(c) in ('W','F')
        width+=.25*sum(wide(a)!=wide(b) and not (a.isspace() or b.isspace()) for a,b in zip(text,text[1:]))
    return width*size

OPEN_PUNCT = set('（［｛〈《「『【〔〖〘〚“‘')
CLOSE_PUNCT = set('，。、；：！？％）］｝〉》」』】〕〗〙〛”’')

def cjk_units(text):
    """Han boundaries, intact Latin tokens, and a small explicit punctuation rule.

    This is deliberately not a full Unicode line-breaking/shaping engine.
    """
    raw=re.findall(r'[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff01-\uff5e“”‘’]| +|[^ \u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff01-\uff5e“”‘’]+',text)
    units=[]; pending=''
    for unit in raw:
        if unit.isspace(): pending+=' '; continue
        if unit in OPEN_PUNCT:
            pending+=unit; continue
        if unit in CLOSE_PUNCT and units and not pending:
            units[-1]+=unit
        else:
            units.append(pending+unit); pending=''
    if pending.strip(): units.append(pending)
    if units and units[0].strip()=='•' and len(units)>1:
        units[:2]=[units[0]+units[1]]
    return units

def width_budget(slot):
    return (slot['width']-2*slot.get('inset_px',0))*.94

def line_cap(slot):
    return min(slot['max_lines'],math.floor((slot['height']/slot['font_size_px']-slot.get('vertical_guard_em',0))/slot['line_height']))

def fit_lines(text, slot, metrics, name, language='en'):
    """Explicit wraps with the unchanged 6% width guard and fixed line cap."""
    width=width_budget(slot); size=slot['font_size_px']; lines=[]
    for paragraph in text.splitlines():
        if not paragraph: lines.append(''); continue
        # Validate before tokenization so unsupported characters cannot disappear.
        text_width(paragraph.replace('\t',' '),metrics,size)
        line=''; continuation='  ' if paragraph.startswith('• ') else ''
        units=cjk_units(paragraph.replace('\t',' ')) if language=='zh-CN' else paragraph.split()
        for word in units:
            candidate=(line+word if language=='zh-CN' else line+' '+word) if line else word.lstrip()
            if text_width(candidate,metrics,size)>width:
                if line:
                    lines.append(line.rstrip()); line=continuation+word.lstrip()
                else: line=word.lstrip()
                if text_width(line,metrics,size)>width:
                    raise InputError(f'{name}: a word/URL or punctuation group is wider than its fixed box; shorten it')
            else: line=candidate
        lines.append(line.rstrip())
    cap=line_cap(slot)
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

def check_package(parts, layout, allow_placeholders=False, language=None):
    if language is None:
        probe=ET.fromstring(parts.get('ppt/slides/slide1.xml',b'<empty/>'))
        langs={r.get('lang','en') for r in probe.findall('.//a:rPr',NS)}
        if len(langs)!=1: raise InputError('Mixed or missing language profile')
        language=langs.pop()
    manifest,_=resources(language)
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
    slots=dict(manifest['layouts'][layout]['slots'])
    slots.update({'label.'+k:v for k,v in manifest['layouts'][layout]['labels'].items()})
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
        if name.startswith(('slot.','label.')):
            key=name[5:] if name.startswith('slot.') else name
            if key not in slots or key in found: raise InputError('Unexpected/duplicate text slot: '+name)
            spec=slots[key]
            target=[round(spec[k]*EMU) for k in ('x','y','width','height')]
            if any(abs(a-b)>1 for a,b in zip(vals,target)):
                raise InputError(f'{name}: fixed template geometry changed')
            found[key]=shape
            if key.startswith('label.') and not allow_placeholders:
                actual=''.join(t.text or '' for t in shape.findall('.//a:t',NS))
                expected_label=LABELS[language][key[6:]] if language=='zh-CN' else spec['text']
                if actual!=expected_label: raise InputError(f'{name}: section label changed')
            runs=shape.findall('p:txBody/a:p/a:r/a:rPr',NS)
            if not runs: raise InputError(f'{name}: no editable styled text')
            for run in runs:
                fonts=[run.find('a:'+tag,NS) for tag in ('latin','ea','cs')]
                if any(font is None or font.get('typeface')!=manifest['font'] for font in fonts):
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
        _,all_metrics=resources(language)
        for key,shape in found.items():
            spec=slots[key]
            if key.startswith('label.') and language=='en':
                label_text=''.join(t.text or '' for t in shape.findall('.//a:t',NS))
                fit_lines(label_text,spec,all_metrics['bold'],key,language)
                continue
            body=shape.find('p:txBody/a:bodyPr',NS)
            if body is None or body.get('wrap')!='none' or any(int(body.get(k,0))!=round(spec.get('inset_px',0)*EMU) for k in ('lIns','rIns')) or any(int(body.get(k,0)) for k in ('tIns','bIns')):
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
            cap=line_cap(spec)
            if len(lines)>cap: raise InputError(f'{key}: too many rendered text lines')
            for line in lines:
                if text_width(line,metrics,spec['font_size_px'])>width_budget(spec)+.1:
                    raise InputError(f'{key}: line exceeds fixed text width budget')
    return slide,{k:v for k,v in found.items() if not k.startswith('label.')}

def replace_text(shape, lines, spec):
    body=shape.find('p:txBody',NS)
    base=copy.deepcopy(body.find('a:p/a:r/a:rPr',NS))
    for p in list(body.findall('a:p',NS)): body.remove(p)
    bp=body.find('a:bodyPr',NS)
    bp.set('wrap','none'); bp.set('anchor','t')
    for k in ('lIns','rIns'): bp.set(k,str(round(spec.get('inset_px',0)*EMU)))
    for k in ('tIns','bIns'): bp.set(k,'0')
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


def fill(data, layout, output, language=None):
    if language is None: language=data.get('language','en') if isinstance(data,dict) else 'en'
    if not isinstance(language,str): raise InputError('language: expected en or zh-CN')
    manifest,metrics=resources(language)
    if not isinstance(layout,str) or layout not in manifest['layouts']: raise InputError('Unknown layout: '+str(layout))
    fields,notes=prepare(data,language)
    spec=manifest['layouts'][layout]
    prepared={k:fit_lines(fields[k],v,metrics['bold' if v['bold'] else 'regular'],k,language) for k,v in spec['slots'].items()}
    template=ASSETS/spec['template']
    parts=load_package(template)
    slide,shapes=check_package(parts,layout,allow_placeholders=True,language='en')
    for shape in slide.findall('.//p:sp',NS):
        if language=='zh-CN':
            name=shape_name(shape)
            if name=='slot.headline':
                shape.find('p:spPr/a:xfrm/a:ext',NS).set('cy',str(round(spec['slots']['headline']['height']*EMU)))
            for run in shape.findall('.//a:rPr',NS):
                run.set('lang',language)
                for tag in ('latin','ea','cs'): run.find('a:'+tag,NS).set('typeface',manifest['font'])
        name=shape_name(shape)
        if name.startswith('label.') and language=='zh-CN':
            label_spec=spec['labels'][name[6:]]
            label=LABELS[language][name[6:]] if language=='zh-CN' else label_spec['text']
            lines=fit_lines(label,label_spec,metrics['bold'],name,language)
            replace_text(shape,lines,label_spec)
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
                ET.SubElement(r,A+'t').text=('本次更新的来源说明：\n' if language=='zh-CN' else 'Source notes supplied with this update:\n')+('\n'.join(notes) if notes else ('未提供来源说明。' if language=='zh-CN' else 'No source notes provided.'))
        parts[note_name]=ET.tostring(note,encoding='utf-8',xml_declaration=True)
    check_package(parts,layout,language=language)
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
    return {'output':str(output),'layout':layout,'language':language,'required_font':manifest['font'],'editable_text_slots':len(shapes),
            'checks':'fixed slide bounds, fixed slot geometry, non-overlap, font/size and conservative text-fit budgets',
            'visual_review':'Render and inspect before sharing; font substitution can change appearance.'}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    fill_p=sub.add_parser('fill',help='Fill a supplied layout from JSON, without overwriting')
    fill_p.add_argument('input',type=Path); fill_p.add_argument('output',type=Path)
    fill_p.add_argument('--layout',choices=['standard','blocker','milestone'])
    fill_p.add_argument('--language',choices=list(LANGUAGES),help='Section labels, missing-data text and font profile; does not translate input')
    check_p=sub.add_parser('check',help='Check a generated slide against the packaged layout')
    check_p.add_argument('pptx',type=Path);check_p.add_argument('--layout',required=True,choices=['standard','blocker','milestone'])
    args=parser.parse_args(argv)
    try:
        if args.command=='fill':
            if args.input.stat().st_size>100_000: raise InputError('Input JSON exceeds 100 KiB')
            data=json.loads(args.input.read_text(encoding='utf-8'))
            layout=args.layout or (data.get('layout','standard') if isinstance(data,dict) else 'standard')
            result=fill(data,layout,args.output,args.language)
        else:
            check_package(load_package(args.pptx),args.layout)
            result={'checked':str(args.pptx),'layout':args.layout,'result':'PASS',
                    'limit':'Structural and conservative fit checks; visual rendering still needs review.'}
        print(json.dumps(result,indent=2)); return 0
    except (InputError,OSError,ValueError,zipfile.BadZipFile,ET.ParseError) as e:
        print('Error: '+str(e),file=sys.stderr); return 2

if __name__=='__main__': raise SystemExit(main())
