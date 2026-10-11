package net.minecraft.util;

import java.util.function.Consumer;

public class Util {
    public static <T> T make(T object, Consumer<? super T> consumer) { consumer.accept(object); return object; }
}
