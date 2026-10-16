#include <cfenv>
#include <xmmintrin.h>
extern "C" {
unsigned test_get_mxcsr(){return _mm_getcsr();}
void test_set_mxcsr(unsigned v){_mm_setcsr(v);}
int test_get_round(){return std::fegetround();}
int test_set_round(int v){return std::fesetround(v);}
int test_downward(){return FE_DOWNWARD;}
unsigned test_get_x87(){unsigned short c;asm volatile("fnstcw %0":"=m"(c));return c;}
void test_set_x87(unsigned v){unsigned short c=v;asm volatile("fnclex; fldcw %0"::"m"(c));}
}
