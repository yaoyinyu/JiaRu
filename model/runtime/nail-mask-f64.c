/* 原尺寸mask路径：F32参数位值提升，F64特征；坐标及粗mask种子保持F32。 */
#include <wasm_simd128.h>

__attribute__((import_module("env"), import_name("exp"))) double host_exp(double);

/* 正项收敛级数避免大参数交错相消；|x|>=6的erf尾误差小于3e-17。 */
double erf64(double x) {
    double a = __builtin_fabs(x);
    if (a >= 6.0) return x < 0.0 ? -1.0 : 1.0;
    double term = 1.0, sum = 1.0, a2 = 2.0 * a * a;
    for (int n = 1; n <= 160; ++n) {
        term *= a2 / (2.0 * n + 1.0);
        double next = sum + term;
        if (next == sum) break;
        sum = next;
    }
    double result = (1.1283791670955125739 * a * host_exp(-a * a)) * sum;
    return x < 0.0 ? -result : result;
}

void promote(const float *input, double *out, int n) {
    for (int i = 0; i < n; ++i) out[i] = input[i];
}

/* 两段输入按通道顺序读取，避免物化解码器大尺寸Concat。 */
static double scalar_conv(const double *first, const double *second,
                          const float *weight, int c1, int c2, int h, int w,
                          int o, int y, int x) {
    int channels = c1 + c2, plane = h * w;
    double sum = 0.0;
    for (int c = 0; c < channels; ++c) {
        const double *input = c < c1 ? first + c * plane : second + (c - c1) * plane;
        const float *kernel = weight + (o * channels + c) * 9;
        for (int ky = 0; ky < 3; ++ky) {
            int iy = y + ky - 1;
            if (iy < 0 || iy >= h) continue;
            for (int kx = 0; kx < 3; ++kx) {
                int ix = x + kx - 1;
                if (ix >= 0 && ix < w) sum += input[iy * w + ix] * (double)kernel[ky * 3 + kx];
            }
        }
    }
    return sum;
}

void conv3(const double *first, const double *second, const float *weight,
           double *out, int c1, int c2, int outputs, int h, int w) {
    int channels = c1 + c2, plane = h * w;
    for (int o = 0; o < outputs; ++o) {
        for (int y = 0; y < h; ++y) {
            double *row = out + (o * h + y) * w;
            row[0] = scalar_conv(first, second, weight, c1, c2, h, w, o, y, 0);
            int x = 1;
            for (; x + 1 < w - 1; x += 2) {
                v128_t sum = wasm_f64x2_splat(0.0);
                for (int c = 0; c < channels; ++c) {
                    const double *input = c < c1 ? first + c * plane : second + (c - c1) * plane;
                    const float *kernel = weight + (o * channels + c) * 9;
                    for (int ky = 0; ky < 3; ++ky) {
                        int iy = y + ky - 1;
                        if (iy < 0 || iy >= h) continue;
                        for (int kx = 0; kx < 3; ++kx) {
                            v128_t a = wasm_v128_load(input + iy * w + x + kx - 1);
                            v128_t b = wasm_f64x2_splat((double)kernel[ky * 3 + kx]);
                            sum = wasm_f64x2_add(sum, wasm_f64x2_mul(a, b));
                        }
                    }
                }
                wasm_v128_store(row + x, sum);
            }
            for (; x < w; ++x) row[x] = scalar_conv(first, second, weight, c1, c2, h, w, o, y, x);
        }
    }
}

void gn4(double *x, const float *gamma, const float *beta, int channels,
         int h, int w, double epsilon) {
    int plane = h * w, count = channels * plane / 4;
    for (int group = 0; group < 4; ++group) {
        double *a = x + group * count, sum = 0.0;
        for (int i = 0; i < count; ++i) sum += a[i];
        double mean = sum / count, variance = 0.0;
        for (int i = 0; i < count; ++i) {
            double centered = a[i] - mean;
            variance += centered * centered;
        }
        double denominator = __builtin_sqrt(variance / count + epsilon);
        for (int i = 0; i < count; ++i) {
            int c = group * (channels / 4) + i / plane;
            a[i] = ((a[i] - mean) / denominator) * (double)gamma[c] + (double)beta[c];
        }
    }
}

void gelu(double *x, int n, double divisor, double one, double half) {
    for (int i = 0; i < n; ++i) x[i] = (x[i] * (one + erf64(x[i] / divisor))) * half;
}

void pool2(const double *x, double *out, int channels, int h, int w) {
    int oh = h / 2, ow = w / 2;
    for (int c = 0; c < channels; ++c) {
        for (int y = 0; y < oh; ++y) {
            for (int z = 0; z < ow; ++z) {
                int i = (c * h + y * 2) * w + z * 2;
                out[(c * oh + y) * ow + z] = (((x[i] + x[i + 1]) + x[i + w]) + x[i + w + 1]) * .25;
            }
        }
    }
}

/* 每步float运算在WASM中真实舍入，不能提升为double坐标。 */
static void coordinate(int index, float ratio, int incoming, int *lo, int *hi,
                       float *weight0, float *weight1) {
    float shifted = ((float)index + .5f) * ratio;
    shifted = shifted - .5f;
    float value = shifted > 0.f ? shifted : 0.f;
    int lower = (int)value;
    if (lower > incoming - 1) lower = incoming - 1;
    *lo = lower;
    *hi = lower + 1 < incoming ? lower + 1 : incoming - 1;
    *weight1 = value - (float)lower;
    *weight0 = 1.f - *weight1;
}

void resize64(const double *x, double *out, int channels, int h, int w,
              int oh, int ow, float ry, float rx) {
    for (int c = 0; c < channels; ++c) {
        for (int y = 0; y < oh; ++y) {
            int yl, yh; float wy0, wy1;
            coordinate(y, ry, h, &yl, &yh, &wy0, &wy1);
            for (int z = 0; z < ow; ++z) {
                int xl, xh; float wx0, wx1;
                coordinate(z, rx, w, &xl, &xh, &wx0, &wx1);
                double top = (double)wx0 * x[(c * h + yl) * w + xl] + (double)wx1 * x[(c * h + yl) * w + xh];
                double bottom = (double)wx0 * x[(c * h + yh) * w + xl] + (double)wx1 * x[(c * h + yh) * w + xh];
                out[(c * oh + y) * ow + z] = (double)wy0 * top + (double)wy1 * bottom;
            }
        }
    }
}

void final_mask(const double *x, const float *weight, const float *bias,
                const float *candidate, float *out, int channels, int pixels) {
    for (int i = 0; i < pixels; ++i) {
        double delta = 0.0;
        for (int c = 0; c < channels; ++c) delta += x[c * pixels + i] * (double)weight[c];
        delta += (double)bias[0];
        float seed = candidate[3 * pixels + i] * 8.f;
        seed = seed - 4.f;
        out[i] = (float)((double)seed + delta);
    }
}
