// Exact per-region five-dimensional skyline; three discrete dimensions.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>
using I=int64_t;
extern "C" void grouped_pareto(I n,const double*z,const I*group,uint8_t*keep){
 std::fill(keep,keep+n,0);std::vector<I> order(n);for(I i=0;i<n;i++)order[i]=i;
 auto less=[&](I a,I b){if(group[a]!=group[b])return group[a]<group[b];
  for(int j:{2,3,4,0,1}){if(z[5*a+j]!=z[5*b+j])return z[5*a+j]<z[5*b+j];}return a<b;};
 std::sort(order.begin(),order.end(),less);
 for(I begin=0;begin<n;){I end=begin+1;while(end<n&&group[order[end]]==group[order[begin]])end++;
  std::vector<I> frontier;
  for(I pos=begin;pos<end;){I stop=pos+1;while(stop<end&&z[5*order[stop]+2]==z[5*order[pos]+2]&&z[5*order[stop]+3]==z[5*order[pos]+3]&&z[5*order[stop]+4]==z[5*order[pos]+4])stop++;
   double best_d=std::numeric_limits<double>::infinity(),best_t=best_d;
   for(I k=pos;k<stop;k++){I i=order[k];double t=z[5*i],d=z[5*i+1];if(d<best_d||(d==best_d&&t==best_t)){frontier.push_back(i);best_t=t;best_d=d;}}
   pos=stop;
  }
  for(I i:frontier){bool dominated=false;for(I j:frontier){bool le=true,lt=false;for(int k=0;k<5;k++){le&=z[5*j+k]<=z[5*i+k];lt|=z[5*j+k]<z[5*i+k];}if(le&&lt){dominated=true;break;}}keep[i]=!dominated;}
  begin=end;
 }
}
