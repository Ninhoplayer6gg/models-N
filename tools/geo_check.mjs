// Confere o .geo.json (GeckoLib / Minecraft Java) no Blockbench oficial (build web local):
//   1. abre o .bbmodel e pede ao próprio Blockbench a exportação Bedrock (Codecs.bedrock.compile),
//      que é a mesma usada pelo plugin do GeckoLib -> grava blockbench_export.geo.json;
//   2. abre o NOSSO .geo.json como modelo novo (importação Bedrock) e aplica o .png, como faria
//      quem recebe só os arquivos do GeckoLib;
//   3. compara os dois projetos dentro do Blockbench (ossos, pivôs, rotações, cubos, UV, caixa
//      do modelo) e tira as mesmas capturas dos dois para comparação de pixels.
//
// Uso (ver tools/README.md):
//   node tools/geo_check.mjs --bbmodel a.bbmodel --geo a.geo.json --png a.png --out pasta \
//        [--blockbench http://127.0.0.1:8765/index.html] [--playwright /caminho/playwright/index.mjs]

import fs from 'node:fs';
import path from 'node:path';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 ? process.argv[i + 1] : def;
}
const bbPath = arg('bbmodel');
const geoPath = arg('geo');
const pngPath = arg('png');
const outDir = arg('out', 'geo_check');
const bbUrl = arg('blockbench', 'http://127.0.0.1:8765/index.html');
const pwPath = arg('playwright', process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
if (!bbPath || !geoPath || !pngPath) {
  console.error('use --bbmodel arquivo.bbmodel --geo arquivo.geo.json --png textura.png');
  process.exit(2);
}
const { chromium } = await import(pwPath);
fs.mkdirSync(outDir, { recursive: true });
const bbText = fs.readFileSync(bbPath, 'utf8');
const geoText = fs.readFileSync(geoPath, 'utf8');
const pngUrl = 'data:image/png;base64,' + fs.readFileSync(pngPath).toString('base64');

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'],
});
const page = await browser.newPage({ viewport: { width: 1500, height: 1000 } });
const consoleErrors = [];
page.on('pageerror', (e) => consoleErrors.push(String(e && e.message || e)));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
await page.goto(bbUrl, { waitUntil: 'load', timeout: 120000 });
await page.waitForFunction(() => window.Blockbench && window.Codecs && window.Codecs.project && window.Formats, null, { timeout: 120000 });
await page.waitForTimeout(1500);
consoleErrors.splice(0);  // erros de rede do próprio app antes de abrir os modelos
await page.evaluate(() => { if (window.three_grid) three_grid.visible = false; });

// Lê o projeto aberto: ossos, cubos e caixa do modelo no mundo (como o Blockbench vê).
const snapshot = () => page.evaluate(() => {
  const box = new THREE.Box3();
  Cube.all.forEach((c) => { if (c.mesh) box.expandByObject(c.mesh); });
  const groups = Group.all.map((g) => ({ name: g.name, parent: g.parent && g.parent.name ? g.parent.name : null,
    origin: g.origin.slice(), rotation: g.rotation.slice() }));
  const cubes = Cube.all.map((c) => ({ group: c.parent && c.parent.name ? c.parent.name : null, from: c.from.slice(),
    to: c.to.slice(), origin: c.origin.slice(), rotation: c.rotation.slice(), uv_offset: c.uv_offset.slice(),
    mirror_uv: !!c.mirror_uv, inflate: c.inflate || 0,
    faces: Object.fromEntries(Object.entries(c.faces).map(([k, f]) => [k, f.uv.slice()])) }));
  const tex = Texture.all[0];
  Validator.validate();
  return { format: Format.id, box_uv: Project.box_uv, texture_size: [Project.texture_width, Project.texture_height],
    identifier: Project.model_identifier, groups, cubes, world_box: { min: box.min.toArray(), max: box.max.toArray() },
    texture: tex ? { width: tex.width, height: tex.height, loaded: !!(tex.img && tex.img.complete && tex.img.naturalWidth) } : null,
    validator_warnings: Validator.warnings.map((w) => w.message), validator_errors: Validator.errors.map((e) => e.message) };
});

async function shots(prefix, center, radius, ext) {
  const views = [
    { id: 'perspectiva', dir: [0.75, 0.5, -0.9], ortho: false },
    { id: 'lado_direito', dir: [1, 0, 0], ortho: true, span: Math.max(ext[2], ext[1]) },
    { id: 'frente', dir: [0, 0, -1], ortho: true, span: Math.max(ext[0], ext[1]) },
    { id: 'traseira', dir: [-0.8, 0.45, 0.9], ortho: false },
  ];
  const files = {};
  for (const v of views) {
    const dataUrl = await page.evaluate(({ v, center, radius }) => {
      const p = Preview.selected;
      const n = Math.hypot(...v.dir);
      const d = v.dir.map((x) => x / n);
      if (v.ortho) {
        const pos = [center[0] + d[0] * 400, center[1] + d[1] * 400, center[2] + d[2] * 400];
        p.loadAnglePreset({ projection: 'orthographic', position: pos, target: center.slice() });
        p.camera.zoom = (p.width / 40) / (v.span * 1.15);
        p.camera.updateProjectionMatrix();
      } else {
        const dist = radius / Math.sin((45 / 2) * Math.PI / 180) * 1.05;
        p.loadAnglePreset({ projection: 'perspective', position: [center[0] + d[0] * dist, center[1] + d[1] * dist, center[2] + d[2] * dist],
          target: center.slice(), fov: 45 });
      }
      p.render();
      return p.canvas.toDataURL('image/png');
    }, { v, center, radius });
    const file = path.join(outDir, `${prefix}_${v.id}.png`);
    fs.writeFileSync(file, Buffer.from(dataUrl.split(',')[1], 'base64'));
    files[v.id] = file;
  }
  return files;
}

// 1. projeto original + exportação do próprio Blockbench
const original = await page.evaluate(async ({ bbText, name }) => {
  Codecs.project.load(JSON.parse(bbText), { path: name, name });
  await new Promise((r) => setTimeout(r, 2500));
  return { bedrock: Codecs.bedrock.compile() };
}, { bbText, name: path.basename(bbPath) });
fs.writeFileSync(path.join(outDir, 'blockbench_export.geo.json'), original.bedrock);
const snapA = await snapshot();
const lo = snapA.world_box.min, hi = snapA.world_box.max;
const center = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
const ext = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]];
const radius = Math.hypot(...ext) / 2;
const shotsA = await shots('projeto', center, radius, ext);

// 2. só o .geo.json + .png (importação Bedrock em um projeto novo)
const loadErrors = consoleErrors.splice(0);
await page.evaluate(async ({ geoText, name, pngUrl }) => {
  Codecs.bedrock.load(JSON.parse(geoText), { path: 'models/entity/' + name });
  const tex = new Texture({ name: name.replace(/\.geo\.json$/, '.png') }).fromDataURL(pngUrl).add(false);
  for (let i = 0; i < 50 && !(tex.img && tex.img.complete && tex.img.naturalWidth); i++) {
    await new Promise((r) => setTimeout(r, 100));
  }
  Cube.all.forEach((c) => c.applyTexture(tex, true));
  Canvas.updateAll();
  await new Promise((r) => setTimeout(r, 1500));
}, { geoText, name: path.basename(geoPath), pngUrl });
const snapB = await snapshot();
await page.evaluate(() => { if (window.three_grid) three_grid.visible = false; });
const shotsB = await shots('geo', center, radius, ext);
const geoReexport = await page.evaluate(() => Codecs.bedrock.compile());

// 3. comparação dentro do Blockbench
const diffs = [];
const key = (g) => g.name;
const gA = Object.fromEntries(snapA.groups.map((g) => [key(g), g]));
const gB = Object.fromEntries(snapB.groups.map((g) => [key(g), g]));
const close = (a, b) => a.length === b.length && a.every((x, i) => Math.abs(x - b[i]) < 1e-6);
for (const [name, g] of Object.entries(gA)) {
  const h = gB[name];
  if (!h) { diffs.push(`osso ausente no .geo.json: ${name}`); continue; }
  if (g.parent !== h.parent) diffs.push(`osso ${name}: pai ${g.parent} x ${h.parent}`);
  if (!close(g.origin, h.origin)) diffs.push(`osso ${name}: pivô ${g.origin} x ${h.origin}`);
  if (!close(g.rotation, h.rotation)) diffs.push(`osso ${name}: rotação ${g.rotation} x ${h.rotation}`);
}
if (snapA.groups.length !== snapB.groups.length) diffs.push(`ossos: ${snapA.groups.length} x ${snapB.groups.length}`);
const sig = (c) => JSON.stringify([c.group, c.from, c.to, c.uv_offset, c.mirror_uv, c.inflate,
  c.rotation.every((r) => r === 0) ? null : [c.origin, c.rotation]]);
const sA = snapA.cubes.map(sig).sort();
const sB = snapB.cubes.map(sig).sort();
if (JSON.stringify(sA) !== JSON.stringify(sB)) {
  const setB = new Set(sB);
  diffs.push(`cubos diferentes: ${sA.filter((s) => !setB.has(s)).slice(0, 5).join(' | ')}`);
}
const faceSig = (c) => JSON.stringify([c.group, c.from, c.to, c.faces]);
const fA = snapA.cubes.map(faceSig).sort();
const fB = snapB.cubes.map(faceSig).sort();
if (JSON.stringify(fA) !== JSON.stringify(fB)) diffs.push('UV das faces diferente após importar o .geo.json');
if (!close(snapA.world_box.min, snapB.world_box.min) || !close(snapA.world_box.max, snapB.world_box.max)) {
  diffs.push(`caixa do modelo: ${JSON.stringify(snapA.world_box)} x ${JSON.stringify(snapB.world_box)}`);
}

const report = {
  bbmodel: bbPath,
  geo: geoPath,
  blockbench_version: await page.evaluate(() => Blockbench.version),
  export_identical_to_ours: original.bedrock === geoText,
  reexport_identical_to_ours: geoReexport === geoText,
  project: { format: snapA.format, cubes: snapA.cubes.length, groups: snapA.groups.length, texture: snapA.texture,
    validator_warnings: snapA.validator_warnings, validator_errors: snapA.validator_errors },
  geo_import: { format: snapB.format, box_uv: snapB.box_uv, texture_size: snapB.texture_size, identifier: snapB.identifier,
    cubes: snapB.cubes.length, groups: snapB.groups.length, texture: snapB.texture,
    validator_warnings: snapB.validator_warnings, validator_errors: snapB.validator_errors },
  differences: diffs,
  console_errors: [...loadErrors, ...consoleErrors],
  screenshots: { projeto: shotsA, geo: shotsB },
};
fs.writeFileSync(path.join(outDir, 'geo_report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ export_identical_to_ours: report.export_identical_to_ours,
  reexport_identical_to_ours: report.reexport_identical_to_ours, differences: diffs,
  geo_import: { format: snapB.format, cubes: snapB.cubes.length, groups: snapB.groups.length, texture: snapB.texture,
    validator_errors: snapB.validator_errors }, console_errors: report.console_errors }, null, 2));
await browser.close();
