// Shared sparse directed graph index. No graph copy per region or OD.
// Fastest paths minimize (seconds, actual length); equal labels retain first
// discovery with node/edge IDs giving deterministic traversal.
#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <queue>
#include <tuple>
#include <vector>
using I=int64_t; using U=uint32_t;
const double INF=std::numeric_limits<double>::infinity();
using Item=std::tuple<double,double,U>;
using Queue=std::priority_queue<Item,std::vector<Item>,std::greater<Item>>;
struct Graph {
 I n,m; const I *s,*t; const double *time,*length;
 std::vector<I> off,rev;std::vector<U> out,in;
 std::vector<double> dist,aux,prefix,suffix;
 std::vector<I> mark;I token=0;
 std::vector<I> result;
 Graph(I nn,I mm,const I*ss,const I*tt,const double*times,const double*lengths):n(nn),m(mm),s(ss),t(tt),time(times),length(lengths),off(n+1),rev(n+1),out(m),in(m),dist(n,INF),aux(n,INF),prefix(n,INF),suffix(n,INF),mark(n,0){
  for(I e=0;e<m;e++){off[s[e]+1]++;rev[t[e]+1]++;}
  for(I u=1;u<=n;u++){off[u]+=off[u-1];rev[u]+=rev[u-1];}
  auto a=off,b=rev;for(I e=0;e<m;e++){out[a[s[e]]++]=e;in[b[t[e]]++]=e;}
 }
 void full(I root,bool reverse,double*cost,double*len,I*parent){
  std::fill(cost,cost+n,INF);std::fill(len,len+n,INF);std::fill(parent,parent+n,-1);
  cost[root]=len[root]=0;Queue q;q.emplace(0,0,root);
  const auto &o=reverse?rev:off;const auto &adj=reverse?in:out;
  while(!q.empty()){
   auto [d,l,u]=q.top();q.pop();if(d!=cost[u]||l!=len[u])continue;
   for(I k=o[u];k<o[u+1];k++){U e=adj[k],v=reverse?s[e]:t[e];double nd=d+time[e],nl=l+length[e];
    if(nd<cost[v]||(nd==cost[v]&&nl<len[v])){cost[v]=nd;len[v]=nl;parent[v]=u;q.emplace(nd,nl,v);}
   }
  }
 }
 void pairs(I p,const I*from,const I*to,double cutoff,double*times,double*lengths){
  std::vector<std::tuple<I,I,I>> requests;requests.reserve(p);
  for(I k=0;k<p;k++)requests.emplace_back(from[k],to[k],k);
  std::sort(requests.begin(),requests.end());std::vector<U> touched;
  for(I begin=0;begin<p;){
   I end=begin+1;U root=std::get<0>(requests[begin]);while(end<p&&std::get<0>(requests[end])==root)end++;
   Queue q;dist[root]=aux[root]=0;touched.push_back(root);q.emplace(0,0,root);
   while(!q.empty()){
    auto [d,l,u]=q.top();q.pop();if(d!=dist[u]||l!=aux[u])continue;
    for(I k=off[u];k<off[u+1];k++){U e=out[k],v=t[e];double nd=d+time[e],nl=l+length[e];
     if(nd<=cutoff&&(nd<dist[v]||(nd==dist[v]&&nl<aux[v]))){if(dist[v]==INF)touched.push_back(v);dist[v]=nd;aux[v]=nl;q.emplace(nd,nl,v);}
    }
   }
   for(I k=begin;k<end;k++){I v=std::get<1>(requests[k]),i=std::get<2>(requests[k]);times[i]=dist[v];lengths[i]=aux[v];}
   for(U v:touched){dist[v]=aux[v]=INF;}touched.clear();begin=end;
  }
 }
 void internal_labels(const I*members,I count,const double*seeds,bool reverse,double*labels,const std::vector<U>&local){
  for(U u:local)labels[u]=INF;Queue q;
  for(I k=0;k<count;k++){U u=members[k];if(seeds[u]<labels[u]){labels[u]=seeds[u];q.emplace(labels[u],0,u);}}
  const auto &o=reverse?rev:off;const auto &adj=reverse?in:out;
  while(!q.empty()){
   auto [d,l,u]=q.top();q.pop();if(d!=labels[u])continue;
   for(I k=o[u];k<o[u+1];k++){U e=adj[k],v=reverse?s[e]:t[e];if(mark[v]!=token)continue;
    double nd=d+time[e];if(nd<labels[v]){labels[v]=nd;q.emplace(nd,0,v);}
   }
  }
 }
 I* gateways(const I*members,I count,double radius,const double*ds,const double*dd,
             const I*parents,const I*next,double budget,double*timings,I*out_size){
  auto started=std::chrono::steady_clock::now();std::vector<U> local;Queue q;
  ++token;
  for(I k=0;k<count;k++){U u=members[k];if(mark[u]!=token){mark[u]=token;dist[u]=0;local.push_back(u);q.emplace(0,0,u);}}
  while(!q.empty()){
   auto [d,l,u]=q.top();q.pop();if(d!=dist[u])continue;
   for(int direction=0;direction<2;direction++){
    const auto &o=direction?rev:off;const auto &adj=direction?in:out;
    for(I k=o[u];k<o[u+1];k++){U e=adj[k],v=direction?s[e]:t[e];double nd=d+length[e];
     if(nd<=radius&&(mark[v]!=token||nd<dist[v])){
      if(mark[v]!=token){mark[v]=token;local.push_back(v);}dist[v]=nd;q.emplace(nd,0,v);
     }
    }
   }
  }
  timings[0]=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
  auto interface_start=std::chrono::steady_clock::now();
  internal_labels(members,count,ds,false,prefix.data(),local);
  internal_labels(members,count,dd,true,suffix.data(),local);
  // Directed root connectivity is audited inside the bounded view, independently
  // of geometry and without treating weak connectivity as equivalence.
  std::vector<uint8_t> reached(local.size(),0);I unreachable=0;
  auto reach=[&](bool reverse){std::vector<U> stack{U(members[0])},touched;aux[members[0]]=0;touched.push_back(members[0]);
   const auto &o=reverse?rev:off;const auto &adj=reverse?in:out;
   while(!stack.empty()){U u=stack.back();stack.pop_back();for(I k=o[u];k<o[u+1];k++){U e=adj[k],v=reverse?s[e]:t[e];if(mark[v]==token&&aux[v]==INF){aux[v]=0;touched.push_back(v);stack.push_back(v);}}}
   std::vector<bool> ok(count);for(I k=0;k<count;k++)ok[k]=aux[members[k]]==0;for(U v:touched)aux[v]=INF;return ok;};
  auto forward=reach(false),backward=reach(true);for(I k=0;k<count;k++)if(!forward[k]||!backward[k])unreachable++;
  std::map<I,std::pair<I,I>> gateways;I internal_edges=0;
  for(U u:local){
   for(I k=off[u];k<off[u+1];k++){U e=out[k],v=t[e];if(mark[v]==token){internal_edges++;continue;}
    if(prefix[u]+time[e]+dd[v]<=budget){gateways[u].first|=2;gateways[u].second++;}}
   for(I k=rev[u];k<rev[u+1];k++){U e=in[k],v=s[e];if(mark[v]==token)continue;
    if(ds[v]+time[e]+suffix[u]<=budget){gateways[u].first|=1;gateways[u].second++;}}
  }
  result={I(local.size()),internal_edges,unreachable,I(gateways.size()),count};
  for(auto &[node,roles]:gateways){result.push_back(node);result.push_back(roles.first);result.push_back(roles.second);}
  auto trace=[&](I node,const I*tree){I steps=0;while(tree[node]>=0&&mark[tree[node]]==token){node=tree[node];if(++steps>n)return I(-2);}return tree[node]<0?I(-1):node;};
  for(I k=0;k<count;k++){result.push_back(members[k]);result.push_back(trace(members[k],parents));result.push_back(trace(members[k],next));}
  for(U v:local)dist[v]=INF;
  timings[1]=std::chrono::duration<double>(std::chrono::steady_clock::now()-interface_start).count();
  *out_size=result.size();return result.data();
 }
};
extern "C" {
 void* graph_create(I n,I m,const I*s,const I*t,const double*time,const double*length){if(n<=0||n>UINT32_MAX||m>UINT32_MAX)return nullptr;return new Graph(n,m,s,t,time,length);}
 void graph_free(void*g){delete static_cast<Graph*>(g);}
 void graph_full(void*g,I root,int reverse,double*cost,double*length,I*parent){static_cast<Graph*>(g)->full(root,reverse,cost,length,parent);}
 void graph_pairs(void*g,I p,const I*from,const I*to,double cutoff,double*time,double*length){static_cast<Graph*>(g)->pairs(p,from,to,cutoff,time,length);}
 I* graph_gateways(void*g,const I*members,I count,double radius,const double*ds,const double*dd,const I*parents,const I*next,double budget,double*timings,I*size){if(count<1){*size=0;return nullptr;}return static_cast<Graph*>(g)->gateways(members,count,radius,ds,dd,parents,next,budget,timings,size);}
}
