package com.geckolib.cache.model;

import org.jspecify.annotations.Nullable;

// Stub: só os dados do osso (o original também guarda estado de animação e renderização).
public abstract class GeoBone {
    public final @Nullable GeoBone parent;
    public final String name;
    public final GeoBone[] children;
    public final GeoLocator[] locators;
    public final float pivotX, pivotY, pivotZ, rotX, rotY, rotZ;

    public GeoBone(@Nullable GeoBone parent, String name, GeoBone[] children, GeoLocator[] locators,
                   float pivotX, float pivotY, float pivotZ, float rotX, float rotY, float rotZ) {
        this.parent = parent; this.name = name; this.children = children; this.locators = locators;
        this.pivotX = pivotX; this.pivotY = pivotY; this.pivotZ = pivotZ; this.rotX = rotX; this.rotY = rotY; this.rotZ = rotZ;
    }
    public String name() { return name; }
    @Override public String toString() { return name; }
}
