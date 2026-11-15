// Render a small set of react-icons to transparent PNGs so pptxgenjs can
// place them inside colored circles on the slides.
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

const {
  FaSatelliteDish,
  FaBookOpen,
  FaBullseye,
  FaDatabase,
  FaFlask,
  FaChartLine,
  FaRoute,
  FaCheckCircle,
  FaShip,
} = require('react-icons/fa');

const OUT = path.join(__dirname, 'assets');
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });

const ICONS = {
  motivation: FaSatelliteDish,
  whytask: FaShip,
  litreview: FaBookOpen,
  rq: FaBullseye,
  variables: FaDatabase,
  methods: FaFlask,
  prelim: FaChartLine,
  planned: FaRoute,
  check: FaCheckCircle,
};

async function renderOne(name, Comp, colorHex) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(Comp, { color: `#${colorHex}`, size: 256 })
  );
  const fullSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 512 512">${svg.replace(/<svg[^>]*>|<\/svg>/g, '')}</svg>`;
  const outPath = path.join(OUT, `${name}_${colorHex}.png`);
  await sharp(Buffer.from(fullSvg)).resize(256, 256).png().toFile(outPath);
  console.log('wrote', outPath);
}

async function main() {
  // White icons (go inside colored circles) and one navy set (for on-light use)
  for (const [name, Comp] of Object.entries(ICONS)) {
    await renderOne(name, Comp, 'FFFFFF');
  }
}

main();
