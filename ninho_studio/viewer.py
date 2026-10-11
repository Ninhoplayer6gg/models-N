"""Visualizador 3D interativo (HTML + WebGL puro, sem bibliotecas externas).

Pensado para o celular: arraste com um dedo para girar, use dois dedos para
aproximar e toque duas vezes para voltar à vista inicial. Funciona dentro da
saída do Colab e também como arquivo .html aberto direto no navegador
(não depende de internet nem de CDN).
"""

from __future__ import annotations

import base64
import html
import json
from typing import Optional

import numpy as np

from .mesh import Mesh

_TEMPLATE = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  .nms-wrap { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; max-width: 720px; margin: 0 auto; color: #1d232a; }
  .nms-wrap canvas { width: 100%; height: min(60vh, 480px); display: block; touch-action: none; border-radius: 12px;
    background: linear-gradient(#dfe8ee, #f4f6f2); }
  .nms-bar { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
  .nms-bar button { flex: 1 1 auto; min-width: 72px; min-height: 44px; font-size: 16px; border: 0; border-radius: 10px;
    background: #2f6b3a; color: #fff; padding: 8px 12px; }
  .nms-bar button.off { background: #8a948d; }
  .nms-note { font-size: 13px; color: #4a5560; margin: 4px 0 0; }
  .nms-err { padding: 12px; background: #fde8e8; border-radius: 10px; display: none; }
</style>
</head>
<body>
<div class="nms-wrap" id="__ID__">
  <canvas></canvas>
  <div class="nms-err"></div>
  <div class="nms-bar">
    <button data-view="persp">3/4</button>
    <button data-view="front">Frente</button>
    <button data-view="side">Lado</button>
    <button data-view="top">Topo</button>
    <button data-action="spin" class="off">Girar</button>
    <button data-action="bones" class="off">Ossos</button>
  </div>
  <p class="nms-note">__NOTE__</p>
</div>
<script>
(function () {
  "use strict";
  var root = document.getElementById("__ID__");
  var canvas = root.querySelector("canvas");
  var errBox = root.querySelector(".nms-err");
  function fail(msg) { errBox.style.display = "block"; errBox.textContent = msg; canvas.style.display = "none"; }
  var gl = canvas.getContext("webgl", { antialias: true, alpha: true }) || canvas.getContext("experimental-webgl");
  if (!gl) { fail("Seu navegador não abriu o WebGL. Use as imagens estáticas (frente, lado, topo e perspectiva)."); return; }

  function f32(b64) {
    var bin = atob(b64), len = bin.length, bytes = new Uint8Array(len);
    for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
    return new Float32Array(bytes.buffer);
  }
  var DATA = __DATA__;
  var pos = f32(DATA.positions), uv = f32(DATA.uvs), nrm = f32(DATA.normals);
  var count = pos.length / 3;

  function shader(type, src) {
    var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    return s;
  }
  function program(vs, fs) {
    var p = gl.createProgram();
    gl.attachShader(p, shader(gl.VERTEX_SHADER, vs)); gl.attachShader(p, shader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }
  var meshProg, lineProg;
  try {
    meshProg = program(
      "attribute vec3 aPos; attribute vec2 aUV; attribute vec3 aN; uniform mat4 uMVP; varying vec2 vUV; varying float vL;" +
      "void main(){ vUV=aUV; vec3 L1=normalize(vec3(0.45,1.0,-0.6)); vec3 L2=normalize(vec3(-0.6,0.3,0.7));" +
      "vL=min(1.0, 0.58+0.42*max(dot(aN,L1),0.0)+0.12*max(dot(aN,L2),0.0)); gl_Position=uMVP*vec4(aPos,1.0);}",
      "precision mediump float; uniform sampler2D uTex; varying vec2 vUV; varying float vL;" +
      "void main(){ vec4 c=texture2D(uTex,vUV); if(c.a<0.5) discard; gl_FragColor=vec4(c.rgb*vL,1.0);}");
    lineProg = program(
      "attribute vec3 aPos; uniform mat4 uMVP; uniform float uSize; void main(){ gl_Position=uMVP*vec4(aPos,1.0); gl_PointSize=uSize; }",
      "precision mediump float; uniform vec4 uColor; void main(){ gl_FragColor=uColor; }");
  } catch (e) { fail("Erro no WebGL: " + e.message); return; }

  function buffer(arr) { var b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, arr, gl.STATIC_DRAW); return b; }
  var bPos = buffer(pos), bUV = buffer(uv), bN = buffer(nrm);

  // grade do chão (1 bloco = 16 px) e ossos
  var lo = DATA.bounds[0], hi = DATA.bounds[1];
  var grid = [], g0x = Math.floor(lo[0] / 16) * 16 - 16, g1x = Math.ceil(hi[0] / 16) * 16 + 16;
  var g0z = Math.floor(lo[2] / 16) * 16 - 16, g1z = Math.ceil(hi[2] / 16) * 16 + 16;
  for (var x = g0x; x <= g1x; x += 16) grid.push(x, 0, g0z, x, 0, g1z);
  for (var z = g0z; z <= g1z; z += 16) grid.push(g0x, 0, z, g1x, 0, z);
  var bGrid = buffer(new Float32Array(grid)), gridCount = grid.length / 3;
  var boneLines = [], bonePts = [];
  DATA.bones.forEach(function (b) {
    bonePts.push(b.p[0], b.p[1], b.p[2]);
    if (b.parent) { boneLines.push(b.parent[0], b.parent[1], b.parent[2], b.p[0], b.p[1], b.p[2]); }
  });
  var bBoneL = buffer(new Float32Array(boneLines)), bBoneP = buffer(new Float32Array(bonePts));

  var tex = gl.createTexture();
  var img = new Image();
  img.onload = function () {
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    ready = true; draw();
  };
  img.src = DATA.texture;
  var ready = false;

  // matemática de matrizes (coluna-maior, como o WebGL espera)
  function mul(a, b) { var o = new Float32Array(16);
    for (var c = 0; c < 4; c++) for (var r = 0; r < 4; r++) {
      o[c * 4 + r] = a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] + a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3]; }
    return o; }
  function persp(fovy, aspect, near, far) { var f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]); }
  function lookAt(e, c, u) {
    var zx = e[0] - c[0], zy = e[1] - c[1], zz = e[2] - c[2], l = Math.hypot(zx, zy, zz); zx /= l; zy /= l; zz /= l;
    var xx = u[1] * zz - u[2] * zy, xy = u[2] * zx - u[0] * zz, xz = u[0] * zy - u[1] * zx; l = Math.hypot(xx, xy, xz); xx /= l; xy /= l; xz /= l;
    var yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
    return new Float32Array([xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0,
      -(xx * e[0] + xy * e[1] + xz * e[2]), -(yx * e[0] + yy * e[1] + yz * e[2]), -(zx * e[0] + zy * e[1] + zz * e[2]), 1]); }

  var center = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2];
  var radius = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
  var VIEWS = { persp: [-0.88, 0.42], front: [-Math.PI / 2, 0.0], side: [0.0, 0.0], top: [0.0, 1.55] };
  var yaw = VIEWS.persp[0], pitch = VIEWS.persp[1], zoom = 1.0, spin = false, showBones = false;

  function draw() {
    if (!ready) return;
    var dpr = window.devicePixelRatio || 1;
    var w = Math.max(1, Math.round(canvas.clientWidth * dpr)), h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    var dist = radius / Math.sin(0.30) * 1.1 / zoom;
    var eye = [center[0] + dist * Math.cos(pitch) * Math.cos(yaw), center[1] + dist * Math.sin(pitch), center[2] + dist * Math.cos(pitch) * Math.sin(yaw)];
    var up = Math.abs(pitch) > 1.5 ? [-1, 0, 0] : [0, 1, 0];
    var mvp = mul(persp(0.6, w / h, dist * 0.05, dist * 4 + radius * 4), lookAt(eye, center, up));

    gl.enable(gl.DEPTH_TEST);
    gl.useProgram(lineProg);
    var lp = gl.getAttribLocation(lineProg, "aPos");
    gl.uniformMatrix4fv(gl.getUniformLocation(lineProg, "uMVP"), false, mvp);
    gl.uniform1f(gl.getUniformLocation(lineProg, "uSize"), 1.0);
    gl.uniform4f(gl.getUniformLocation(lineProg, "uColor"), 0.55, 0.62, 0.66, 1.0);
    gl.bindBuffer(gl.ARRAY_BUFFER, bGrid); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.LINES, 0, gridCount);

    gl.useProgram(meshProg);
    gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); gl.frontFace(gl.CCW);
    gl.uniformMatrix4fv(gl.getUniformLocation(meshProg, "uMVP"), false, mvp);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.uniform1i(gl.getUniformLocation(meshProg, "uTex"), 0);
    [["aPos", bPos, 3], ["aUV", bUV, 2], ["aN", bN, 3]].forEach(function (a) {
      var loc = gl.getAttribLocation(meshProg, a[0]); gl.bindBuffer(gl.ARRAY_BUFFER, a[1]);
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, a[2], gl.FLOAT, false, 0, 0); });
    gl.drawArrays(gl.TRIANGLES, 0, count);
    gl.disable(gl.CULL_FACE);
    [["aUV"], ["aN"]].forEach(function (a) { gl.disableVertexAttribArray(gl.getAttribLocation(meshProg, a[0])); });

    if (showBones) {
      gl.disable(gl.DEPTH_TEST);
      gl.useProgram(lineProg);
      gl.uniformMatrix4fv(gl.getUniformLocation(lineProg, "uMVP"), false, mvp);
      gl.uniform4f(gl.getUniformLocation(lineProg, "uColor"), 0.12, 0.35, 0.85, 1.0);
      gl.bindBuffer(gl.ARRAY_BUFFER, bBoneL); gl.enableVertexAttribArray(lp); gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, boneLines.length / 3);
      gl.uniform4f(gl.getUniformLocation(lineProg, "uColor"), 0.86, 0.16, 0.16, 1.0);
      gl.uniform1f(gl.getUniformLocation(lineProg, "uSize"), 7.0 * dpr);
      gl.bindBuffer(gl.ARRAY_BUFFER, bBoneP); gl.vertexAttribPointer(lp, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.POINTS, 0, bonePts.length / 3);
    }
  }

  // toque e mouse
  var pointers = {}, lastDist = 0, lastTap = 0;
  canvas.addEventListener("pointerdown", function (e) { canvas.setPointerCapture(e.pointerId); pointers[e.pointerId] = [e.clientX, e.clientY];
    var now = Date.now(), single = Object.keys(pointers).length === 1;
    if (single && now - lastTap < 300) { yaw = VIEWS.persp[0]; pitch = VIEWS.persp[1]; zoom = 1; draw(); }
    if (single) lastTap = now; });
  canvas.addEventListener("pointermove", function (e) {
    if (!pointers[e.pointerId]) return;
    var ids = Object.keys(pointers);
    if (ids.length === 1) {
      var p = pointers[e.pointerId]; yaw += (e.clientX - p[0]) * 0.01;
      pitch = Math.max(-1.55, Math.min(1.55, pitch + (e.clientY - p[1]) * 0.01));
    }
    pointers[e.pointerId] = [e.clientX, e.clientY];
    if (ids.length === 2) {
      var a = pointers[ids[0]], b = pointers[ids[1]], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      if (lastDist) zoom = Math.max(0.4, Math.min(5, zoom * d / lastDist)); lastDist = d;
    }
    draw();
  });
  function up(e) { delete pointers[e.pointerId]; lastDist = 0; }
  canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
  canvas.addEventListener("wheel", function (e) { e.preventDefault(); zoom = Math.max(0.4, Math.min(5, zoom * (e.deltaY < 0 ? 1.1 : 0.9))); draw(); }, { passive: false });
  root.querySelectorAll("button[data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () { var v = VIEWS[btn.getAttribute("data-view")]; yaw = v[0]; pitch = v[1]; zoom = 1; draw(); }); });
  root.querySelector("button[data-action=spin]").addEventListener("click", function () { spin = !spin; this.classList.toggle("off", !spin); if (spin) tick(); });
  root.querySelector("button[data-action=bones]").addEventListener("click", function () { showBones = !showBones; this.classList.toggle("off", !showBones); draw(); });
  function tick() { if (!spin) return; yaw += 0.01; draw(); requestAnimationFrame(tick); }
  window.addEventListener("resize", draw);
  window.__nmsViewer = { draw: draw, setView: function (k) { var v = VIEWS[k]; yaw = v[0]; pitch = v[1]; zoom = 1; draw(); },
    toggleBones: function () { showBones = !showBones; draw(); }, isReady: function () { return ready; } };
})();
</script>
</body>
</html>
"""


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype="<f4").tobytes()).decode("ascii")


def viewer_html(mesh: Mesh, texture_png: bytes, title: str = "Ninho Model Studio", element_id: Optional[str] = None,
                note: Optional[str] = None) -> str:
    """Gera a página HTML do visualizador (auto-contida)."""
    w, h = mesh.uv_size
    # encolhe 1/64 de texel para dentro da face (mesma técnica do Blockbench contra "sangramento")
    uvs = mesh.uvs.copy()
    rects = mesh.uv_rects
    margin = 1.0 / 64.0
    for k in range(3):
        uvs[:, k, 0] = np.clip(uvs[:, k, 0], rects[:, 0] + margin, rects[:, 2] - margin)
        uvs[:, k, 1] = np.clip(uvs[:, k, 1], rects[:, 1] + margin, rects[:, 3] - margin)
    uvs[..., 0] /= float(w)
    uvs[..., 1] /= float(h)
    # vértices em ordem anti-horária vista de fora (para o descarte de faces de trás)
    pos = mesh.positions.copy()
    nrm = np.repeat(mesh.normals[:, None, :], 3, axis=1)
    cross = np.cross(pos[:, 1] - pos[:, 0], pos[:, 2] - pos[:, 0])
    flip = (cross * mesh.normals).sum(axis=1) < 0
    pos[flip] = pos[flip][:, [0, 2, 1]]
    uvs[flip] = uvs[flip][:, [0, 2, 1]]
    lo, hi = mesh.bounds
    bones = []
    for b in mesh.bones.values():
        parent = mesh.bones[b.parent].pivot_world.tolist() if b.parent and b.parent in mesh.bones else None
        bones.append({"name": b.name, "p": [round(float(v), 3) for v in b.pivot_world], "parent": parent})
    data = {
        "positions": _b64(pos.reshape(-1)),
        "uvs": _b64(uvs.reshape(-1)),
        "normals": _b64(nrm.reshape(-1)),
        "bounds": [lo.tolist(), hi.tolist()],
        "bones": bones,
        "texture": "data:image/png;base64," + base64.b64encode(texture_png).decode("ascii"),
    }
    element_id = element_id or "nms-viewer"
    note = note or "Arraste para girar · dois dedos para aproximar · toque duas vezes para voltar"
    return (
        _TEMPLATE.replace("__TITLE__", html.escape(title))
        .replace("__ID__", element_id)
        .replace("__NOTE__", html.escape(note))
        .replace("__DATA__", json.dumps(data))
    )
