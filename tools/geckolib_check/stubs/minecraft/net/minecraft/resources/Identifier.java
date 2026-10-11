package net.minecraft.resources;

public final class Identifier {
    private final String namespace;
    private final String path;

    private Identifier(String namespace, String path) { this.namespace = namespace; this.path = path; }
    public static Identifier fromNamespaceAndPath(String namespace, String path) { return new Identifier(namespace, path); }
    public static Identifier parse(String text) {
        int i = text.indexOf(':');
        return i < 0 ? new Identifier("minecraft", text) : new Identifier(text.substring(0, i), text.substring(i + 1));
    }
    public Identifier withPath(String newPath) { return new Identifier(namespace, newPath); }
    public String getNamespace() { return namespace; }
    public String getPath() { return path; }
    @Override public String toString() { return namespace + ":" + path; }
    @Override public boolean equals(Object o) { return o instanceof Identifier r && r.namespace.equals(namespace) && r.path.equals(path); }
    @Override public int hashCode() { return 31 * namespace.hashCode() + path.hashCode(); }
}
