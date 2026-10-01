# Verification record: Chinese profile update

Checked 1 October 2026. Local candidate for 0.2.0, based on 0.1.0.

## Passed in this update

- 49 Python unittest cases: all original 22 retained, plus 27 Chinese-profile
  cases. They cover every layout, real glyph metrics, mixed-script widths,
  Chinese punctuation, intact Latin tokens, line/width boundaries, missing facts,
  fixed CJK geometry/insets, modified labels/fonts, no overwrite, unsupported
  glyphs/non-BMP/variation selectors, and copied-skill fill plus check from an
  unrelated directory
- The original English example files still pass the strengthened checker. The
  three original templates and English example binaries are unchanged
- Twelve exact Chinese PPTX fixtures rendered to PDF and PNG: original Chinese,
  mixed Chinese/Latin, missing-data and maximum-line cases for all three layouts
- Each of the twelve PNGs individually inspected: legible characters, stable
  reading order, no visible clipping/overlap, and missing information preserved
- Exported PDF text matched the explicit slide lines (ignoring extraction's
  synthetic spaces). Only NotoSansCJKsc-Regular/Bold appeared; no font fallback
- Glyph outlines placed at the PDF's actual glyph origins remained inside their
  assigned boxes. Zero measured outline overruns across the twelve fixtures;
  individual counts are in `cjk-render-checks.json`
- Python syntax compilation and skill frontmatter validation
- New shipped examples are byte-identical to the rendered/checked fixtures

The first boundary pass caught CJK/Latin auto-spacing and Latin descenders below
an old two-line headline box. The final profile adds a conservative quarter-em
boundary allowance, a fixed 130px headline height, 4px horizontal ink padding,
and a 0.12-em vertical guard. These are fixed profile rules, not automatic
resizing. The 6% width margin and all original overlap/overflow checks remain.

## Fonts, runtime and scope

Python 3.12.14; LibreOfficeDev 26.8.0.0.alpha0; Poppler PNG export. The font faces
were Noto Sans CJK SC Regular/Bold 2.004. `cjk-font-metrics.json` records source
font SHA-256/version, per-face coverage and measured ink envelope. Coverage is
28,304 regular and 28,303 bold code points. Rare stacked accents outside the
supported horizontal ink envelope are explicitly rejected. No font binary is
shipped or installed.

The copied skill remains self-contained and uses Python 3.10+ standard library
only. The compact CJK metric resource is 7,306 bytes. A local 20-fill timing check
averaged about 0.04 seconds per Chinese slide; this is an environment-specific
observation, not a performance guarantee. Rendering and developer metric/outline
checks have separate optional dependencies.

Microsoft PowerPoint, Keynote, Google Slides and automatic Codex/Claude skill
loading were not tested. The behavioral prompt/rubric exists but the independent
agent-level smoke has not been run for this update. No support is claimed for
all Unicode, non-BMP Han, emoji, vertical text, TC/HK-localized glyphs or complex
shaping. Speaker-note typography is outside the visible slide fit check.

## Reproduce the optional visual checks

Install the required fonts on the rendering machine first. Use a fresh directory:

```sh
python tools/make_cjk_qa.py /path/to/qa
mkdir /path/to/qa/pdf
soffice --headless --convert-to pdf --outdir /path/to/qa/pdf /path/to/qa/*.pptx
```

`tools/check_cjk_render.py` additionally needs PyMuPDF and fontTools. Pass the
Regular/Bold Noto CJK TTCs (the SC face is index 2):

```sh
python tools/check_cjk_render.py /path/to/qa \
  /path/to/NotoSansCJK-Regular.ttc /path/to/NotoSansCJK-Bold.ttc
```

Use `pdftoppm -scale-to 1600 -singlefile -png input.pdf output` for each preview.
The script checks glyph outlines, font identity and text extraction; it does not
replace viewing the images or establish behavior in another editor.

To regenerate metric data (fontTools is a development-only dependency):

```sh
python tools/measure_cjk.py /path/to/NotoSansCJK-Regular.ttc \
  /path/to/NotoSansCJK-Bold.ttc /path/to/cjk-font-metrics.json
```

## Previous English verification

The 0.1.0 record included 22 tests, three template previews, three filled English
previews, a missing-data preview and three synthetic maximum-line fixtures.
Chinese input failed explicitly in that release. The same original Chinese
fixture still fails under default `en`; it now renders when `zh-CN` is selected.

## Delivered PPTX SHA-256

- skills/one-slide-update/assets/blocker.pptx: aa7b062fd86aacd65ec9b485bbab19d4f4ca95b2c57e17ffc5c304857478ce8d
- skills/one-slide-update/assets/milestone.pptx: 96129a00f272cfc7ea0ecb03f603aafa523931cb26aff209b54b6dade95911bb
- skills/one-slide-update/assets/standard.pptx: 5677fa6aab08cd5f15a3a81622f67caade84a3f0a1542981dcfb45c6cfdf952f
- examples/outputs/missing-data.pptx: 3ce004dffa2fcc56ad59a6903e4123e94718874f6cb3bac78b2ab6b3d9eaf272
- examples/outputs/relay-blocker.pptx: 739f0dd7ccfa0d9936b4864c25c35744bf2082b0f28e2c2adbe18bb3c9249909
- examples/outputs/relay-milestone.pptx: 5c516895e720e79cb123a9af5aa4a10d0f29b3ac0cd535151fdc0ccfe582938b
- examples/outputs/relay-standard.pptx: 9c0febcbdd1a16879e6c4a626a145265b0fc6d859b9c6c0f6995f60135f3f3ce

## New Chinese PPTX SHA-256

- examples/outputs/chinese-missing-standard.pptx: 87e6b92e5d1c52d9339c691d93b1c160fa7f3b290f9f75b94d502feaf00a49d7
- examples/outputs/chinese-mixed-blocker.pptx: 7b161c4cc7ea89215ce9af83ef2b39171963c7abf2469585edc93f0e59c758db
- examples/outputs/chinese-mixed-milestone.pptx: d268446a38ee5ed6269a67976db732ac9aca6ea3c8165c1d201681a054966715
- examples/outputs/chinese-mixed-standard.pptx: 4804dd33b26f69f675673ea131bfa73e2ef9d17ddbe8d8387b4b99645837d7cf
