// Optional conservative distance potential; never a selected-route backend.
#include <algorithm>
#include <cfloat>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>
#if defined(__x86_64__) && defined(__SSE2__)
#include <xmmintrin.h>
#endif

namespace {
thread_local char error_text[256] = {};
void error(const char* s) { std::strncpy(error_text,s,255);error_text[255]=0; }
using U = uint32_t; using Q = uint64_t;
constexpr U ABSENT=UINT32_MAX;
bool supported() {
#if defined(__x86_64__) && defined(__SSE2__) && FLT_EVAL_METHOD == 0
  unsigned csr=_mm_getcsr();
  unsigned short control;
  asm volatile("fnstcw %0" : "=m"(control));
  // GCC may use x87 while materializing denormal probe constants. Reject
  // unmasked x87 exceptions before any such load/conversion can execute.
  if((control & 0x003fu)!=0x003fu || (control & 0x0c00u)) return false;
  if(sizeof(double)!=8 || !std::numeric_limits<double>::is_iec559 ||
      std::numeric_limits<double>::digits!=53 || std::fegetround()!=FE_TONEAREST ||
      (csr & ((1u<<15)|(1u<<6)|(3u<<13))) || (csr & 0x1f80u)!=0x1f80u) return false;
  // Volatile loads and operations prevent constant folding, including probes
  // of a subnormal INPUT (DAZ) and a subnormal RESULT (FTZ).
  volatile double large=9007199254740992.0, one=1.0;
  volatile double tiny=std::numeric_limits<double>::denorm_min();
  volatile double normal=std::numeric_limits<double>::min(), half=0.5;
  volatile double rn=large+one, subinput=tiny+tiny, subresult=normal*half;
  bool result=rn==large && subinput>tiny && subresult>0 && subresult<normal;
  _mm_setcsr(csr); // Preserve caller's sticky flags after the inexact RN probe.
  return result;
#else
  return false;
#endif
}
Q weight(double value, unsigned k, Q cap) {
  uint64_t bits;std::memcpy(&bits,&value,8);
  Q magnitude=bits & 0x7fffffffffffffffull;
  unsigned exponent=(bits>>52)&2047u;
  Q mantissa=bits & ((Q(1)<<52)-1);
  if(exponent==2047 || ((bits>>63) && magnitude))
    throw std::runtime_error("Nonfinite or negative original distance");
  if(!magnitude) return 0;
  int shift;
  if(exponent) { mantissa|=Q(1)<<52;shift=int(exponent)-1023-52+int(k); }
  else shift=-1074+int(k);
  if(shift>=0) {
    if(shift>=64 || mantissa>(cap>>shift)) return cap;
    return std::min(cap,mantissa<<shift);
  }
  if(-shift>=64) return 0;
  return std::min(cap,mantissa>>(-shift));
}
bool conservative(double value,unsigned k,Q q) {
  // Independent exact dyadic inequality q*2^-k <= original distance. This
  // compares cross-products, rather than trusting the floor result alone.
  uint64_t bits;std::memcpy(&bits,&value,8);
  unsigned exponent=(bits>>52)&2047u;Q mantissa=bits&((Q(1)<<52)-1);
  int shift;
  if(exponent){mantissa|=Q(1)<<52;shift=int(exponent)-1023-52+int(k);}
  else shift=-1074+int(k);
  if(shift>=0) {
    if(shift>=64 || mantissa>(UINT64_MAX>>shift))return true;
    return q<=(mantissa<<shift);
  }
  unsigned right=unsigned(-shift);
  if(!q)return true;
  if(right>=64 || q>(UINT64_MAX>>right))return false;
  return (q<<right)<=mantissa;
}
struct Potential {
  U n,destination;Q m,cap,checked=0,heap_peak=0;unsigned k;
  std::vector<Q> p;
  Potential(U nn,Q mm,U d,unsigned kk,Q h):n(nn),destination(d),m(mm),cap(h),k(kk),p(nn,h){}
  void validate(const int64_t* source,const int64_t* target,const double* length) {
    if(p[destination]!=0) throw std::runtime_error("Nonzero destination potential");
    for(auto v:p) if(v>cap) throw std::runtime_error("Potential exceeds cap");
    checked=0;
    for(Q e=0;e<m;++e) {
      if(source[e]<0 || target[e]<0 || Q(source[e])>=n || Q(target[e])>=n)
        throw std::runtime_error("Original edge endpoint outside graph");
      Q w=weight(length[e],k,cap);
      if(!conservative(length[e],k,w))throw std::runtime_error("Downward edge quantization certificate failed");
      // w<=cap<=2^62-1, so this addition is exact and cannot overflow.
      if(p[source[e]]>w+p[target[e]]) throw std::runtime_error("Original edge certificate failed");
      ++checked;
    }
  }
};
}
extern "C" {
int energy_environment_supported(){return supported()?1:0;}
const char* energy_last_error(){return error_text;}
void* energy_build(uint64_t n,uint64_t m,const int64_t* source,const int64_t* target,
                   const double* length,uint64_t destination,unsigned k,uint64_t cap) {
  error_text[0]=0;
  try {
    if(!supported()) throw std::runtime_error("Unsupported binary64 environment");
    if(!n || n>UINT32_MAX || m>UINT32_MAX || destination>=n || k>30 ||
       !cap || cap>((Q(1)<<62)-1)) throw std::runtime_error("Unsupported bounded index/quantum domain");
    auto result=std::make_unique<Potential>(U(n),m,U(destination),k,cap);
    std::vector<Q> offsets(n+1,0);
    std::vector<U> incoming(m),heap(n),position(n,ABSENT);
    for(Q e=0;e<m;++e) {
      if(source[e]<0 || target[e]<0 || Q(source[e])>=n || Q(target[e])>=n)
        throw std::runtime_error("Original edge endpoint outside graph");
      (void)weight(length[e],k,cap); ++offsets[target[e]+1];
    }
    for(Q v=1;v<=n;++v) offsets[v]+=offsets[v-1];
    // Reuse heap position storage as CSR cursor because m<=UINT32_MAX.
    for(Q v=0;v<n;++v) position[v]=U(offsets[v]);
    for(Q e=0;e<m;++e) incoming[position[target[e]]++]=U(e);
    std::fill(position.begin(),position.end(),ABSENT);
    Q size=0;
    auto less=[&](U a,U b){return result->p[a]<result->p[b] ||
      (result->p[a]==result->p[b] && a<b);};
    auto swap_at=[&](Q a,Q b){std::swap(heap[a],heap[b]);position[heap[a]]=U(a);position[heap[b]]=U(b);};
    auto decrease=[&](U v){
      Q i=position[v];
      if(i==ABSENT) { if(size>=n) throw std::runtime_error("Indexed heap capacity exceeded");
        i=size++;heap[i]=v;position[v]=U(i);result->heap_peak=std::max(result->heap_peak,size); }
      while(i && less(heap[i],heap[(i-1)/2])) {Q parent=(i-1)/2;swap_at(i,parent);i=parent;}
    };
    result->p[destination]=0;decrease(U(destination));
    while(size) {
      U v=heap[0];position[v]=ABSENT;--size;
      if(size) {
        heap[0]=heap[size];position[heap[0]]=0;Q i=0;
        while(2*i+1<size) {Q child=2*i+1;if(child+1<size && less(heap[child+1],heap[child]))++child;
          if(!less(heap[child],heap[i]))break;swap_at(i,child);i=child;}
      }
      for(Q at=offsets[v];at<offsets[v+1];++at) {
        Q e=incoming[at],w=weight(length[e],k,cap),candidate=std::min(cap,result->p[v]+w);
        U from=U(source[e]);if(candidate<result->p[from]){result->p[from]=candidate;decrease(from);}
      }
    }
    // A distinct full scan validates every original edge, including edges
    // outside the reverse-reached subset. Construction scratch dies here.
    result->validate(source,target,length);
    return result.release();
  } catch(const std::exception& e){error(e.what());return nullptr;}
    catch(...){error("Unknown potential construction error");return nullptr;}
}
int energy_validate(void* handle,const int64_t* s,const int64_t* t,const double* d) {
  try{if(!handle)throw std::runtime_error("Closed potential");static_cast<Potential*>(handle)->validate(s,t,d);return 1;}
  catch(const std::exception& e){error(e.what());return 0;}
}
const uint64_t* energy_labels(void* h){return h?static_cast<Potential*>(h)->p.data():nullptr;}
uint64_t energy_checked_edges(void* h){return h?static_cast<Potential*>(h)->checked:0;}
uint64_t energy_heap_peak(void* h){return h?static_cast<Potential*>(h)->heap_peak:0;}
void energy_destroy(void* h){delete static_cast<Potential*>(h);}
}
