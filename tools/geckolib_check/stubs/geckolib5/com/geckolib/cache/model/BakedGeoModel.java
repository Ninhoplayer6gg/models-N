package com.geckolib.cache.model;

import java.util.Map;

public record BakedGeoModel(GeoBone[] topLevelBones, Map<String, GeoLocator> locators, ModelProperties properties) {}
