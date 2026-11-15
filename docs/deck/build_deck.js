const pptxgen = require('pptxgenjs');
const path = require('path');

const A = (n) => path.join(__dirname, 'assets', `${n}_FFFFFF.png`);

const THEME = {
  name: 'SignalTrace',
  headFontFace: 'Poppins',
  bodyFontFace: 'Calibri',
  colors: {
    dk1: '1B1E24',   // graphite near-black text (neutral, not blue-tinted)
    lt1: 'FFFFFF',   // white background
    dk2: '14171C',   // near-black graphite (title slide / dark panel bg)
    lt2: 'F2EFEA',   // warm light sand-gray (cards)
    accent1: 'B8752B', // amber-bronze - dominant data color
    accent2: '1B8C99', // signal cyan - secondary accent / highlight
    accent3: '23272E', // dark slate - supporting panel fill
    accent4: 'A8906A', // muted tan - thin lines / borders
    accent5: '8A8E96', // neutral gray (captions/footer)
    accent6: '2E2A22', // deep warm charcoal
    hlink: 'B8752B',
    folHlink: '1B8C99',
  },
};
const CLR = THEME.colors;
const ALARM = 'C0392B'; // coral-red, used only for false-alarm figures — not a theme slot

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };

const FOOTER_TEXT = 'So Much Data, So Little Space  •  Fall Committee Meeting  •  hectar';

pres.defineSlideMaster({
  title: 'CONTENT',
  background: { color: CLR.lt1 },
  slideNumber: { x: 12.7, y: 7.1, fontFace: THEME.bodyFontFace, fontSize: 10, color: CLR.accent5 },
  objects: [
    {
      placeholder: {
        options: {
          name: 'title', type: 'title',
          x: 1.55, y: 0.5, w: 11.0, h: 0.95,
          fontFace: THEME.headFontFace, fontSize: 30, bold: true,
          color: CLR.dk1, align: 'left', valign: 'middle', margin: 0,
        },
        text: 'Title',
      },
    },
    {
      text: {
        text: FOOTER_TEXT,
        options: {
          x: 0.5, y: 7.1, w: 9.5, h: 0.3,
          fontFace: THEME.bodyFontFace, fontSize: 10, color: CLR.accent5, align: 'left', margin: 0,
        },
      },
    },
  ],
});

function addHeaderIcon(slide, iconName) {
  // Rounded-square instrument chip with a thin offset ring, instead of a plain filled circle.
  slide.addShape('roundRect', { x: 0.46, y: 0.41, w: 0.95, h: 0.95, rectRadius: 0.16, fill: { type: 'none' }, line: { color: CLR.accent2, width: 1, dashType: 'dash' } });
  slide.addShape('roundRect', { x: 0.5, y: 0.45, w: 0.85, h: 0.85, rectRadius: 0.16, fill: { color: CLR.accent1 }, line: { type: 'none' } });
  slide.addImage({ path: A(iconName), x: 0.72, y: 0.67, w: 0.4, h: 0.4 });
}

function card(slide, { x, y, w, h, fill = CLR.lt2, accent = null }) {
  slide.addShape('roundRect', { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: 'none' } });
  if (accent) {
    slide.addShape('roundRect', { x, y, w, h: 0.07, rectRadius: 0.035, fill: { color: accent }, line: { type: 'none' } });
  }
}

function statCard(slide, { x, y, w, h, value, label, valueColor = CLR.accent1, accent = CLR.accent2 }) {
  card(slide, { x, y, w, h, accent });
  slide.addText(value, {
    x, y: y + 0.2, w, h: h - 0.7, align: 'center', valign: 'bottom',
    fontFace: THEME.headFontFace, fontSize: 30, bold: true, color: valueColor, margin: 0,
  });
  slide.addText(label, {
    x: x + 0.15, y: y + h - 0.55, w: w - 0.3, h: 0.5, align: 'center', valign: 'top',
    fontFace: THEME.bodyFontFace, fontSize: 11, color: CLR.dk1, margin: 0,
  });
}

function numberRow(slide, { x, y, w, n, head, body }) {
  slide.addShape('roundRect', { x, y, w: 0.42, h: 0.42, rectRadius: 0.09, fill: { color: CLR.accent1 }, line: { type: 'none' } });
  slide.addText(String(n), {
    x, y, w: 0.42, h: 0.42, align: 'center', valign: 'middle',
    fontFace: THEME.bodyFontFace, fontSize: 14, bold: true, color: CLR.lt1, margin: 0,
  });
  slide.addText(
    [
      { text: head + '  ', options: { bold: true, color: CLR.dk1 } },
      { text: body, options: { color: CLR.dk1 } },
    ],
    { x: x + 0.6, y: y - 0.05, w: w - 0.6, h: 0.55, fontFace: THEME.bodyFontFace, fontSize: 13, align: 'left', valign: 'middle', margin: 0 }
  );
}

// ---------- Slide 0: Title ----------
{
  const slide = pres.addSlide();
  slide.background = { color: CLR.dk2 };

  // Radar-scope motif: concentric rings with a sweep line and a detected "blip" —
  // a vessel that pings on radar but isn't where it should be.
  const cx = 10.85, cy = 3.75;
  [2.7, 2.05, 1.4, 0.75].forEach((r, i) => {
    slide.addShape('ellipse', {
      x: cx - r, y: cy - r, w: r * 2, h: r * 2,
      fill: { type: 'none' },
      line: { color: CLR.accent4, width: 0.75, transparency: 35 + i * 12 },
    });
  });
  slide.addShape('line', {
    x: cx, y: cy, w: 2.55, h: -2.0,
    line: { color: CLR.accent2, width: 1.25, transparency: 25 },
  });
  slide.addShape('ellipse', { x: cx + 0.95, y: cy - 1.15, w: 0.14, h: 0.14, fill: { color: CLR.accent1 }, line: { type: 'none' } });
  slide.addShape('roundRect', { x: cx - 0.34, y: cy - 0.34, w: 0.68, h: 0.68, rectRadius: 0.12, fill: { color: CLR.accent1 }, line: { type: 'none' } });
  slide.addImage({ path: A('whytask'), x: cx - 0.22, y: cy - 0.22, w: 0.44, h: 0.44 });

  slide.addText('So Much Data, So Little Space', {
    x: 0.9, y: 2.55, w: 11.5, h: 1.1, fontFace: THEME.headFontFace, fontSize: 38, bold: true,
    color: CLR.lt1, align: 'left', margin: 0,
  });
  slide.addText('Benchmarking SAR compression against dark-vessel detection accuracy', {
    x: 0.9, y: 3.6, w: 9.6, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 18, italic: true,
    color: CLR.lt2, align: 'left', margin: 0,
  });
  slide.addText('Fall Committee Meeting  •  hectar  •  October 2026', {
    x: 0.9, y: 4.35, w: 10, h: 0.4, fontFace: THEME.bodyFontFace, fontSize: 13,
    color: CLR.accent4, align: 'left', margin: 0,
  });
}

// ---------- Slide 1: Motivation ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'motivation');
  slide.addText('Motivation', { placeholder: 'title' });

  slide.addText(
    [
      { text: 'Satellites capture far more Earth-observation data than they can physically send home. ', options: {} },
      { text: 'I saw this firsthand working at a radar-based company this summer', options: { bold: true } },
      { text: ', where a handful of satellites generated more data than the ground segment could download and process fast enough, so the information they had just captured sat delayed instead of reaching anyone in time.', options: {} },
    ],
    { x: 0.9, y: 1.75, w: 6.9, h: 1.9, fontFace: THEME.bodyFontFace, fontSize: 15, color: CLR.dk1, align: 'left', valign: 'top', margin: 0, paraSpaceAfter: 6 }
  );
  slide.addText(
    [
      { text: 'Closing that gap changes what kind of work is possible. ', options: { italic: true, color: CLR.accent3 } },
      { text: 'It turns a result that used to arrive too late to act on into one that arrives in time to matter.', options: { color: CLR.dk1 } },
    ],
    { x: 0.9, y: 3.85, w: 6.9, h: 1.5, fontFace: THEME.bodyFontFace, fontSize: 15, align: 'left', valign: 'top', margin: 0 }
  );

  statCard(slide, { x: 8.15, y: 1.75, w: 4.3, h: 1.7, value: '520 Mbps', label: 'Sentinel-1 downlink rate, less than half its peak capture rate of 1,280 Mbps' });
  statCard(slide, { x: 8.15, y: 3.65, w: 4.3, h: 1.7, value: '~900 Gbit', label: 'Onboard recorder capacity, a limited buffer before data must wait for the next ground pass' });
  slide.addText('eoPortal, n.d.', { x: 8.15, y: 5.45, w: 4.3, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 9, italic: true, color: CLR.accent5, align: 'right', margin: 0 });
}

// ---------- Slide 1b: Why Dark-Vessel Detection, Specifically ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'whytask');
  slide.addText('Why Dark-Vessel Detection, Specifically', { placeholder: 'title' });

  slide.addText(
    'Detection accuracy is the yardstick for compression loss, but which detection task supplies that yardstick is a deliberate choice.',
    { x: 0.9, y: 1.65, w: 11.3, h: 0.55, fontFace: THEME.bodyFontFace, fontSize: 14, italic: true, color: CLR.dk2, align: 'left', margin: 0 }
  );

  const reasons = [
    {
      head: 'The failure mode has real stakes.',
      body: 'IUU fishing costs an estimated $10 to 23.5 billion a year (Agnew et al., 2009), and vessels that go dark are also the ones most likely to carry forced labor aboard (McDonald et al., 2021).',
    },
    {
      head: 'It has a built-in, scalable ground truth.',
      body: 'A SAR detection with no matching AIS broadcast is "dark" by definition, so the task checks itself automatically, without hand-labeling.',
    },
    {
      head: 'A public, compression-ready benchmark exists.',
      body: 'xView3-SAR pairs thousands of Sentinel-1 scenes with AIS-derived labels, and few SAR tasks have this much ground truth ready to reuse.',
    },
    {
      head: 'Small targets are where compression breaks first.',
      body: 'Vessels are the fine, low-contrast detail codecs degrade first, while a coarser task like land-cover classification wouldn’t separate them at all.',
    },
  ];
  let y = 2.5;
  for (let i = 0; i < reasons.length; i++) {
    numberRow(slide, { x: 0.9, y, w: 11.3, n: i + 1, head: reasons[i].head, body: reasons[i].body });
    y += 0.92;
  }

  card(slide, { x: 0.9, y: 6.45, w: 11.3, h: 0.62, fill: CLR.dk2 });
  slide.addText(
    [
      { text: 'In short, ', options: { bold: true, color: CLR.lt1 } },
      { text: 'this is the task where compression loss is both measurable at scale and visible first.', options: { color: CLR.lt2 } },
    ],
    { x: 1.1, y: 6.45, w: 10.9, h: 0.62, fontFace: THEME.bodyFontFace, fontSize: 12.5, align: 'left', valign: 'middle', margin: 0 }
  );
}

// ---------- Slide 2: Literature Review ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'litreview');
  slide.addText('Literature Review', { placeholder: 'title' });

  const rows = [
    { head: 'Onboard compression is already standard.', body: 'Sentinel-1’s FDBAQ scheme cuts data volume 37–62%, validated at 42–47% reduction on real sites (Malz et al., 2012).' },
    { head: 'Standards govern size.', body: 'CCSDS-123 and CEOS-ARD set compression and completeness criteria, but neither specifies a required downstream detection accuracy.' },
    { head: 'Learned compression and foundation models are emerging.', body: 'A complex-valued autoencoder beats BAQ by 4 to 6 dB SQNR, and TerraFM offers a pretrained Sentinel-1/2 embedding instead of training from scratch (Mohammadi Asiyabi et al., 2025, and Danish et al., 2025).' },
    { head: 'Task-based evaluation changes the answer.', body: 'Codecs matched on compression ratio can diverge sharply in detector accuracy, since reconstruction quality (PSNR/SSIM) doesn’t predict it (Chrabot, 2026).' },
  ];
  let y = 1.75;
  for (let i = 0; i < rows.length; i++) {
    numberRow(slide, { x: 0.9, y, w: 11.3, n: i + 1, head: rows[i].head, body: rows[i].body });
    y += 1.15;
  }

  card(slide, { x: 0.9, y: 6.25, w: 11.3, h: 0.78, fill: CLR.dk2 });
  slide.addText(
    [
      { text: 'The gap this project fills ', options: { bold: true, color: CLR.lt1 } },
      { text: 'is that no published study tests a learned SAR representation against a real detection task using task-based evaluation.', options: { color: CLR.lt2 } },
    ],
    { x: 1.1, y: 6.25, w: 10.9, h: 0.78, fontFace: THEME.bodyFontFace, fontSize: 13, align: 'left', valign: 'middle', margin: 0 }
  );
}

// ---------- Slide 3: Research Question ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'rq');
  slide.addText('Research Question', { placeholder: 'title' });

  card(slide, { x: 0.9, y: 1.85, w: 11.3, h: 1.75, fill: CLR.lt2 });
  slide.addText(
    'How much can raw SAR data be compressed, and by which representation, before the loss degrades dark-vessel detection accuracy below a useful threshold?',
    { x: 1.3, y: 1.85, w: 10.5, h: 1.75, fontFace: THEME.headFontFace, fontSize: 20, italic: true, color: CLR.dk2, align: 'left', valign: 'middle', margin: 0 }
  );

  slide.addText(
    [
      { text: 'Representation and bandwidth are the subject, and ', options: { color: CLR.dk1 } },
      { text: 'dark-vessel detection is only the yardstick', options: { bold: true, color: CLR.accent3 } },
      { text: ', a public, labeled task (xView3-SAR) that makes accuracy loss measurable instead of assumed.', options: { color: CLR.dk1 } },
    ],
    { x: 0.9, y: 3.85, w: 11.3, h: 0.8, fontFace: THEME.bodyFontFace, fontSize: 14, align: 'left', valign: 'top', margin: 0 }
  );

  const axes = [
    { label: 'Size', detail: 'bits per complex sample' },
    { label: 'Transmission time', detail: 'at a realistic downlink rate' },
    { label: 'Detection accuracy', detail: 'probability of detection, false alarms, AIS-match rate' },
  ];
  const aw = 3.63, gap = 0.2, ax0 = 0.9, ay = 4.95;
  axes.forEach((a, i) => {
    const x = ax0 + i * (aw + gap);
    card(slide, { x, y: ay, w: aw, h: 1.65, fill: CLR.lt1 });
    slide.addShape('roundRect', { x, y: ay, w: aw, h: 1.65, rectRadius: 0.08, fill: { color: CLR.lt1 }, line: { color: CLR.accent4, width: 1 } });
    slide.addText(a.label, { x: x + 0.2, y: ay + 0.18, w: aw - 0.4, h: 0.5, fontFace: THEME.headFontFace, fontSize: 16, bold: true, color: CLR.accent1, align: 'left', margin: 0 });
    slide.addText(a.detail, { x: x + 0.2, y: ay + 0.7, w: aw - 0.4, h: 0.85, fontFace: THEME.bodyFontFace, fontSize: 12.5, color: CLR.dk1, align: 'left', valign: 'top', margin: 0 });
  });
}

// ---------- Slide 4: Key Variables + Data Sources ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'variables');
  slide.addText('Key Variables & Data Sources', { placeholder: 'title' });

  card(slide, { x: 0.9, y: 1.75, w: 5.55, h: 3.15 });
  slide.addText('Representation type (the category)', { x: 1.15, y: 1.95, w: 5.1, h: 0.4, fontFace: THEME.headFontFace, fontSize: 15, bold: true, color: CLR.accent1, margin: 0 });
  {
    const repPairs = [
      { label: 'Raw backscatter', detail: '  no sweep, the reference point' },
      { label: 'BAQ', detail: '  swept by bit depth' },
      { label: 'HEVC', detail: '  swept by quantization parameter' },
      { label: 'JPEG2000', detail: '  swept by bitrate' },
      { label: 'Learned embedding (TerraFM + LoRA)', detail: '  swept by output size and bit depth' },
    ];
    const repRuns = [];
    repPairs.forEach((v) => {
      repRuns.push({ text: v.label, options: { bold: true } });
      repRuns.push({ text: v.detail, options: { breakLine: true, bullet: { code: '25CF' } } });
    });
    slide.addText(repRuns, { x: 1.3, y: 2.45, w: 4.9, h: 2.3, fontFace: THEME.bodyFontFace, fontSize: 12.5, color: CLR.dk1, align: 'left', valign: 'top', margin: 0, paraSpaceAfter: 8 });
  }

  card(slide, { x: 6.65, y: 1.75, w: 5.55, h: 3.15 });
  slide.addText('Dependent variables (per representation)', { x: 6.9, y: 1.95, w: 5.1, h: 0.4, fontFace: THEME.headFontFace, fontSize: 15, bold: true, color: CLR.accent1, margin: 0 });
  slide.addText(
    ['Bits per complex sample (size)', 'Transmission time at a fixed downlink rate', 'Detection probability (recall vs. xView3-SAR)', 'False alarm count', 'AIS-match rate (dark vs. reconciled)'].map((t) => ({ text: t, options: { bullet: { code: '25CF' }, breakLine: true } })),
    { x: 7.05, y: 2.45, w: 4.9, h: 2.3, fontFace: THEME.bodyFontFace, fontSize: 13, color: CLR.dk1, align: 'left', valign: 'top', margin: 0, paraSpaceAfter: 8 }
  );

  const sources = [
    { label: 'Sentinel-1 scenes', detail: 'Copernicus Data Space / ASF Vertex' },
    { label: 'Detection labels', detail: 'xView3-SAR' },
    { label: 'AIS broadcasts', detail: 'Global Fishing Watch / NOAA MarineCadastre' },
  ];
  const sw = 3.63, sx0 = 0.9, sy = 5.2;
  sources.forEach((s, i) => {
    const x = sx0 + i * (sw + 0.2);
    slide.addShape('roundRect', { x, y: sy, w: sw, h: 1.3, rectRadius: 0.08, fill: { color: CLR.accent3 }, line: { type: 'none' } });
    slide.addText(s.label, { x: x + 0.2, y: sy + 0.15, w: sw - 0.4, h: 0.4, fontFace: THEME.headFontFace, fontSize: 13.5, bold: true, color: CLR.lt1, margin: 0 });
    slide.addText(s.detail, { x: x + 0.2, y: sy + 0.58, w: sw - 0.4, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 11.5, color: CLR.lt2, margin: 0 });
  });
}

// ---------- Slide 5: Methods ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'methods');
  slide.addText('Methods', { placeholder: 'title' });

  slide.addText(
    'Task-based evaluation design (Chrabot, 2026) holds the scene fixed, varies the representation, and measures detection outcomes directly.',
    { x: 0.9, y: 1.7, w: 11.3, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 14, italic: true, color: CLR.dk2, align: 'left', margin: 0 }
  );

  const steps = ['Fixed scene', 'Vary representation', 'CFAR detector\n(+ pretrained baseline)', 'Validate with\nxView3-SAR + AIS'];
  const sw = 2.68, gap = 0.18, sx0 = 0.9, sy = 2.55;
  steps.forEach((s, i) => {
    const x = sx0 + i * (sw + gap);
    slide.addShape('roundRect', { x, y: sy, w: sw, h: 1.4, rectRadius: 0.1, fill: { color: i === 2 ? CLR.accent1 : CLR.lt2 }, line: { type: 'none' } });
    slide.addText(s, { x: x + 0.15, y: sy, w: sw - 0.3, h: 1.4, fontFace: THEME.bodyFontFace, fontSize: 12.5, bold: true, color: i === 2 ? CLR.lt1 : CLR.dk1, align: 'center', valign: 'middle', margin: 0 });
    if (i < steps.length - 1) {
      slide.addShape('rect', { x: x + sw, y: sy + 0.65, w: gap, h: 0.04, fill: { color: CLR.accent5 }, line: { type: 'none' } });
    }
  });

  slide.addShape('roundRect', { x: 0.9, y: 4.5, w: 11.3, h: 2.2, rectRadius: 0.08, fill: { color: CLR.lt2 }, line: { type: 'none' } });
  slide.addText('Threats to validity', { x: 1.15, y: 4.68, w: 10.8, h: 0.4, fontFace: THEME.headFontFace, fontSize: 15, bold: true, color: CLR.accent3, margin: 0 });
  slide.addText(
    [
      'A single AOI’s clutter statistics may not generalize to a second region.',
      'The learned embedding’s training data and evaluation scenes must stay disjoint to avoid leakage.',
      'AIS coverage gaps produce false “dark vessel” flags unrelated to compression.',
      'TerraFM is pretrained on focused backscatter, one step downstream of the raw samples BAQ/HEVC/JPEG2000 operate on, and this is reported explicitly rather than treated as equivalent.',
    ].map((t) => ({ text: t, options: { bullet: { code: '25CF' }, breakLine: true } })),
    { x: 1.3, y: 5.15, w: 10.6, h: 1.45, fontFace: THEME.bodyFontFace, fontSize: 12.5, color: CLR.dk1, align: 'left', valign: 'top', margin: 0, paraSpaceAfter: 5 }
  );
}

// ---------- Slide 6: Preliminary Analysis ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'prelim');
  slide.addText('Preliminary Analysis, Progress to Date', { placeholder: 'title' });

  slide.addText(
    [
      { text: 'The first comparison point is ', options: { bold: true, color: CLR.dk2 } },
      { text: 'a from-scratch CFAR detector run against the same scene’s raw, BAQ, and JPEG2000 representations.', options: { color: CLR.dk1 } },
    ],
    { x: 0.9, y: 1.65, w: 11.3, h: 0.5, fontFace: THEME.bodyFontFace, fontSize: 14, italic: true, align: 'left', margin: 0 }
  );

  const reps = [
    { name: 'Raw', sub: 'no compression', recall: '100%', fa: '0' },
    { name: 'BAQ', sub: '8.35× smaller', recall: '25%', fa: '0' },
    { name: 'JPEG2000', sub: '~39× smaller', recall: '65%', fa: '54' },
  ];
  const rw = 3.63, rgap = 0.2, rx0 = 0.9, ry = 2.3;
  reps.forEach((r, i) => {
    const x = rx0 + i * (rw + rgap);
    card(slide, { x, y: ry, w: rw, h: 2.75, accent: CLR.accent2 });
    slide.addText(r.name, { x: x + 0.25, y: ry + 0.27, w: rw - 0.5, h: 0.4, fontFace: THEME.headFontFace, fontSize: 18, bold: true, color: CLR.dk1, margin: 0 });
    slide.addText(r.sub, { x: x + 0.25, y: ry + 0.69, w: rw - 0.5, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 11, italic: true, color: CLR.accent5, margin: 0 });
    slide.addText(r.recall, { x: x + 0.25, y: ry + 1.07, w: rw - 0.5, h: 0.75, fontFace: THEME.headFontFace, fontSize: 38, bold: true, color: CLR.accent1, align: 'left', margin: 0 });
    slide.addText('recall vs. ground truth', { x: x + 0.25, y: ry + 1.82, w: rw - 0.5, h: 0.3, fontFace: THEME.bodyFontFace, fontSize: 10.5, color: CLR.dk1, margin: 0 });
    const faColor = r.fa === '0' ? CLR.accent5 : ALARM;
    slide.addText([{ text: r.fa, options: { bold: true, color: faColor } }, { text: '  false alarms', options: { color: CLR.dk1 } }], { x: x + 0.25, y: ry + 2.22, w: rw - 0.5, h: 0.35, fontFace: THEME.bodyFontFace, fontSize: 13, margin: 0 });
  });

  const chips = [
    { label: 'Schema', detail: '4 tables, GiST-indexed, live' },
    { label: 'TerraFM', detail: '768-dim embedding verified end-to-end' },
  ];
  const chw = 5.55, chy = 5.3;
  chips.forEach((c, i) => {
    const x = 0.9 + i * (chw + 0.2);
    slide.addShape('roundRect', { x, y: chy, w: chw, h: 0.75, rectRadius: 0.08, fill: { color: CLR.accent3 }, line: { type: 'none' } });
    slide.addText(
      [{ text: c.label + '  ', options: { bold: true, color: CLR.lt1 } }, { text: c.detail, options: { color: CLR.lt2 } }],
      { x: x + 0.25, y: chy, w: chw - 0.5, h: 0.75, fontFace: THEME.bodyFontFace, fontSize: 13, align: 'left', valign: 'middle', margin: 0 }
    );
  });

  slide.addText(
    'This ran on the synthetic validation scene used to test the BAQ/JPEG2000 pipeline (Gaussian sea clutter and 20 injected targets). A real Sentinel-1 scene has not been used yet. An SLC scene over a shipping lane is being acquired for the next iteration.',
    { x: 0.9, y: 6.2, w: 11.3, h: 0.6, fontFace: THEME.bodyFontFace, fontSize: 11, italic: true, color: CLR.accent5, align: 'left', margin: 0 }
  );
}

// ---------- Slide 7: Planned Analysis / Work ----------
{
  const slide = pres.addSlide({ masterName: 'CONTENT' });
  addHeaderIcon(slide, 'planned');
  slide.addText('Planned Analysis & Work', { placeholder: 'title' });

  const milestones = [
    { when: 'Weeks 8–10', what: 'Baseline detector producing real output on raw and compressed scenes, xView3-SAR labels verified, from-scratch CFAR begins, and the codec sweep expands (HEVC, more JPEG2000 points)' },
    { when: 'Week 11', what: 'Rough draft due, including preliminary benchmark results across raw and at least two classical codecs' },
    { when: 'Weeks 12–13', what: 'AIS join engine (H3 index, interpolation, distance and time matching), and CFAR refined against baseline' },
    { when: 'Spring', what: 'LoRA-tuned TerraFM embedding swept across sizes, full benchmark across all representations, serving layer, and final evaluation report' },
  ];
  const mw = 2.68, gap = 0.18, mx0 = 0.9, my = 2.0;
  const lineY = my + 0.22;
  slide.addShape('rect', { x: mx0 + 0.22, y: lineY, w: 3 * (mw + gap) + (mw - 0.44), h: 0.035, fill: { color: CLR.accent4 }, line: { type: 'none' } });
  milestones.forEach((m, i) => {
    const x = mx0 + i * (mw + gap);
    slide.addShape('ellipse', { x: x + 0.07, y: my, w: 0.3, h: 0.3, fill: { color: i === 1 ? CLR.accent2 : CLR.accent1 }, line: { type: 'none' } });
    slide.addText(m.when, { x, y: my + 0.45, w: mw, h: 0.4, fontFace: THEME.headFontFace, fontSize: 14, bold: true, color: CLR.accent3, align: 'left', margin: 0 });
    slide.addText(m.what, { x, y: my + 0.9, w: mw, h: 2.9, fontFace: THEME.bodyFontFace, fontSize: 11.5, color: CLR.dk1, align: 'left', valign: 'top', margin: 0 });
  });

  slide.addText(
    [
      { text: 'As a scope check, ', options: { bold: true, color: CLR.lt1 } },
      { text: 'Fall covers items 1 through 3 (benchmark harness, baseline detector, database) at a preliminary level, while the full sweep, tuned detector, and serving layer are Spring work, per the 40/60 grade split.', options: { color: CLR.lt2 } },
    ],
    { x: 0.9, y: 6.5, w: 11.3, h: 0.65, fill: { color: CLR.dk2 }, fontFace: THEME.bodyFontFace, fontSize: 12, align: 'left', valign: 'middle', margin: 0.1 }
  );
}

(async () => {
  await pres.writeFile({ fileName: path.join(__dirname, 'committee_meeting_deck.pptx') });
  console.log('wrote deck');
})();
