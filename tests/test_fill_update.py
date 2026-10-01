import copy
import importlib.util
import json
import tempfile
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('fill_update',ROOT/'skills/one-slide-update/scripts/fill_update.py')
f=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(f)

class FillTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.data=json.loads((ROOT/'examples/inputs/relay-update.json').read_text())
    def output(self,name='out'):return self.dir/(name+'.pptx')
    def visible(self,path):
        parts=f.load_package(path);root=ET.fromstring(parts['ppt/slides/slide1.xml'])
        return '\n'.join(t.text or '' for t in root.findall('.//a:t',f.NS))
    def test_all_layouts_generate_native_editable_text(self):
        for layout in ('standard','blocker','milestone'):
            out=self.output(layout);report=f.fill(self.data,layout,out)
            parts=f.load_package(out);slide,slots=f.check_package(parts,layout)
            self.assertIn(len(slots),(8,10));self.assertNotIn('ppt/media/image1.png',parts)
            self.assertNotIn('%',self.visible(out));self.assertIn('24 October',self.visible(out))
            self.assertTrue(all(s.find('p:txBody',f.NS) is not None for s in slots.values()))
    def test_missing_data_is_not_inferred(self):
        out=self.output();f.fill({},'standard',out);text=self.visible(out)
        for phrase in ('Not assessed','Date not provided','Owner not provided','Decision not provided','As of not provided'):
            self.assertIn(phrase,text)
        self.assertNotIn('On track',text);self.assertNotIn('2026',text)
    def test_falsey_wrong_types_rejected(self):
        for key,value in [('headline',12),('progress','Completed'),('milestone',[]),('status',False)]:
            data=copy.deepcopy(self.data);data[key]=value
            # [] is not an object even when empty.
            with self.subTest(key=key),self.assertRaises(f.InputError):f.fill(data,'standard',self.output(key))
    def test_unknown_fields_rejected(self):
        self.data['percent_complete']=90
        with self.assertRaisesRegex(f.InputError,'Unknown input'):f.fill(self.data,'standard',self.output())
    def test_long_headline_fails_without_output(self):
        self.data['headline']='A very long required headline '*50
        with self.assertRaisesRegex(f.InputError,'headline:'):f.fill(self.data,'standard',self.output())
        self.assertFalse(self.output().exists())
    def test_long_word_fails(self):
        self.data['headline']='W'*100
        with self.assertRaisesRegex(f.InputError,'wider'):f.fill(self.data,'standard',self.output())
    def test_many_progress_items_fail_fit(self):
        self.data['progress']=['Required progress detail '+str(i) for i in range(10)]
        with self.assertRaisesRegex(f.InputError,'progress:'):f.fill(self.data,'blocker',self.output())
    def test_no_overwrite(self):
        out=self.output();out.write_bytes(b'KEEP')
        with self.assertRaisesRegex(f.InputError,'exists'):f.fill(self.data,'standard',out)
        self.assertEqual(out.read_bytes(),b'KEEP')
    def test_invalid_xml_character_rejected(self):
        self.data['headline']='Hello\x01world'
        with self.assertRaisesRegex(f.InputError,'control'):f.fill(self.data,'standard',self.output())
    def test_realistic_chinese_input_rejected_before_output(self):
        data=json.loads((ROOT/'examples/inputs/chinese-update.json').read_text())
        with self.assertRaisesRegex(f.InputError,'Unsupported character'):f.fill(data,'blocker',self.output())
        self.assertFalse(self.output().exists())
    def test_unsupported_script_is_explicit(self):
        self.data['headline']='项目更新'
        with self.assertRaisesRegex(f.InputError,'Unsupported character'):f.fill(self.data,'standard',self.output())
    def mutated(self):
        out=self.output();f.fill(self.data,'standard',out);parts=f.load_package(out)
        return parts,ET.fromstring(parts['ppt/slides/slide1.xml'])
    def test_out_of_bounds_rejected(self):
        parts,slide=self.mutated();slide.find('.//a:xfrm/a:off',f.NS).set('x','-100')
        parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'outside'):f.check_package(parts,'standard')
    def test_changed_slot_geometry_rejected(self):
        parts,slide=self.mutated();slide.find('.//a:xfrm/a:off',f.NS).set('x','12345')
        parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'geometry'):f.check_package(parts,'standard')
    def test_changed_line_spacing_rejected(self):
        parts,slide=self.mutated();slide.find('.//a:lnSpc/a:spcPts',f.NS).set('val','99999')
        parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'line spacing'):f.check_package(parts,'standard')
    def test_changed_font_rejected(self):
        parts,slide=self.mutated();slide.find('.//a:rPr/a:latin',f.NS).set('typeface','Comic Sans MS')
        parts['ppt/slides/slide1.xml']=ET.tostring(slide)
        with self.assertRaisesRegex(f.InputError,'font changed'):f.check_package(parts,'standard')
    def test_literal_markup_is_text_not_xml(self):
        self.data['headline']='Research < review & release'
        out=self.output();f.fill(self.data,'standard',out)
        self.assertIn('Research < review & release',self.visible(out))
    def test_notes_have_only_provided_sources(self):
        out=self.output();f.fill(self.data,'standard',out);parts=f.load_package(out)
        self.assertIn(b'Original fictional example',parts['ppt/notesSlides/notesSlide1.xml'])
        self.assertNotIn(b'Bracketed text',parts['ppt/notesSlides/notesSlide1.xml'])
    def test_input_not_modified(self):
        original=copy.deepcopy(self.data);f.fill(self.data,'standard',self.output())
        self.assertEqual(self.data,original)
    def test_fixed_slide_size_rejected(self):
        parts,slide=self.mutated();pres=ET.fromstring(parts['ppt/presentation.xml'])
        pres.find('p:sldSz',f.NS).set('cx','500')
        parts['ppt/presentation.xml']=ET.tostring(pres)
        with self.assertRaisesRegex(f.InputError,'dimensions'):f.check_package(parts,'standard')
    def test_standalone_copy_runs_from_unrelated_directory(self):
        copied=self.dir/'standalone';shutil.copytree(ROOT/'skills/one-slide-update',copied)
        input_path=self.dir/'input.json';input_path.write_text(json.dumps(self.data))
        result=subprocess.run([sys.executable,str(copied/'scripts/fill_update.py'),'fill',str(input_path),str(self.output()),'--layout','blocker'],cwd=self.dir,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertTrue(self.output().exists())
    def test_null_sources_and_invalid_empty_sources_are_distinct(self):
        data=dict(self.data,source_notes=None);f.fill(data,'standard',self.output())
        data['source_notes']={}
        with self.assertRaisesRegex(f.InputError,'source_notes'):f.fill(data,'standard',self.output('bad'))
    def test_supplied_status_is_preserved(self):
        self.data['status']='Not yet rated';out=self.output();f.fill(self.data,'standard',out)
        self.assertIn('Not yet rated',self.visible(out))

if __name__=='__main__':unittest.main()
