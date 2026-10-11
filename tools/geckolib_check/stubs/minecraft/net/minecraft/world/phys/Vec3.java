package net.minecraft.world.phys;

// Stub mínimo (só o que o leitor de geometria do GeckoLib usa), com a semântica do Vec3 do Minecraft.
public class Vec3 {
    public static final Vec3 ZERO = new Vec3(0, 0, 0);
    public final double x;
    public final double y;
    public final double z;

    public Vec3(double x, double y, double z) { this.x = x; this.y = y; this.z = z; }
    public Vec3 add(double dx, double dy, double dz) { return new Vec3(x + dx, y + dy, z + dz); }
    public Vec3 add(Vec3 v) { return add(v.x, v.y, v.z); }
    public Vec3 multiply(double mx, double my, double mz) { return new Vec3(x * mx, y * my, z * mz); }
    public Vec3 multiply(Vec3 v) { return multiply(v.x, v.y, v.z); }
    public Vec3 scale(double f) { return multiply(f, f, f); }
    public double x() { return x; }
    public double y() { return y; }
    public double z() { return z; }
    @Override public String toString() { return "(" + x + ", " + y + ", " + z + ")"; }
}
