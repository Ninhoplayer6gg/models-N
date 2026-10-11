package com.mojang.blaze3d.vertex;

// Só para compilar GeoQuad.render (não é chamado neste teste).
public interface VertexConsumer {
    void addVertex(float x, float y, float z, int color, float u, float v, int overlay, int light, float nx, float ny, float nz);
}
