import com.google.gson.*;
import software.bernie.geckolib.GeckoLibConstants;
import software.bernie.geckolib.cache.object.BakedGeoModel;
import software.bernie.geckolib.cache.object.GeoBone;
import software.bernie.geckolib.cache.object.GeoCube;
import software.bernie.geckolib.cache.object.GeoQuad;
import software.bernie.geckolib.cache.object.GeoVertex;
import software.bernie.geckolib.loading.json.raw.*;
import software.bernie.geckolib.loading.object.BakedModelFactory;
import software.bernie.geckolib.loading.object.GeometryTree;

import java.nio.file.Files;
import java.nio.file.Path;

// Carrega cada .geo.json com o código do GeckoLib 4, repetindo os passos de GeckoLibCache.loadModels
// (FileLoader.loadModelFile + conferência da versão + BakedModelFactory), e grava o modelo "assado" em JSON.
public class GeckoLib4LoadCheck {
    // Mesmos adaptadores de geometria de KeyFramesAdapter.GEO_GSON (os de animação não entram na leitura do modelo).
    static final Gson GEO_GSON = new GsonBuilder().setLenient()
            .registerTypeAdapter(Bone.class, Bone.deserializer())
            .registerTypeAdapter(Cube.class, Cube.deserializer())
            .registerTypeAdapter(FaceUV.class, FaceUV.deserializer())
            .registerTypeAdapter(LocatorClass.class, LocatorClass.deserializer())
            .registerTypeAdapter(LocatorValue.class, LocatorValue.deserializer())
            .registerTypeAdapter(MinecraftGeometry.class, MinecraftGeometry.deserializer())
            .registerTypeAdapter(Model.class, Model.deserializer())
            .registerTypeAdapter(ModelProperties.class, ModelProperties.deserializer())
            .registerTypeAdapter(PolyMesh.class, PolyMesh.deserializer())
            .registerTypeAdapter(PolysUnion.class, PolysUnion.deserializer())
            .registerTypeAdapter(TextureMesh.class, TextureMesh.deserializer())
            .registerTypeAdapter(UVFaces.class, UVFaces.deserializer())
            .registerTypeAdapter(UVUnion.class, UVUnion.deserializer())
            .create();

    public static void main(String[] args) throws Exception {
        JsonArray out = new JsonArray();
        for (String file : args) {
            JsonObject entry = new JsonObject();
            entry.addProperty("file", file);
            GeckoLibConstants.LOGGER.messages.clear();
            try {
                String resource = "ninho:geo/entity/" + Path.of(file).getFileName();
                Model model = GEO_GSON.fromJson(Files.readString(Path.of(file)), Model.class);
                // --- mesma conferência de versão de GeckoLibCache.loadModels ---
                switch (model.formatVersion()) {
                    case V_1_12_0 -> {}
                    case V_1_14_0 -> GeckoLibConstants.LOGGER.warn("Unsupported geometry json version: 1.14.0 for model {}. This model may not appear as expected", resource);
                    case V_1_21_0 -> GeckoLibConstants.LOGGER.warn("Unsupported geometry json version: 1.21.0 for model {}. Supported versions: 1.12.0. Remove any rotated face UVs and re-export the model to fix", resource);
                    case null, default -> GeckoLibConstants.LOGGER.warn("Unsupported geometry json version for model {}. Supported versions: 1.12.0", resource);
                }
                BakedGeoModel baked = BakedModelFactory.getForNamespace("ninho").constructGeoModel(GeometryTree.fromModel(model));
                entry.addProperty("ok", true);
                entry.addProperty("format_version", String.valueOf(model.formatVersion()));
                entry.addProperty("format_version_supported", model.formatVersion() != null && model.formatVersion().name().equals("V_1_12_0"));
                entry.addProperty("texture_width", baked.properties().textureWidth());
                entry.addProperty("texture_height", baked.properties().textureHeight());
                JsonArray bones = new JsonArray();
                for (GeoBone bone : baked.topLevelBones()) dump(bone, bones);
                entry.add("bones", bones);
            } catch (Exception ex) {
                entry.addProperty("ok", false);
                entry.addProperty("error", ex.toString());
            }
            JsonArray log = new JsonArray();
            GeckoLibConstants.LOGGER.messages.forEach(log::add);
            entry.add("log", log);
            out.add(entry);
        }
        System.out.println(new GsonBuilder().create().toJson(out));
    }

    private static void dump(GeoBone bone, JsonArray into) {
        JsonObject b = new JsonObject();
        b.addProperty("name", bone.getName());
        b.addProperty("parent", bone.getParent() == null ? null : bone.getParent().getName());
        b.add("pivot", arr(bone.getPivotX(), bone.getPivotY(), bone.getPivotZ()));
        b.add("rotation_rad", arr(bone.getRotX(), bone.getRotY(), bone.getRotZ()));
        JsonArray cubes = new JsonArray();
        for (GeoCube cube : bone.getCubes()) {
            JsonObject c = new JsonObject();
            c.add("pivot", arr(cube.pivot().x, cube.pivot().y, cube.pivot().z));
            c.add("rotation_rad", arr(cube.rotation().x, cube.rotation().y, cube.rotation().z));
            c.add("size", arr(cube.size().x, cube.size().y, cube.size().z));
            JsonArray quads = new JsonArray();
            for (GeoQuad quad : cube.quads()) {
                if (quad == null) continue;
                JsonObject q = new JsonObject();
                q.addProperty("direction", quad.direction().getName());
                q.add("normal", arr(quad.normal().x(), quad.normal().y(), quad.normal().z()));
                JsonArray verts = new JsonArray();
                for (GeoVertex v : quad.vertices())
                    verts.add(arr(v.position().x(), v.position().y(), v.position().z(), v.texU(), v.texV()));
                q.add("vertices", verts);
                quads.add(q);
            }
            c.add("quads", quads);
            cubes.add(c);
        }
        b.add("cubes", cubes);
        into.add(b);
        for (GeoBone child : bone.getChildBones()) dump(child, into);
    }

    private static JsonArray arr(double... values) {
        JsonArray a = new JsonArray();
        for (double v : values) a.add(v);
        return a;
    }
}
