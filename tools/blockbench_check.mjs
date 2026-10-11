// Abre um .bbmodel no Blockbench (build web oficial servida localmente) em um
// Chromium sem tela e registra o que o próprio Blockbench vê:
//   * formato/versão carregados, contagem de cubos e grupos, textura carregada;
//   * avisos/erros do validador interno do Blockbench;
//   * capturas do viewport (perspectiva, lado, frente, topo, traseira);
//   * reexportação como .bbmodel (ida e volta) e exportação Bedrock (.geo.json);
//   * visible_box calculado pelo Blockbench.
//
// Uso (ver tools/README.md):
//   node tools/blockbench_check.mjs --model exemplos/x.bbmodel --out pasta \
//        [--blockbench http://127.0.0.1:8765/index.html] [--playwright /caminho/playwright/index.mjs]

import fs from 'node:fs';
import path from 'node:path';

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 ? process.argv[i + 1] : def;
}
const modelPath = arg('model');
const outDir = arg('out', 'blockbench_check');
const bbUrl = arg('blockbench', 'http://127.0.0.1:8765/index.html');
const pwPath = arg('playwright', process.env.PLAYWRIGHT_MODULE || '/opt/node22/lib/node_modules/playwright/index.mjs');
if (!modelPath) {
  console.error('use --model arquivo.bbmodel');
  process.exit(2);
}
const { chromium } = await import(pwPath);
fs.mkdirSync(outDir, { recursive: true });
const text = fs.readFileSync(modelPath, 'utf8');
const fileName = path.basename(modelPath);

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
const bootErrors = consoleErrors.splice(0);  // erros de rede do próprio app (plugins/CDN) antes de abrir o modelo

const info = await page.evaluate(async ({ text, fileName }) => {
  const messageBoxes = [];
  const original = Blockbench.showMessageBox;
  Blockbench.showMessageBox = function (opts, cb) { messageBoxes.push(JSON.stringify(opts).slice(0, 300)); return original.call(this, opts, cb); };
  const json = JSON.parse(text);
  Codecs.project.load(json, { path: fileName, name: fileName });
  await new Promise((r) => setTimeout(r, 2500));
  Validator.validate();
  await new Promise((r) => setTimeout(r, 500));
  const tex = Texture.all[0];
  const box = new THREE.Box3();
  Cube.all.forEach((c) => { if (c.mesh) box.expandByObject(c.mesh); });
  const groups = Group.all.map((g) => ({ name: g.name, origin: g.origin.slice(), rotation: g.rotation.slice(),
    parent: g.parent && g.parent.name ? g.parent.name : null, children: g.children.length }));
  return {
    blockbench_version: Blockbench.version,
    format: Format.id,
    format_name: Format.name,
    box_uv: Project.box_uv,
    texture_size: [Project.texture_width, Project.texture_height],
    model_identifier: Project.model_identifier,
    cubes: Cube.all.length,
    groups: Group.all.length,
    root_nodes: Outliner.root.length,
    texture: tex ? { name: tex.name, width: tex.width, height: tex.height, uv_width: tex.uv_width, uv_height: tex.uv_height,
      loaded: !!(tex.img && tex.img.complete && tex.img.naturalWidth), error: tex.error || 0 } : null,
    validator_warnings: Validator.warnings.map((w) => w.message),
    validator_errors: Validator.errors.map((e) => e.message),
    message_boxes: messageBoxes,
    world_box: { min: box.min.toArray(), max: box.max.toArray() },
    group_list: groups,
  };
}, { text, fileName });

// capturas do viewport
const lo = info.world_box.min, hi = info.world_box.max;
const center = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
const ext = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]];
const radius = Math.hypot(...ext) / 2;
const views = [
  { id: 'perspectiva', dir: [0.75, 0.5, -0.9], ortho: false },
  { id: 'lado_direito', dir: [1, 0, 0], ortho: true, span: Math.max(ext[2], ext[1]) },
  { id: 'frente', dir: [0, 0, -1], ortho: true, span: Math.max(ext[0], ext[1]) },
  { id: 'topo', dir: [0, 1, 0], ortho: true, span: Math.max(ext[0], ext[2]) },
  { id: 'traseira', dir: [-0.8, 0.45, 0.9], ortho: false },
];
const shots = {};
const hideGrid = arg('hide-grid', '1') === '1';
await page.evaluate((hide) => { if (hide && window.three_grid) three_grid.visible = false; }, hideGrid);
for (const v of views) {
  const dataUrl = await page.evaluate(({ v, center, radius }) => {
    const p = Preview.selected;
    const n = Math.hypot(...v.dir);
    const d = v.dir.map((x) => x / n);
    if (v.ortho) {
      const dist = 400;
      const pos = [center[0] + d[0] * dist, center[1] + d[1] * dist, center[2] + d[2] * dist];
      if (v.id === 'topo') pos[0] += 0.001;
      p.loadAnglePreset({ projection: 'orthographic', position: pos, target: center.slice() });
      const zoom = (p.width / 40) / (v.span * 1.15);
      p.camera.zoom = zoom;
      p.camera.updateProjectionMatrix();
    } else {
      const fov = 45;
      const dist = radius / Math.sin((fov / 2) * Math.PI / 180) * 1.05;
      const pos = [center[0] + d[0] * dist, center[1] + d[1] * dist, center[2] + d[2] * dist];
      p.loadAnglePreset({ projection: 'perspective', position: pos, target: center.slice(), fov });
    }
    p.render();
    return p.canvas.toDataURL('image/png');
  }, { v, center, radius });
  const file = path.join(outDir, `bb_${v.id}.png`);
  fs.writeFileSync(file, Buffer.from(dataUrl.split(',')[1], 'base64'));
  shots[v.id] = file;
}

// ida e volta + exportação Bedrock + visible box
const extra = await page.evaluate(() => {
  const resaved = Codecs.project.compile({ raw: true, bitmaps: true });
  const bedrock = Codecs.bedrock.compile();
  const before = Project.visible_box.slice();
  let vb = null;
  try { vb = calculateVisibleBox().slice(); } catch (e) { vb = String(e); }
  return { resaved, bedrock, visible_box_file: before, visible_box_calc: vb };
});
fs.writeFileSync(path.join(outDir, 'bb_resaved.bbmodel'), JSON.stringify(extra.resaved, null, '\t'));
const geoName = (info.model_identifier || 'modelo') + '.geo.json';
fs.writeFileSync(path.join(outDir, geoName), extra.bedrock);
let bedrockSummary = null;
try {
  const geo = JSON.parse(extra.bedrock);
  const g = geo['minecraft:geometry'][0];
  bedrockSummary = { format_version: geo.format_version, identifier: g.description.identifier,
    texture_width: g.description.texture_width, texture_height: g.description.texture_height,
    bones: g.bones.length, cubes: g.bones.reduce((a, b) => a + (b.cubes ? b.cubes.length : 0), 0) };
} catch (e) { bedrockSummary = { error: String(e) }; }

// comparação de ida e volta (campos estruturais)
const original = JSON.parse(text);
function pick(el) { return JSON.stringify({ from: el.from, to: el.to, origin: el.origin, rotation: el.rotation || [0, 0, 0],
  uv_offset: el.uv_offset || [0, 0], faces: Object.fromEntries(Object.entries(el.faces).map(([k, f]) => [k, { uv: f.uv, texture: f.texture }])) }); }
function pickG(g) { return JSON.stringify({ name: g.name, origin: g.origin, rotation: g.rotation }); }
const diffs = [];
const resEl = Object.fromEntries(extra.resaved.elements.map((e) => [e.uuid, e]));
for (const el of original.elements) {
  const r = resEl[el.uuid];
  if (!r) { diffs.push(`cubo ausente após reabrir: ${el.name}`); continue; }
  if (pick(el) !== pick(r)) diffs.push(`cubo diferente após reabrir: ${el.name}`);
}
const resG = Object.fromEntries(extra.resaved.groups.map((g) => [g.uuid, g]));
for (const g of original.groups) {
  const r = resG[g.uuid];
  if (!r) { diffs.push(`grupo ausente após reabrir: ${g.name}`); continue; }
  if (pickG(g) !== pickG(r)) diffs.push(`grupo diferente após reabrir: ${g.name}`);
}
if (JSON.stringify(original.outliner) !== JSON.stringify(extra.resaved.outliner.map(function strip(n) {
  return typeof n === 'string' ? n : { uuid: n.uuid, isOpen: n.isOpen, children: n.children.map(strip) }; }))) {
  diffs.push('hierarquia (outliner) diferente após reabrir');
}

const report = {
  model: modelPath,
  blockbench_url: bbUrl,
  ...info,
  console_errors_after_load: consoleErrors,
  boot_errors_ignored: bootErrors.length,
  screenshots: shots,
  roundtrip_differences: diffs,
  bedrock_export: bedrockSummary,
  visible_box_file: extra.visible_box_file,
  visible_box_blockbench: extra.visible_box_calc,
};
fs.writeFileSync(path.join(outDir, 'blockbench_report.json'), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ format: report.format, cubes: report.cubes, groups: report.groups, texture: report.texture,
  validator_warnings: report.validator_warnings, validator_errors: report.validator_errors, message_boxes: report.message_boxes,
  console_errors_after_load: report.console_errors_after_load, roundtrip_differences: diffs, bedrock_export: bedrockSummary,
  visible_box_file: report.visible_box_file, visible_box_blockbench: report.visible_box_blockbench }, null, 2));
await browser.close();
