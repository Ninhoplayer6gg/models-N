package com.mojang.datafixers.util;

import java.util.Optional;
import java.util.function.Function;

// Stub mínimo do Either da DataFixerUpper (Mojang).
public abstract class Either<L, R> {
    public static <L, R> Either<L, R> left(L value) { return new Either<>() {
        public <T> T map(Function<? super L, ? extends T> l, Function<? super R, ? extends T> r) { return l.apply(value); }
        public Optional<L> left() { return Optional.of(value); }
        public Optional<R> right() { return Optional.empty(); }
    }; }
    public static <L, R> Either<L, R> right(R value) { return new Either<>() {
        public <T> T map(Function<? super L, ? extends T> l, Function<? super R, ? extends T> r) { return r.apply(value); }
        public Optional<L> left() { return Optional.empty(); }
        public Optional<R> right() { return Optional.of(value); }
    }; }
    public abstract <T> T map(Function<? super L, ? extends T> l, Function<? super R, ? extends T> r);
    public abstract Optional<L> left();
    public abstract Optional<R> right();
}
