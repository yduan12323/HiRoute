// Bounded directed Dijkstra for spatially screened opportunity pairs.
// Binary stdin: uint64 n,m,p; sources[m], targets[m], float64 lengths[m], pairs[p][2].
// Binary stdout: float64[p][2] directed distances; +inf means beyond cutoff/unreachable.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <queue>
#include <tuple>
#include <vector>
using U = uint64_t;
const double INF = std::numeric_limits<double>::infinity();
template<class T> void read(std::vector<T>& v) {
    if (!std::cin.read(reinterpret_cast<char*>(v.data()), v.size()*sizeof(T))) throw std::runtime_error("short input");
}
int main(int argc, char**argv) { try {
    if(argc!=2) return 2;
    double cutoff=std::stod(argv[1]); if(!std::isfinite(cutoff)||cutoff<=0) return 2;
    std::vector<U> header(3); read(header); U n=header[0],m=header[1],p=header[2];
    std::vector<U> source(m),target(m),ends(2*p); std::vector<double> lengths(m);
    read(source);read(target);read(lengths);read(ends);
    std::vector<U> offsets(n+1,0);
    for(U e=0;e<m;++e){ if(source[e]>=n||target[e]>=n||!std::isfinite(lengths[e])||lengths[e]<0) return 3; ++offsets[source[e]+1]; }
    for(U i=1;i<=n;++i) offsets[i]+=offsets[i-1];
    auto cursor=offsets; std::vector<U> neighbors(m);std::vector<double> weights(m);
    for(U e=0;e<m;++e){U pos=cursor[source[e]]++;neighbors[pos]=target[e];weights[pos]=lengths[e];}
    source.clear(); source.shrink_to_fit();target.clear();target.shrink_to_fit();lengths.clear();lengths.shrink_to_fit();cursor.clear();cursor.shrink_to_fit();
    // Sparse targets only. Process each access node once, in each needed direction.
    std::vector<std::tuple<U,U,U>> requests;requests.reserve(2*p);
    for(U i=0;i<p;++i){if(ends[2*i]>=n||ends[2*i+1]>=n) return 3;requests.emplace_back(ends[2*i],ends[2*i+1],2*i);requests.emplace_back(ends[2*i+1],ends[2*i],2*i+1);}
    std::sort(requests.begin(),requests.end());
    std::vector<double> results(2*p,INF),distance(n,INF);std::vector<U> touched;
    U searches=0,visited=0;
    for(U begin=0;begin<requests.size();){
        U end=begin+1,start=std::get<0>(requests[begin]);while(end<requests.size()&&std::get<0>(requests[end])==start)++end;
        using Entry=std::pair<double,U>; std::priority_queue<Entry,std::vector<Entry>,std::greater<Entry>> queue;
        distance[start]=0; touched.push_back(start);queue.emplace(0,start);
        while(!queue.empty()){
            auto [d,u]=queue.top();queue.pop(); if(d!=distance[u])continue;++visited;
            for(U e=offsets[u];e<offsets[u+1];++e){U v=neighbors[e];double nd=d+weights[e];if(nd<=cutoff&&nd<distance[v]){if(distance[v]==INF)touched.push_back(v);distance[v]=nd;queue.emplace(nd,v);}}
        }
        for(U q=begin;q<end;++q)results[std::get<2>(requests[q])]=distance[std::get<1>(requests[q])];
        for(U v:touched)distance[v]=INF;touched.clear();begin=end;++searches;
    }
    std::cerr<<"bounded_searches="<<searches<<" settled_nodes="<<visited<<"\n";
    std::cout.write(reinterpret_cast<char*>(results.data()),results.size()*sizeof(double));
    return std::cout.good()?0:4;
} catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 5;} }
