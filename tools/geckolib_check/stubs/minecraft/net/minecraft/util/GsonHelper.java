package net.minecraft.util;

import com.google.gson.*;

// Stub com a semântica do GsonHelper do Minecraft: com valor padrão, devolve o padrão se a chave
// não existir; sem padrão, a chave é obrigatória; tipo errado gera JsonSyntaxException.
public class GsonHelper {
    private static JsonElement req(JsonObject o, String k, String what) {
        if (!o.has(k)) throw new JsonSyntaxException("Missing " + k + ", expected to find " + what);
        return o.get(k);
    }
    private static JsonPrimitive prim(JsonElement e, String k, String what) {
        if (!e.isJsonPrimitive()) throw new JsonSyntaxException("Expected " + k + " to be " + what + ", was " + e);
        return e.getAsJsonPrimitive();
    }
    public static String getAsString(JsonObject o, String k) { return prim(req(o, k, "a string"), k, "a string").getAsString(); }
    public static String getAsString(JsonObject o, String k, String def) { return o.has(k) ? getAsString(o, k) : def; }
    public static boolean getAsBoolean(JsonObject o, String k) {
        JsonPrimitive p = prim(req(o, k, "a boolean"), k, "a boolean");
        if (!p.isBoolean()) throw new JsonSyntaxException("Expected " + k + " to be a boolean, was " + p);
        return p.getAsBoolean();
    }
    public static boolean getAsBoolean(JsonObject o, String k, boolean def) { return o.has(k) ? getAsBoolean(o, k) : def; }
    private static JsonPrimitive num(JsonObject o, String k) {
        JsonPrimitive p = prim(req(o, k, "a number"), k, "a number");
        if (!p.isNumber()) throw new JsonSyntaxException("Expected " + k + " to be a number, was " + p);
        return p;
    }
    public static double getAsDouble(JsonObject o, String k) { return num(o, k).getAsDouble(); }
    public static double getAsDouble(JsonObject o, String k, double def) { return o.has(k) ? getAsDouble(o, k) : def; }
    public static float getAsFloat(JsonObject o, String k) { return num(o, k).getAsFloat(); }
    public static float getAsFloat(JsonObject o, String k, float def) { return o.has(k) ? getAsFloat(o, k) : def; }
    public static int getAsInt(JsonObject o, String k) { return num(o, k).getAsInt(); }
    public static int getAsInt(JsonObject o, String k, int def) { return o.has(k) ? getAsInt(o, k) : def; }
    public static long getAsLong(JsonObject o, String k) { return num(o, k).getAsLong(); }
    public static long getAsLong(JsonObject o, String k, long def) { return o.has(k) ? getAsLong(o, k) : def; }
    public static JsonArray getAsJsonArray(JsonObject o, String k) {
        JsonElement e = req(o, k, "a JsonArray");
        if (!e.isJsonArray()) throw new JsonSyntaxException("Expected " + k + " to be a JsonArray, was " + e);
        return e.getAsJsonArray();
    }
    public static JsonArray getAsJsonArray(JsonObject o, String k, JsonArray def) { return o.has(k) ? getAsJsonArray(o, k) : def; }
    public static JsonObject getAsJsonObject(JsonObject o, String k) {
        JsonElement e = req(o, k, "a JsonObject");
        if (!e.isJsonObject()) throw new JsonSyntaxException("Expected " + k + " to be a JsonObject, was " + e);
        return e.getAsJsonObject();
    }
    public static JsonObject getAsJsonObject(JsonObject o, String k, JsonObject def) { return o.has(k) ? getAsJsonObject(o, k) : def; }
    public static <T> T getAsObject(JsonObject o, String k, JsonDeserializationContext ctx, Class<? extends T> cls) {
        return ctx.deserialize(req(o, k, cls.getSimpleName()), cls);
    }
    public static <T> T getAsObject(JsonObject o, String k, T def, JsonDeserializationContext ctx, Class<? extends T> cls) {
        return o.has(k) ? ctx.deserialize(o.get(k), cls) : def;
    }
}
