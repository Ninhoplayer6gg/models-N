package com.geckolib;

import net.minecraft.resources.Identifier;

import java.util.ArrayList;
import java.util.List;

// Stub: guarda as mensagens de log do GeckoLib para o teste conferir que não houve aviso/erro.
public final class GeckoLibConstants {
    public static final String MODID = "geckolib";
    public static final Log LOGGER = new Log();

    public static Identifier id(String path) { return Identifier.fromNamespaceAndPath(MODID, path); }

    public static final class Log {
        public final List<String> messages = new ArrayList<>();
        private void add(String level, String msg, Object... args) {
            for (Object a : args) msg = msg.replaceFirst("\\{\\}", java.util.regex.Matcher.quoteReplacement(String.valueOf(a)));
            messages.add(level + ": " + msg);
        }
        public void warn(String msg, Object... args) { add("WARN", msg, args); }
        public void error(String msg, Object... args) { add("ERROR", msg, args); }
        public void info(String msg, Object... args) { add("INFO", msg, args); }
        public void debug(String msg, Object... args) { add("DEBUG", msg, args); }
    }
}
