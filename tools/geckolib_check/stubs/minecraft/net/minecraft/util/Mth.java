package net.minecraft.util;

public class Mth {
    public static final float DEG_TO_RAD = (float)(Math.PI / 180.0);
    public static int floor(double value) { int i = (int)value; return value < i ? i - 1 : i; }
    public static int floor(float value) { int i = (int)value; return value < i ? i - 1 : i; }
}
