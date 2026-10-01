# Chinese and mixed Chinese/Latin slides

Use `--language zh-CN` or JSON `"language": "zh-CN"`. The CLI option takes
precedence. This selects Simplified Chinese section labels and missing-data
phrases; it never translates supplied content. `en` remains the default. The
`check` command identifies the profile from the slide's explicit language tags.

```sh
python scripts/fill_update.py fill update.json update.pptx --layout blocker --language zh-CN
python scripts/fill_update.py check update.pptx --layout blocker
```

## Required fonts

The editor/rendering machine needs **Noto Sans CJK SC Regular and Bold, version
2.004**. Use the official [Noto CJK distribution](https://github.com/notofonts/noto-cjk/tree/main/Sans):
its Simplified Chinese static OTFs or the Regular/Bold TTCs containing the SC
faces. Font files are not bundled, installed, downloaded or embedded by the
helper. The helper can generate/check a PPTX without installed fonts, but it
cannot inspect or prevent another application's font substitution. Install the
fonts and render the exact output before sharing it.

Both Latin and East Asian runs explicitly request the same SC family. This
avoids assuming that a Latin font's fallback has matching widths. The packaged
metrics record each measured font's version, SHA-256, actual character coverage,
and advances. Their OFL-1.1 notice is in `assets/CJK_FONT_LICENSE.txt`. Original
code and layouts retain their MIT license.

## Fit behavior and limits

- Han characters can wrap without spaces; Latin words/URLs remain intact
- Common opening/closing Chinese punctuation is kept with neighboring text;
  this is a small rule set, not a full Unicode line-breaking engine
- Widths use the font's real advances, plus a conservative quarter-em allowance
  at adjacent East Asian/Latin boundaries observed in LibreOffice
- The existing 6% width margin remains. Four-pixel horizontal insets cover glyph
  overhang. A 0.12-em vertical guard and a fixed 130px headline box accommodate
  Noto Latin descenders. Font sizes, positions, overlap checks and explicit line
  caps remain fixed; no content-dependent box growth or font shrinking occurs
- Metrics cover measured BMP Han/Extension A/compatibility ideographs, a Latin
  subset, common Chinese punctuation and fullwidth ASCII. Missing glyphs, rare
  stacked accents outside the measured ink envelope, combining marks, emoji,
  variation selectors and all non-BMP characters fail before PPTX creation
- No automatic Traditional Chinese conversion, TC/HK glyph localization,
  Japanese/Korean layout, vertical text, complex-script shaping or translation
  is provided. Do not silently replace the user's characters when rejected
- Fit/glyph coverage checks apply to visible slide text. Speaker notes preserve
  supplied provenance; their typography is not part of the one-slide fit check

The exact examples and maximum-line fixtures were rendered in LibreOfficeDev
26.8 with Noto Sans CJK SC 2.004. PowerPoint, Keynote and Google Slides remain
untested. Passing structural checks is not cross-editor visual certification.
