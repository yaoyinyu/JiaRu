/* 只增加坐标导出，不改写原数值内核；完整新控制仍须重跑。 */
#include "nail-mask-f64.c"

void capture_coordinates(int incoming, int outgoing, float ratio,
                         int *lower, int *upper, float *weight0, float *weight1) {
    for (int i = 0; i < outgoing; ++i) {
        coordinate(i, ratio, incoming, lower + i, upper + i, weight0 + i, weight1 + i);
    }
}
