// Deterministic topology-only recursive BFS bisection. No query inputs.
// Nodes are ranked by stable OSM identity before entering this program.
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <numeric>
#include <vector>
using I=int64_t;
struct Region { int parent,left=-1,right=-1,depth; I sites,nodes; int reason=0; };
std::vector<std::vector<int>> adj;
std::vector<int> weight, mark, visited, side, leaves;
std::vector<Region> regions;
int token=0, capacity;
int split(const std::vector<int>& nodes,int parent,int depth) {
 int id=regions.size(); I total=0; for(int u:nodes)total+=weight[u];
 regions.push_back({parent,-1,-1,depth,total,I(nodes.size()),0});
 if(total<=capacity){for(int u:nodes)leaves[u]=id; return id;}
 int t=++token; for(int u:nodes)mark[u]=t;
 std::vector<int> order;order.reserve(nodes.size());
 for(int seed:nodes)if(visited[seed]!=t){
  size_t begin=order.size();visited[seed]=t;order.push_back(seed);
  for(size_t k=begin;k<order.size();k++)for(int v:adj[order[k]])
   if(mark[v]==t && visited[v]!=t){visited[v]=t;order.push_back(v);}
 }
 I cumulative=0,best=total+1;size_t cut=0;
 for(size_t k=0;k<order.size();k++){
  cumulative+=weight[order[k]];
  if(cumulative>0 && cumulative<total && std::abs(2*cumulative-total)<best){
   best=std::abs(2*cumulative-total);cut=k+1;
  }
 }
 if(!cut){regions[id].reason=1;for(int u:nodes)leaves[u]=id;return id;}
 for(size_t k=0;k<order.size();k++)side[order[k]]=k<cut?0:1;
 std::vector<int> a,b; a.reserve(cut); b.reserve(nodes.size()-cut);
 for(int u:nodes)(side[u]?b:a).push_back(u);
 // Release the traversal buffer before descent; children retain identity order.
 std::vector<int>().swap(order);
 int l=split(a,id,depth+1),r=split(b,id,depth+1);
 regions[id].left=l;regions[id].right=r;return id;
}
int main(int argc,char**argv){
 if(argc!=5)return 2;
 std::ifstream in(argv[1],std::ios::binary);I n,m,s;in.read((char*)&n,8);in.read((char*)&m,8);in.read((char*)&s,8);
 if(!in||n<=0||n>INT32_MAX)return 3;
 adj.resize(n);weight.assign(n,0);mark.assign(n,0);visited.assign(n,0);side.resize(n);leaves.resize(n);
 for(I k=0;k<m;k++){int u,v;in.read((char*)&u,4);in.read((char*)&v,4);adj[u].push_back(v);adj[v].push_back(u);}
 for(auto&v:adj){std::sort(v.begin(),v.end());v.erase(std::unique(v.begin(),v.end()),v.end());}
 for(I k=0;k<s;k++){int u;in.read((char*)&u,4);weight[u]++;}
 if(!in)return 4;
 capacity=std::stoi(argv[4]);if(capacity<1)return 5;
 std::vector<int> nodes(n);std::iota(nodes.begin(),nodes.end(),0);split(nodes,-1,0);
 std::ofstream leaf(argv[2],std::ios::binary);leaf.write((char*)leaves.data(),4*n);
 std::ofstream meta(argv[3]);meta<<"region,parent,left,right,depth,sites,nodes,reason\n";
 for(size_t k=0;k<regions.size();k++){auto&r=regions[k];meta<<k<<','<<r.parent<<','<<r.left<<','<<r.right<<','<<r.depth<<','<<r.sites<<','<<r.nodes<<','<<r.reason<<'\n';}
 return (!leaf||!meta)?6:0;
}
