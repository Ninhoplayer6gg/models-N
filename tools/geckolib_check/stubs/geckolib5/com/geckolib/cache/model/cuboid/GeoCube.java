package com.geckolib.cache.model.cuboid;

import com.geckolib.cache.model.GeoQuad;
import net.minecraft.world.phys.Vec3;
import org.jspecify.annotations.Nullable;

// Stub com os mesmos componentes do GeoCube original (sem os métodos de renderização).
public record GeoCube(@Nullable GeoQuad[] quads, Vec3 pivot, Vec3 rotation, Vec3 size, boolean hasRotation) {
    public GeoCube(@Nullable GeoQuad[] quads, Vec3 pivot, Vec3 rotation, Vec3 size) {
        this(quads, pivot, rotation, size, rotation.x != 0 || rotation.y != 0 || rotation.z != 0);
    }
}
