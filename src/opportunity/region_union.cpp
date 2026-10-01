// Deterministic sparse union kernel. Same whole-component constraints as Python reference.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>
extern "C" int constrained_union(int64_t n,int64_t p,const int64_t* edges,
    const double* bounds,double progress,double detour,double diameter,int64_t* labels){
 try{
    std::vector<int64_t> parent(n);std::vector<double> lo(bounds,bounds+4*n),hi=lo;
    for(int64_t i=0;i<n;++i)parent[i]=i;
    auto find=[&](int64_t i){while(parent[i]!=i){parent[i]=parent[parent[i]];i=parent[i];}return i;};
    for(int64_t e=0;e<p;++e){
        int64_t a=find(edges[2*e]),b=find(edges[2*e+1]);if(a==b)continue;
        double l[4],h[4];for(int k=0;k<4;++k){l[k]=std::min(lo[4*a+k],lo[4*b+k]);h[k]=std::max(hi[4*a+k],hi[4*b+k]);}
        double dx=h[2]-l[2],dy=h[3]-l[3];
        if(h[0]-l[0]>progress||h[1]-l[1]>detour||std::sqrt(dx*dx+dy*dy)>diameter)continue;
        if(a>b)std::swap(a,b);parent[b]=a;
        for(int k=0;k<4;++k){lo[4*a+k]=l[k];hi[4*a+k]=h[k];}
    }
    for(int64_t i=0;i<n;++i)labels[i]=find(i);return 0;
 }catch(...){return 1;}
}
