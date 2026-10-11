package com.geckolib.cache.model;

public class GeoLocator {
    public final GeoBone parent;
    public final String name;
    public final float offsetX, offsetY, offsetZ, rotX, rotY, rotZ;

    public GeoLocator(GeoBone parent, String name, float offsetX, float offsetY, float offsetZ, float rotX, float rotY, float rotZ) {
        this.parent = parent; this.name = name; this.offsetX = offsetX; this.offsetY = offsetY; this.offsetZ = offsetZ;
        this.rotX = rotX; this.rotY = rotY; this.rotZ = rotZ;
    }
    public String name() { return name; }
}
