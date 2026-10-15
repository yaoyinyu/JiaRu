/* 原内核保持；仅替换resize的坐标舍入为原生float融合乘加语义。 */
#define resize64 original_resize64
#include "nail-mask-f64.c"
#undef resize64

static void native_coordinate(int index, float ratio, int incoming, int *lo, int *hi,
                              float *weight0, float *weight1) {
    /* index<=628时此乘积与减法在double中精确，最后一次float舍入等价FMA。 */
    float shifted = (float)(((double)index + .5) * (double)ratio - .5);
    float value = shifted > 0.f ? shifted : 0.f;
    int lower = (int)value;
    if (lower > incoming - 1) lower = incoming - 1;
    *lo = lower;
    *hi = lower + 1 < incoming ? lower + 1 : incoming - 1;
    *weight1 = value - (float)lower;
    *weight0 = 1.f - *weight1;
}

void capture_coordinates(int incoming, int outgoing, float ratio,
                         int *lower, int *upper, float *weight0, float *weight1) {
    for (int i = 0; i < outgoing; ++i) {
        native_coordinate(i, ratio, incoming, lower + i, upper + i, weight0 + i, weight1 + i);
    }
}

void resize64(const double *x, double *out, int channels, int h, int w,
              int oh, int ow, float ry, float rx) {
    for (int c = 0; c < channels; ++c) {
        for (int y = 0; y < oh; ++y) {
            int yl, yh; float wy0, wy1;
            native_coordinate(y, ry, h, &yl, &yh, &wy0, &wy1);
            for (int z = 0; z < ow; ++z) {
                int xl, xh; float wx0, wx1;
                native_coordinate(z, rx, w, &xl, &xh, &wx0, &wx1);
                double top = (double)wx0 * x[(c * h + yl) * w + xl] + (double)wx1 * x[(c * h + yl) * w + xh];
                double bottom = (double)wx0 * x[(c * h + yh) * w + xl] + (double)wx1 * x[(c * h + yh) * w + xh];
                out[(c * oh + y) * ow + z] = (double)wy0 * top + (double)wy1 * bottom;
            }
        }
    }
}
