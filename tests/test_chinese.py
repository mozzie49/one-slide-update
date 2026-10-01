import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from test_fill_update import f,ROOT

class ChineseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.data=json.loads((ROOT/'examples/inputs/chinese-mixed-update.json').read_text())
        self.manifest,self.metrics=f.resources('zh-CN')
    def out(self,name='out'): return self.dir/(name+'.pptx')
    def fill(self,data=None,layout='standard'):
        out=self.out(); f.fill(self.data if data is None else data,layout,out);return f.load_package(out)
    def visible(self,parts):
        return ''.join(t.text or '' for t in ET.fromstring(parts['ppt/slides/slide1.xml']).findall('.//a:t',f.NS))
    def test_all_three_layouts_mixed_text_labels_and_fonts(self):
        for layout in self.manifest['layouts']:
            out=self.out(layout);f.fill(self.data,layout,out);parts=f.load_package(out)
            slide,slots=f.check_package(parts,layout)
            self.assertIn('本周进展',self.visible(parts));self.assertIn('Atlas API',self.visible(parts))
            self.assertFalse(any(n.startswith('ppt/media/') for n in parts))
            for run in slide.findall('.//a:rPr',f.NS):
                self.assertEqual(run.get('lang'),'zh-CN')
                for tag in ('latin','ea','cs'):
                    self.assertEqual(run.find('a:'+tag,f.NS).get('typeface'),'Noto Sans CJK SC')
    def test_original_chinese_input_with_explicit_profile(self):
        d=json.loads((ROOT/'examples/inputs/chinese-update.json').read_text())
        f.fill(d,'blocker',self.out(),language='zh-CN')
        self.assertIn('新版文章已完成初审',self.visible(f.load_package(self.out())))
    def test_missing_chinese_facts_are_not_inferred(self):
        for layout in self.manifest['layouts']:
            out=self.out(layout);f.fill({'language':'zh-CN'},layout,out);txt=self.visible(f.load_package(out))
            for phrase in ('未评估','日期未提供','负责人未提供','决策信息未提供','截至 未提供'):
                self.assertIn(phrase,txt)
            self.assertNotIn('2026',txt);self.assertNotIn('%',txt)
    def test_explicit_chinese_override_preserves_supplied_latin(self):
        d=dict(self.data,language='en');f.fill(d,'standard',self.out(),language='zh-CN')
        self.assertIn('Atlas API',self.visible(f.load_package(self.out())))
    def test_widths_are_not_latin_or_blanket_fullwidth(self):
        m=self.metrics['regular'];self.assertEqual(m['中'],1);self.assertLess(m['i'],.4)
        self.assertGreater(m['W'],m['i']);self.assertNotEqual(m['A'],f.resources()[1]['regular']['A'])
    def test_renderer_autospace_is_budgeted(self):
        m=self.metrics['regular'];base=m['中']+m['A']+m['文']
        self.assertAlmostEqual(f.text_width('中A文',m,1),base+.5)
    def test_han_width_boundary_and_overflow(self):
        slot=self.manifest['layouts']['standard']['slots']['project'];m=self.metrics['bold']
        self.assertEqual(f.fit_lines('中'*28,slot,m,'project','zh-CN'),['中'*28])
        with self.assertRaisesRegex(f.InputError,'project:'):f.fit_lines('中'*29,slot,m,'project','zh-CN')
    def test_mixed_width_boundary_is_conservative(self):
        slot=self.manifest['layouts']['standard']['slots']['project'];m=self.metrics['bold']
        n=1
        while f.text_width('中A'*n,m,28)<=f.width_budget(slot):n+=1
        self.assertEqual(len(f.fit_lines('中A'*(n-1),slot,m,'project','zh-CN')),1)
        with self.assertRaisesRegex(f.InputError,'project:'):f.fit_lines('中A'*n,slot,m,'project','zh-CN')
    def test_unspaced_chinese_wrap_preserves_characters(self):
        slot=self.manifest['layouts']['standard']['slots']['headline'];text='帮助中心新版文章已经完成初审上线日期仍需客服团队确认'
        lines=f.fit_lines(text,slot,self.metrics['bold'],'headline','zh-CN')
        self.assertEqual(''.join(lines),text);self.assertEqual(len(lines),2)
    def test_mixed_wrap_preserves_latin_tokens(self):
        slot=self.manifest['layouts']['standard']['slots']['headline'];text='帮助中心 AtlasAPI 联调完成，测试意见已收集，发布日期待确认'
        lines=f.fit_lines(text,slot,self.metrics['bold'],'headline','zh-CN')
        self.assertEqual(''.join(lines).replace(' ',''),text.replace(' ',''));self.assertTrue(any('AtlasAPI' in line for line in lines))
    def test_punctuation_not_orphaned(self):
        slot={'width':120,'height':300,'font_size_px':20,'max_lines':10,'line_height':1.22}
        text='请确认（试点范围），然后核对“验收时间”。'
        lines=f.fit_lines(text,slot,self.metrics['regular'],'text','zh-CN')
        self.assertEqual(''.join(lines),text)
        for line in lines:
            self.assertNotIn(line[0],f.CLOSE_PUNCT);self.assertNotIn(line[-1],f.OPEN_PUNCT)
    def test_bullet_continuation_width_includes_indent(self):
        slot={'width':120,'height':300,'font_size_px':20,'max_lines':10,'line_height':1.22}
        lines=f.fit_lines('• 已完成API联调并确认测试方案',slot,self.metrics['regular'],'progress','zh-CN')
        self.assertGreater(len(lines),1)
        for line in lines:self.assertLessEqual(f.text_width(line,self.metrics['regular'],20),120*.94)
    def test_long_latin_word_still_fails(self):
        d=dict(self.data,headline='测试'+('W'*100))
        with self.assertRaisesRegex(f.InputError,'wider'):self.fill(d)
        self.assertFalse(self.out().exists())
    def test_cjk_overflow_never_writes_or_truncates(self):
        with self.assertRaisesRegex(f.InputError,'headline:'):self.fill(dict(self.data,headline='中文测试'*100))
        self.assertFalse(self.out().exists())
    def test_non_bmp_and_missing_glyph_boundaries_rejected(self):
        for ch in ('\U00020000','\U0002ffff','\U0001f680','\ufffd','\ufe0f','\u0301','\u9fff','\ud800','\u01d7','\u3031','\u302b'):
            with self.subTest(code=hex(ord(ch))),self.assertRaisesRegex(f.InputError,'Unsupported character'):
                self.fill(dict(self.data,headline='测试'+ch))
            self.assertFalse(self.out().exists())
    def test_supported_bmp_edges_come_from_cmap(self):
        for ch in ('\u3400','\u4e00','\u9fef'):
            self.assertIn(ch,self.metrics['regular']);self.assertEqual(f.text_width(ch,self.metrics['regular'],1),1)
    def test_changed_east_asian_font_rejected(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        slide.find('.//a:ea',f.NS).set('typeface','SimSun');parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'font changed'):f.check_package(parts,'standard')
    def test_changed_chinese_label_rejected(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        labels=[s for s in slide.findall('.//p:sp',f.NS) if f.shape_name(s).startswith('label.')]
        labels[0].find('.//a:t',f.NS).text='错误标签';parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'section label'):f.check_package(parts,'standard')
    def test_wrong_or_mixed_language_profile_rejected(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        slide.find('.//a:rPr',f.NS).set('lang','en');parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'language profile'):f.check_package(parts,'standard')
    def test_invalid_language_rejected(self):
        for language in (None,False,[],{},'zh-TW','xx'):
            with self.subTest(language=language),self.assertRaises(f.InputError):self.fill(dict(self.data,language=language))
    def test_copied_skill_fill_and_check_from_unrelated_directory(self):
        copied=self.dir/'skill';shutil.copytree(ROOT/'skills/one-slide-update',copied)
        inp=self.dir/'input.json';inp.write_text(json.dumps(self.data,ensure_ascii=False))
        script=str(copied/'scripts/fill_update.py')
        for args in (['fill',str(inp),str(self.out()),'--layout','blocker'],['check',str(self.out()),'--layout','blocker']):
            r=subprocess.run([sys.executable,script]+args,cwd=self.dir,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
    def test_original_english_artifacts_still_check(self):
        for layout in ('standard','blocker','milestone'):
            f.check_package(f.load_package(ROOT/'examples/outputs'/('relay-'+layout+'.pptx')),layout)
    def test_cjk_headline_uses_fixed_safe_geometry(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        headline=next(sh for sh in slide.findall('.//p:sp',f.NS) if f.shape_name(sh)=='slot.headline')
        height=headline.find('p:spPr/a:xfrm/a:ext',f.NS)
        self.assertEqual(int(height.get('cy')),130*f.EMU)
        height.set('cy',str(122*f.EMU));parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'geometry'):f.check_package(parts,'standard')
    def test_cjk_ink_padding_cannot_be_removed(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        slide.find('.//a:bodyPr',f.NS).set('lIns','0');parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'insets'):f.check_package(parts,'standard')
    def test_cjk_label_padding_is_checked(self):
        parts=self.fill();slide=ET.fromstring(parts['ppt/slides/slide1.xml'])
        label=next(sh for sh in slide.findall('.//p:sp',f.NS) if f.shape_name(sh).startswith('label.'))
        label.find('p:txBody/a:bodyPr',f.NS).set('tIns','900000');parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'insets'):f.check_package(parts,'standard')
    def test_cjk_every_slot_still_rejects_extra_line(self):
        for layout in self.manifest['layouts'].values():
            for name,slot in layout['slots'].items():
                text='\n'.join(['中']*(f.line_cap(slot)+1))
                with self.subTest(name=name),self.assertRaisesRegex(f.InputError,name+':'):
                    f.fit_lines(text,slot,self.metrics['bold' if slot['bold'] else 'regular'],name,'zh-CN')
    def test_chinese_input_not_modified(self):
        before=copy.deepcopy(self.data);self.fill();self.assertEqual(self.data,before)

if __name__=='__main__': unittest.main()
