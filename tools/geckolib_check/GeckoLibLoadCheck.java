import com.geckolib.GeckoLibConstants;
import com.geckolib.cache.model.BakedGeoModel;
import com.geckolib.cache.model.GeoBone;
import com.geckolib.cache.model.GeoQuad;
import com.geckolib.cache.model.GeoVertex;
import com.geckolib.cache.model.cuboid.CuboidGeoBone;
import com.geckolib.cache.model.cuboid.GeoCube;
import com.geckolib.loading.definition.geometry.Geometry;
import com.geckolib.loading.definition.geometry.object.ModelFormatVersion;
import com.google.gson.*;
import net.minecraft.resources.Identifier;
import net.minecraft.util.GsonHelper;

import java.nio.file.Files;
import java.nio.file.Path;

// Carrega cada .geo.json com o código do GeckoLib 5 (Geometry.GSON + bake), repetindo os passos de
// GeckoLibGsonLoader.deserializeJsonModel/bakeGeckoLibModelFile, e grava o modelo "assado" em JSON.
public class GeckoLibLoadCheck {
    public static void main(String[] args) throws Exception {
        JsonArray out = new JsonArray();
        for (String file : args) {
            JsonObject entry = new JsonObject();
            entry.addProperty("file", file);
            GeckoLibConstants.LOGGER.messages.clear();
            try {
                Identifier resourcePath = Identifier.fromNamespaceAndPath("ninho", "entity/" + Path.of(file).getFileName().toString().replace(".geo.json", ""));
                JsonObject json = JsonParser.parseString(Files.readString(Path.of(file))).getAsJsonObject();
                // --- mesmos passos de GeckoLibGsonLoader.deserializeJsonModel ---
                final Geometry geometry = Geometry.GSON.fromJson(json, Geometry.class);
                final ModelFormatVersion matchedVersion = ModelFormatVersion.match(geometry.formatVersion());
                if (matchedVersion == null)
                    GeckoLibConstants.LOGGER.warn("{}: Unknown geo model format version: '{}'. This may not work correctly", resourcePath, geometry.formatVersion());
                else if (!matchedVersion.isSupported())
                    GeckoLibConstants.LOGGER.error("{}: Unsupported geo model format version: '{}'. {}", resourcePath, geometry.formatVersion(), matchedVersion.getErrorMessage());
                // --- bakeGeckoLibModelFile ---
                BakedGeoModel model = geometry.bake(resourcePath);
                entry.addProperty("ok", true);
                entry.addProperty("format_version", geometry.formatVersion());
                entry.addProperty("format_version_supported", matchedVersion != null && matchedVersion.isSupported());
                entry.addProperty("texture_width", model.properties().textureWidth());
                entry.addProperty("texture_height", model.properties().textureHeight());
                JsonArray bones = new JsonArray();
                for (GeoBone bone : model.topLevelBones()) dump(bone, bones);
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
        b.addProperty("name", bone.name());
        b.addProperty("parent", bone.parent == null ? null : bone.parent.name());
        b.add("pivot", arr(bone.pivotX, bone.pivotY, bone.pivotZ));
        b.add("rotation_rad", arr(bone.rotX, bone.rotY, bone.rotZ));
        JsonArray cubes = new JsonArray();
        if (bone instanceof CuboidGeoBone cuboid) {
            for (GeoCube cube : cuboid.cubes) {
                JsonObject c = new JsonObject();
                c.add("pivot", arr(cube.pivot().x, cube.pivot().y, cube.pivot().z));
                c.add("rotation_rad", arr(cube.rotation().x, cube.rotation().y, cube.rotation().z));
                c.add("size", arr(cube.size().x, cube.size().y, cube.size().z));
                JsonArray quads = new JsonArray();
                for (GeoQuad quad : cube.quads()) {
                    if (quad == null) continue;
                    JsonObject q = new JsonObject();
                    q.addProperty("direction", quad.direction().getName());
                    q.add("normal", arr(quad.normalX(), quad.normalY(), quad.normalZ()));
                    JsonArray verts = new JsonArray();
                    for (GeoVertex v : quad.vertices()) verts.add(arr(v.posX(), v.posY(), v.posZ(), v.texU(), v.texV()));
                    q.add("vertices", verts);
                    quads.add(q);
                }
                c.add("quads", quads);
                cubes.add(c);
            }
        }
        b.add("cubes", cubes);
        into.add(b);
        for (GeoBone child : bone.children) dump(child, into);
    }

    private static JsonArray arr(double... values) {
        JsonArray a = new JsonArray();
        for (double v : values) a.add(v);
        return a;
    }
}
