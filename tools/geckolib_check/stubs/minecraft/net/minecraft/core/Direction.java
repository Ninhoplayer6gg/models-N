package net.minecraft.core;

// Stub mínimo com a mesma ordem e nomes do enum Direction do Minecraft.
public enum Direction {
    DOWN("down", Axis.Y, 0, -1, 0), UP("up", Axis.Y, 0, 1, 0), NORTH("north", Axis.Z, 0, 0, -1),
    SOUTH("south", Axis.Z, 0, 0, 1), WEST("west", Axis.X, -1, 0, 0), EAST("east", Axis.X, 1, 0, 0);

    private final String name;
    private final Axis axis;
    private final int dx, dy, dz;

    Direction(String name, Axis axis, int dx, int dy, int dz) { this.name = name; this.axis = axis; this.dx = dx; this.dy = dy; this.dz = dz; }
    public org.joml.Vector3f step() { return new org.joml.Vector3f(dx, dy, dz); }
    public Axis getAxis() { return axis; }
    public String getName() { return name; }
    public static Direction byName(String name) {
        for (Direction d : values()) if (d.name.equals(name)) return d;
        return null;
    }
    @Override public String toString() { return name; }

    public enum Axis { X, Y, Z }
}
