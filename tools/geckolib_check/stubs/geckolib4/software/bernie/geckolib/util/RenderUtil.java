package software.bernie.geckolib.util;

import net.minecraft.world.phys.Vec3;

// Só o método usado pelo BakedModelFactory, copiado do RenderUtil do GeckoLib 4 (o resto é renderização).
public final class RenderUtil {
	public static Vec3 arrayToVec(double[] array) {
		final double x;
		final double y;
		final double z;

		if (array.length == 1) {
			x = y = z = array[0];
		}
		else {
			x = array[0];
			y = array[1];
			z = array[2];
		}

		if (x == 0 && y == 0 && z == 0)
			return Vec3.ZERO;

		return new Vec3(x, y, z);
	}
}
