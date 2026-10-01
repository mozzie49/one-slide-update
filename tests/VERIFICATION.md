# V0 verification record

Checked 1 October 2026 in the local build environment.

## Passed

- 22 Python unittest cases, including all three layouts, native editable text,
  missing data, no fabricated default dates/status, input preservation, standalone
  copied-skill execution, overflow rejection, fixed canvas/shape geometry,
  changed font/line-spacing rejection, literal markup safety and no overwrite
- Python syntax compilation and skill frontmatter validation
- Three template PPTX files and four example PPTX files passed package integrity,
  geometry, font-policy and re-import checks
- The exact example bytes matched the independently validated copies
- All three templates, three filled examples and the missing-data example were
  rendered and individually inspected as PNGs
- Three additional synthetic fixtures filled the maximum permitted body-line
  counts and a two-line headline; all rendered within their assigned regions
- Source code and PPTX XML were scanned for private build paths; none are shipped

## Chinese-input check

The original realistic fixture in examples/inputs/chinese-update.json was run
through the blocker layout. It exited with code 2 and an explicit unsupported-
character error before creating a PPTX. Rendering was therefore not reached.
CJK font fallback and rendered line fit are unverified; v0 does not support CJK.
The English labels are unchanged. No workaround bypassed the fit check.

## Environment and limits

Python 3.12.14. Previews: LibreOfficeDev 26.8.0.0.alpha0, then Poppler PNG export.
The fill helper itself needs only Python 3.10+ and the bundled assets.

Microsoft PowerPoint, Keynote, Google Slides and automatic Codex/Claude skill
loading were not tested. The new skill has a separate blind behavioral smoke task
and rubric, but that agent-level test has not been run. No claim is made about
model accuracy, time saved, market demand or future stars. Font substitution and
other renderers can change appearance. Conservative text-fit checks are not a
pixel-fit guarantee. The v0 fit metrics support Latin-script text, not Chinese.

## Delivered PPTX SHA-256

- skills/one-slide-update/assets/blocker.pptx: aa7b062fd86aacd65ec9b485bbab19d4f4ca95b2c57e17ffc5c304857478ce8d
- skills/one-slide-update/assets/milestone.pptx: 96129a00f272cfc7ea0ecb03f603aafa523931cb26aff209b54b6dade95911bb
- skills/one-slide-update/assets/standard.pptx: 5677fa6aab08cd5f15a3a81622f67caade84a3f0a1542981dcfb45c6cfdf952f
- examples/outputs/missing-data.pptx: 3ce004dffa2fcc56ad59a6903e4123e94718874f6cb3bac78b2ab6b3d9eaf272
- examples/outputs/relay-blocker.pptx: 739f0dd7ccfa0d9936b4864c25c35744bf2082b0f28e2c2adbe18bb3c9249909
- examples/outputs/relay-milestone.pptx: 5c516895e720e79cb123a9af5aa4a10d0f29b3ac0cd535151fdc0ccfe582938b
- examples/outputs/relay-standard.pptx: 9c0febcbdd1a16879e6c4a626a145265b0fc6d859b9c6c0f6995f60135f3f3ce
