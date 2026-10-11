package com.geckolib.cache.model.cuboid;

import com.geckolib.cache.model.GeoBone;
import com.geckolib.cache.model.GeoLocator;
import org.jspecify.annotations.Nullable;

public final class CuboidGeoBone extends GeoBone {
    public final GeoCube[] cubes;

    public CuboidGeoBone(@Nullable GeoBone parent, String name, GeoBone[] children, GeoCube[] cubes, GeoLocator[] locators,
                         float pivotX, float pivotY, float pivotZ, float rotX, float rotY, float rotZ) {
        super(parent, name, children, locators, pivotX, pivotY, pivotZ, rotX, rotY, rotZ);
        this.cubes = cubes;
    }
}
